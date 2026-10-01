"""Offline replay must never turn historical failure or rejection into a repaired answer."""
import copy
import json

import pytest

from scripts.controlled_benchmark import DEST
from scripts.replay_source_guard import ROOT, read_inputs, guarded_row, metrics, replay_original
from scripts.run_controlled_study import context_for

DEV = ROOT / 'artifacts/controlled_study/20260919T223749942686Z'
GATE = ROOT / 'artifacts/controlled_study/20260919T225703610993Z'


def test_completed_input_integrity_and_raw_replay():
    rows, cases = read_inputs(DEV, GATE)
    assert len(rows['development']) == 96 and len(rows['gate']) == 14
    row = copy.deepcopy(next(r for r in rows['development'] if r.get('verdict')))
    payload = context_for(cases['development'][row['case_id']], 'complete')
    row['verdict']['status'] = 'ABSTAIN'
    with pytest.raises(ValueError, match='success replay mismatch'):
        replay_original(row, payload)


def test_preserved_errors_and_withheld_correct_denominators(monkeypatch):
    from src.verification import source_guard
    data = [json.loads(line) for line in (DEV/'predictions.jsonl').read_text().splitlines()]
    cases = {c['id']: c for c in json.loads((DEST/'development.json').read_text())}
    # Force rejection to test reporting mechanics independently of guard semantics.
    monkeypatch.setattr(source_guard, 'guard_evidence', lambda evidence, payload: {
        'accepted': False, 'rejection_reason': 'test_rejection', 'source': {},
        'verdict': {'status': 'ABSTAIN', 'reason': 'withheld'}})
    guarded = [guarded_row(r, context_for(cases[r['case_id']], 'complete')) for r in data]
    for before, after in zip(data, guarded):
        if before.get('error_type'):
            assert after['error_type'] == before['error_type'] and 'verdict' not in after
        else:
            assert after['verdict']['status'] == 'ABSTAIN'
    values = metrics(guarded)
    assert all(s['attempts'] == 48 and s['exact_matches'] == 0 and s['accepted_count'] == 0
               and s['conditional_accuracy_accepted'] is None for s in values.values())
    assert sorted(s['correct_labels_withheld'] for s in values.values()) == [16, 29]

    wrong = next(r for r in guarded if r['original_status'] in ('PASS', 'FAIL_GAP', 'FAIL_LOGIC')
                 and r['original_status'] != r['expected'])
    key = wrong['model'] + ' | source_guard | complete'
    before_count = values[key]['wrong_answers_withheld']
    wrong['original_status'] = 'ABSTAIN'
    assert metrics(guarded)[key]['wrong_answers_withheld'] == before_count - 1
    assert all(r['seconds'] >= 0 and 'original_seconds' in r for r in guarded)
