import json
import pytest
from scripts.prepare_ncert_output_review import blind_rows


def test_blinding_keeps_all_failures_and_evidence_but_hides_arm_provenance():
    cases = [dict(original_case_id='c', case_id='FRESH-01')]
    rows = [dict(case_id='c', mode=m, status='ERROR' if m == 'graph' else 'PASS',
        error='graph construction failed', judgment=dict(answer='value from internal-graph-node',
        reason='internal-graph-node supports it', cited_passage_ids=['internal-graph-node']),
        context=[dict(id='internal-graph-node', content='original text', source=m,
            metadata=dict(start_offset=0, end_offset=13, factual_provenance=['secret']))])
        for m in ('direct', 'vector', 'graph')]
    packet, key = blind_rows(rows, cases)
    encoded = json.dumps(packet)
    assert len(packet) == 3 and sum(p['operational_status'] == 'ERROR' for p in packet) == 1
    assert '"mode"' not in encoded and 'factual_provenance' not in encoded
    assert 'internal-graph-node' not in encoded and 'construction failed' not in encoded
    assert all(p['context'][0]['text'] == 'original text' for p in packet)
    assert {k['mode'] for k in key} == {'direct', 'vector', 'graph'}
    assert rows[0]['judgment']['cited_passage_ids'] == ['internal-graph-node']
    with pytest.raises(ValueError, match='exactly once'):
        blind_rows(rows[:-1], cases)
