"""Report integrity rejects partial/tampered runs and preserves failed-case denominators."""
import copy
import hashlib
import json
from pathlib import Path
import shutil

import pytest

from scripts.controlled_benchmark import DEST
from scripts.report_decomposed_study import ROOT, read_run, paired_differences
from scripts.run_controlled_study import summarize

BASELINE = ROOT / 'artifacts/controlled_study/20260917T201622567827Z'


def test_saved_baseline_and_reject_corruption(tmp_path):
    gold = {c['id']: c for c in json.loads((DEST / 'development.json').read_text())}
    benchmark = json.loads((DEST / 'manifest.json').read_text())
    rows, _ = read_run(BASELINE, gold, benchmark)
    assert len(rows) == 192
    run = tmp_path / 'run'
    shutil.copytree(BASELINE, run)

    def replace(records):
        data = ''.join(json.dumps(r) + '\n' for r in records).encode()
        (run / 'predictions.jsonl').write_bytes(data)
        (run / 'COMPLETE.json').write_text(json.dumps({'calls': len(records),
            'predictions_sha256': hashlib.sha256(data).hexdigest()}))

    replace(rows[:-1])
    with pytest.raises(ValueError, match='matched cases'):
        read_run(run, gold, benchmark)
    replace(rows[:-1] + [rows[0]])
    with pytest.raises(ValueError, match='matched cases'):
        read_run(run, gold, benchmark)
    changed = copy.deepcopy(rows)
    changed[0]['messages'][1]['content'] = '{}'
    replace(changed)
    with pytest.raises(ValueError, match='Payload mismatch'):
        read_run(run, gold, benchmark)
    replace(rows)
    (run / 'predictions.jsonl').write_text('tampered')
    # Invalid JSON must also fail before a report can be produced.
    with pytest.raises((ValueError, json.JSONDecodeError)):
        read_run(run, gold, benchmark)


def test_paired_errors_and_abstentions_stay_in_denominator():
    gold = {c['id']: c for c in json.loads((DEST / 'development.json').read_text())}
    rows, _ = read_run(BASELINE, gold, json.loads((DEST / 'manifest.json').read_text()))
    revised = [copy.deepcopy(r) for r in rows if r['prompt'] == 'evidence']
    for row in revised:
        row['prompt'] = 'decomposed'
        row.pop('verdict', None)
        row['error_type'] = 'runtime'
        row['correct'] = True  # Stored convenience flag must never control scoring.
    revised[0].pop('error_type')
    revised[0]['verdict'] = {'status': 'ABSTAIN'}
    stats = summarize(revised)
    assert all(s['attempts'] == 48 and s['exact_matches'] == 0 for s in stats.values())
    paired = paired_differences(rows, revised, gold)
    assert all(s['gained_cases'] == 0 and s['difference'] < 0 for s in paired.values())
