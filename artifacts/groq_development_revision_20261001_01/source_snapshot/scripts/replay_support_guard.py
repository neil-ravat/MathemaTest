"""Replay saved diagnostic decisions through the shared gap boundary; no inference."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.verification.parameter_support import guard_gap_claim


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    rows = []
    for path in sorted(args.input.glob('result-*.json')):
        saved = json.loads(path.read_text())
        row = dict(case_id=saved['case_id'], arm=saved['arm'],
                   input_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
        if 'judgment' not in saved:
            row.update(status='INVALID_OUTPUT', error=saved['error'])
        else:
            j = saved['judgment']
            status, reason = guard_gap_claim(j['verdict'], j['reason'],
                context_complete=saved['payload']['context_complete'])
            row.update(raw_status=j['verdict'], status=status, reason=reason)
        rows.append(row)
    assert rows, 'No saved results'
    result = dict(scope='Post-hoc development replay of gap guard only; no numeric provenance replay or new inference',
        changed=sum(r.get('raw_status') != r['status'] for r in rows if 'raw_status' in r),
        invalid=sum(r['status'] == 'INVALID_OUTPUT' for r in rows), rows=rows,
        guard_sha256=hashlib.sha256((ROOT/'src/verification/parameter_support.py').read_bytes()).hexdigest())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x') as f:
        json.dump(result, f, indent=2)
    print(f'{len(rows)} saved outputs; {result["changed"]} gap claims changed to uncertainty; {result["invalid"]} invalid outputs retained')


if __name__ == '__main__':
    main()
