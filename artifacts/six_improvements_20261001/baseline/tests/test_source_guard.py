"""Focused narrow-grammar checks; only hand-authored public text, no benchmark scoring."""
import pytest

from scripts.run_decomposed_study import EvidenceError
from src.verification.source_guard import source_analysis, guard_evidence


def payload(target='f(2) = 6.', definitions=('Define f(x) = x + (x + 2).',)):
    return {'target': target, 'target_position': 10, 'context_complete': True,
            'background_knowledge': 'Integer arithmetic and equality.',
            'background_passages': [], 'context': [
                {'id': f'p{i}', 'position': i, 'content': text} for i, text in enumerate(definitions)]}


def evidence(calculation='2+2+2', **updates):
    result = {'target_kind': 'equality', 'claimed_value': 6, 'calculation': calculation,
              'missing_prerequisites': [], 'cited_passage_ids': ['p0'], 'reason': 'Substitute.'}
    result.update(updates)
    return result


def test_association_normalized_without_folding_or_reordering():
    p = payload()
    assert source_analysis(p)['arithmetic_structure'] == ['add', ['integer', 2], ['integer', 2], ['integer', 2]]
    assert guard_evidence(evidence(), p)['accepted']
    for expression in ('6', '3+3', '(2+2)+2+0', '2*3'):
        r = guard_evidence(evidence(expression), p)
        assert r['rejection_reason'] == 'calculation_structure_mismatch'
        assert r['verdict']['status'] == 'ABSTAIN'
    p = payload('f(2) = -6.', ('Define f(x) = -(x * (x + 1)).',))
    assert guard_evidence(evidence('-(2*(2+1))', claimed_value=-6), p)['accepted']


def test_guard_accepts_source_supported_failure_without_correcting_a_wrong_model():
    p = payload('f(2) = 7.')
    r = guard_evidence(evidence(claimed_value=7), p)
    assert r['accepted'] and r['verdict']['status'] == 'FAIL_LOGIC'
    r = guard_evidence(evidence('7', claimed_value=7), p)
    assert r['source']['source_status'] == 'FAIL_LOGIC'
    assert not r['accepted'] and r['verdict']['status'] == 'ABSTAIN'
    with pytest.raises(EvidenceError):
        guard_evidence(evidence(claimed_value=999), p)


def test_nested_arguments_and_repeated_calls():
    p = payload('f(2) = 11.', ('Define f(x) = g(x + 1) + g(x).', 'Define g(x) = x * 2.'))
    a = source_analysis(p)
    assert a['computed_value'] == 10 and a['source_status'] == 'FAIL_LOGIC'
    assert a['required_passage_ids'] == ['p0', 'p1']
    assert guard_evidence(evidence('(2+1)*2+2*2', claimed_value=11, cited_passage_ids=['p0', 'p1']), p)['accepted']
    p = payload('f(f(2)) = 14.', ('Define f(x) = x + (x + 2).',))
    assert source_analysis(p)['computed_value'] == 14


@pytest.mark.parametrize('target', [
    'Preview: f will be used later. No calculation or proof is asserted here.',
    'Preview only: a function called f will be defined later; no calculation or proof is required here.',
])
def test_explicit_preview(target):
    p = payload(target)
    e = evidence(None, target_kind='preview', claimed_value=None, cited_passage_ids=[])
    assert guard_evidence(e, p)['accepted']


@pytest.mark.parametrize('target', [
    'Preview: one is greater than two. No calculation or proof is required here.',
    'Preview: f will be used later. No calculation or proof is asserted here. False claim.',
    'True = 1.', '__import__("os") = 1.', 'f(x) = 1.', '2**3 = 8.', '6/2 = 3.',
])
def test_unsupported_public_target(target):
    r = source_analysis(payload(target))
    assert not r['supported'] and r['source_status'] == 'ABSTAIN'


def test_background_declarations_and_operation_scope():
    p = payload('2+3 = 5.', ())
    for background in ('Integer addition and equality. Function names are local to this curriculum.',
                       'Integer arithmetic and equality; f, g, and h are unfamiliar textbook-specific function names.'):
        p['background_knowledge'] = background
        assert source_analysis(p)['source_status'] == 'PASS'
    p['background_knowledge'] = 'Integer addition and equality.'
    p['target'] = '2*3 = 6.'
    assert source_analysis(p)['reason'] == 'unsupported_background_operation'
    p['background_knowledge'] = 'Integer arithmetic and equality. Do not use arithmetic.'
    assert source_analysis(p)['reason'] == 'unsupported_background'


def test_missing_arg_does_not_hide_dependency_cycle():
    p = payload('f(missing(2)) = 1.', ('Define f(x) = f(x).',))
    r = source_analysis(p)
    assert not r['supported'] and r['reason'] == 'cyclic_definition'


def test_nested_doubling_calls_hit_expansion_bound_before_materialization():
    target = 'f('*20 + '1' + ')'*20 + ' = 1.'
    result = source_analysis(payload(target, ('Define f(x) = x + x.',)))
    assert not result['supported']
    assert result['reason'] == 'expanded_expression_node_bound'
