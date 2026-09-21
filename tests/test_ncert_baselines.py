import json
import pytest
from scripts.run_ncert_baselines import (budget_context, request_body, validate_response,
                                         numeric_agreement, summarize, wilson, graph_trace, graph_coverage,
                                         require_graph_source)
from scripts.run_ncert_baselines import factual_augmentation, selected_factual_paths, merge_passages
from scripts.build_ncert_study_corpus import validate_cases


def row(id='p', text='abc', start=0, end=3):
    return dict(id=id, content=text, metadata=dict(source_id='s', start_offset=start, end_offset=end))


def response(**updates):
    judgment = dict(status='PASS', answer='300 C', reason='Current multiplied by time',
                    cited_passage_ids=['p'], assumptions=[], missing_prerequisites=[],
                    numeric_value='300', answer_unit='C',
                    arithmetic_checks=[dict(expression='0.5*10*60', claimed_value='300')])
    judgment.update(updates)
    return dict(done=True, done_reason='stop', message=dict(content=json.dumps(judgment)))


def test_context_budget_never_slices_evidence_and_deduplicates():
    rows = [row(), row('duplicate'), row('huge', 'x'*20, 3, 23), row('small', 'def', 23, 26)]
    assert [r['id'] for r in budget_context(rows, 's', 30, max_chars=6)] == ['p', 'small']
    assert budget_context(rows, 's', 30, max_passages=1) == [rows[0]]


@pytest.mark.parametrize('bad', [row(end=31), row(start=True), row(start=3, end=3)])
def test_context_unsafe_provenance_fails_closed(bad):
    with pytest.raises(ValueError, match='Source-order'):
        budget_context([bad], 's', 30)


def test_matched_requests_exclude_reference_and_only_evidence_policy_differs():
    case = dict(target_raw='Question', expected_answer='SECRET')
    direct = request_body(case, 'direct', [])
    vector = request_body(case, 'vector', [row()])
    graph = request_body(case, 'graph', [row()])
    assert vector == graph
    assert 'SECRET' not in json.dumps(vector)
    for key in ('model', 'options', 'stream', 'format'):
        assert direct[key] == vector[key]
    assert direct['options']['num_ctx'] == 16384
    assert 'learned subject knowledge' in direct['messages'][0]['content']


def test_direct_citations_unavailable_retrieval_citations_required():
    direct, checks = validate_response(response(cited_passage_ids=[]), 'direct', [])
    assert direct['status'] == 'PASS' and checks[0]['consistent']
    with pytest.raises(ValueError, match='PASS missing'):
        validate_response(response(cited_passage_ids=[]), 'vector', [row()])
    with pytest.raises(ValueError, match='invalid citation'):
        validate_response(response(), 'direct', [])


def test_nonpass_conflict_and_false_arithmetic_visible():
    with pytest.raises(ValueError, match='Conflicting'):
        validate_response(response(status='ABSTAIN'), 'vector', [row()])
    _, checks = validate_response(response(arithmetic_checks=[dict(expression='1+1', claimed_value='3')]), 'vector', [row()])
    assert checks[0]['consistent'] is False


def test_scalar_agreement_is_narrow_and_errors_remain_denominator():
    refs = {'jesc111:example-11.1': {'expected_answer': {'charge': 300}}}
    assert numeric_agreement('jesc111:example-11.1', dict(status='PASS', numeric_value='600/2'), refs)
    assert numeric_agreement('jesc111:example-11.1', None, refs) is False
    assert numeric_agreement('jemh104:example-3', None, refs) is None
    results = [dict(case_id='c', mode='vector', status='ERROR', wall_seconds=1,
                    numeric_reference_agreement=False)]
    summary = summarize(results)['vector']
    assert summary['scalar_agreement_denominator'] == 1
    assert summary['scalar_agreement_correct'] == 0
    assert summary['educational_accuracy'] is None
    assert summary['cost_usd'] is None
    assert wilson(0, 0) is None


def test_graph_trace_distinguishes_discovery_from_selected_evidence():
    p = row()
    p['metadata']['graph_trace'] = {'expansions': [{'path_ids': ['a', 'b']}]}
    trace = graph_trace([p], [p])
    assert trace['prerequisite_expansion_active'] is True
    assert trace['prerequisite_evidence_in_context'] is False
    p['metadata']['graph_provenance'] = [{'kind': 'prerequisite', 'path_ids': ['a', 'b']}]
    assert graph_trace([p], [p])['selected_prerequisite_paths'] == [['a', 'b']]
    assert graph_trace([p], [])['prerequisite_evidence_in_context'] is False


def test_graph_coverage_zero_edges_is_not_prerequisite_ablation():
    nodes = [dict(id='a', source_id='s', start_offset=0, end_offset=3),
             dict(id='b', source_id='s', start_offset=4, end_offset=9)]
    edge = dict(source='a', target='b', type='PREREQUISITE_OF')
    assert not graph_coverage({'target_start_offset': 5}, 's', nodes, [edge])['prerequisite_ablation_available']
    assert graph_coverage({'target_start_offset': 9}, 's', nodes, [edge])['persisted_prerequisite_edges'] == 1


def test_source_specific_graph_failures_never_fall_back(tmp_path):
    manifest = {'graph_source_status': {'a': {'status': 'success'}, 'b': {'status': 'error'},
                                         'c': {'status': 'empty'}}}
    require_graph_source(manifest, 'a', tmp_path)
    for source in ('b', 'c', 'absent'):
        with pytest.raises(ValueError, match='no graph fallback'):
            require_graph_source(manifest, source, tmp_path)


def test_fresh_cases_stay_unscored_and_safe_file_names_required():
    case = dict(id='x', source_id='jemh103', target_start_offset=10, target_end_offset=20)
    validate_cases([case])
    with pytest.raises(ValueError, match='unique'):
        validate_cases([case, case])
    with pytest.raises(ValueError, match='filename'):
        validate_cases([{**case, 'source_id': '../x'}])
    results = [dict(case_id='x', mode='direct', status='PASS', wall_seconds=1,
                    numeric_reference_agreement=None)]
    summary = summarize(results, development=False)
    assert summary['direct']['scalar_agreement_denominator'] == 0
    assert summary['direct']['educational_accuracy'] is None
    assert 'Fresh' in summary['limitations'][0]


def factual_fixture():
    text = 'aaa bbb ccc'
    nodes = [dict(id='a', source_id='s', start_offset=0, end_offset=3, content='aaa', semantic_role='quantity'),
             dict(id='b', source_id='s', start_offset=4, end_offset=7, content='bbb', semantic_role='unit')]
    edge = dict(source='a', target='b', type='HAS_UNIT', properties=dict(
        source_id='s', start_offset=8, end_offset=11, content='ccc'))
    seed = dict(id='a', content='aaa', source='vector', score=.9, metadata=nodes[0].copy())
    return text, nodes, [edge], [seed]


def test_factual_edges_add_original_neighbor_and_edge_without_prerequisite_claim():
    text, nodes, edges, seeds = factual_fixture()
    rows, trace = factual_augmentation(seeds, nodes, edges, source_id='s', before_position=11, source_text=text)
    assert [r['content'] for r in rows] == ['aaa', 'bbb', 'ccc']
    assert trace['discovered_factual_paths'][0]['edge_type'] == 'HAS_UNIT'
    assert len(selected_factual_paths(rows)) == 1
    assert set(selected_factual_paths(rows)[0]['evidence_roles']) == {'neighbor', 'edge_evidence'}
    assert all('graph_provenance' not in r['metadata'] for r in rows)
    assert 'factual_provenance' not in seeds[0]['metadata']
    assert [r['content'] for r in merge_passages(rows + rows)] == ['aaa', 'bbb', 'ccc']


@pytest.mark.parametrize('target,field,value', [
    ('edge', 'source_id', 'other'), ('edge', 'start_offset', True),
    ('edge', 'end_offset', 20), ('edge', 'content', 'invented'),
    ('neighbor', 'source_id', 'other'), ('neighbor', 'end_offset', 20),
    ('neighbor', 'content', 'invented'), ('seed_node', 'source_id', 'other')])
def test_factual_augmentation_rejects_unsafe_edge_and_node_evidence(target, field, value):
    text, nodes, edges, seeds = factual_fixture()
    record = edges[0]['properties'] if target == 'edge' else nodes[1] if target == 'neighbor' else nodes[0]
    record[field] = value
    rows, trace = factual_augmentation(seeds, nodes, edges, source_id='s', before_position=11, source_text=text)
    assert len(rows) == 1 and not trace['discovered_factual_paths']
    assert trace['rejected_factual_paths']


def test_future_edge_with_prior_endpoints_is_excluded_and_incoming_keeps_direction():
    text, nodes, edges, seeds = factual_fixture()
    rows, trace = factual_augmentation(seeds, nodes, edges, source_id='s', before_position=7, source_text=text)
    assert len(rows) == 1 and not trace['discovered_factual_paths']
    incoming = [dict(id='b', content='bbb', source='vector', score=.9, metadata=nodes[1].copy())]
    _, trace = factual_augmentation(incoming, nodes, edges, source_id='s', before_position=11, source_text=text)
    assert trace['discovered_factual_paths'][0]['traversal'] == 'incoming'
    assert trace['discovered_factual_paths'][0]['from_id'] == 'a'
    edges[0]['type'] = 'PREREQUISITE_OF'
    _, trace = factual_augmentation(seeds, nodes, edges, source_id='s', before_position=11, source_text=text)
    assert not trace['discovered_factual_paths']
