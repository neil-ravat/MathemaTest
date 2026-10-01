from scripts.run_support_controls import cases, select, metrics


def test_controlled_omission_and_evidence_boundary():
    supported, omitted, ambiguous = cases()[:3]
    assert [d for d in supported['docs'] if d['id'] != 'd3'] == omitted['docs']
    assert supported['docs'] == ambiguous['docs']
    assert supported['expected_value'] == 12
    assert omitted['expected_value'] is ambiguous['expected_value'] is None
    ranking = ['d1', 'd4', 'd5', 'd6', 'd2', 'd3']
    graph = select(supported, 'graph', ranking)
    assert [d['id'] for d in graph['context']] == ['d1', 'd4', 'd2', 'd3']
    assert not graph['context_complete']
    assert select(supported, 'complete', ranking)['context_complete']
    assert not select(supported, 'direct', ranking)['context']
    assert 'expected' not in graph and 'group' not in graph


def test_errors_and_uncertified_gaps_stay_in_results():
    rows = [dict(arm='vector', elapsed_seconds=1, error='timeout'),
            dict(arm='vector', elapsed_seconds=2, expected='SUPPORTED',
                 expected_value=12, payload={'context_complete': False},
                 judgment={'verdict': 'CONTROLLED_GAP', 'value': None})]
    result = metrics(rows)['vector']
    assert result['attempts'] == 2 and result['errors'] == 1
    assert result['false_gap_flags'] == result['unsupported_gap_flags'] == 1
