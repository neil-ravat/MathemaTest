import pytest
from scripts.summarize_ncert_ai_scores import summarize


def test_errors_remain_denominator_and_bootstrap_preserves_chapter_pairs():
    cases = [dict(id='c1', source_id='s1'), dict(id='c2', source_id='s2')]
    scores, key, results = [], [], []
    for c in cases:
        for mode in ('direct', 'vector', 'graph'):
            oid = c['id']+mode
            key.append(dict(output_id=oid, case_id=c['id'], mode=mode))
            scores.append(dict(output_id=oid, answer_category='ERROR' if mode == 'graph' else 'COMPLETE',
                evidence_support='ADEQUATE' if mode == 'vector' else 'SOURCE_UNAVAILABLE', reference_resolvable=True))
            results.append(dict(case_id=c['id'], mode=mode, status='ERROR' if mode == 'graph' else 'PASS',
                latency_including_shared_vector_search_seconds=1))
    out = summarize(scores, key, cases, results)
    assert out['graph']['scheduled'] == 2 and out['graph']['full_correct_proportion'] == 0
    assert out['vector']['grounded_correct'] == 2
    assert out['paired']['grounded_losses'] == 2 and out['paired']['chapter_bootstrap95'] == [-1, -1]
    scores[-1]['answer_category'] = 'COMPLETE'
    with pytest.raises(ValueError, match='rescued'):
        summarize(scores, key, cases, results)
