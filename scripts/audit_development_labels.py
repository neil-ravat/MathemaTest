"""Read-only check of visible development text, labels, and historical payloads.

Run from any directory with the repository's .venv/bin/python. No model calls,
benchmark generation, held-out access, or artifact writes occur.
"""
import ast
from collections import Counter
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_controlled_study import context_for


def classify(payload):
    """Evaluate this development grammar using visible text alone, never eval()."""
    if re.fullmatch(r'Preview: \w+ will be used later\. No calculation or proof is asserted here\.', payload['target']):
        return 'PASS'
    definitions = {}
    passages = [d for d in payload['context'] if d['position'] < payload['target_position']]
    for passage in passages + payload['background_passages']:
        match = re.fullmatch(r'Define (\w+)\(x\) = (.+)\.', passage['content'])
        if not match or match[1] in definitions:
            raise ValueError('Unrecognized or duplicate definition')
        definitions[match[1]] = ast.parse(match[2], mode='eval').body
    target = re.fullmatch(r'Check the equality (\w+)\((\d+)\) = (\d+)\.', payload['target'])
    if not target:
        raise ValueError('Unrecognized target')

    def evaluate(node, x, active):
        if isinstance(node, ast.Name) and node.id == 'x':
            return x
        if isinstance(node, ast.Constant) and type(node.value) is int:
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            return evaluate(node.left, x, active) + evaluate(node.right, x, active)
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
                and len(node.args) == 1 and not node.keywords):
            return function(node.func.id, evaluate(node.args[0], x, active), active)
        raise ValueError('Unsupported expression')

    def function(name, x, active):
        if name in active:
            raise ValueError('Cyclic definition')
        return evaluate(definitions[name], x, active | {name})

    try:
        value = function(target[1], int(target[2]), set())
    except KeyError:
        return 'FAIL_GAP' if payload['context_complete'] else 'ABSTAIN'
    return 'PASS' if value == int(target[3]) else 'FAIL_LOGIC'


def main():
    development = ROOT / 'data/controlled_curricula_v1/development.json'
    manifest = json.loads((development.parent / 'manifest.json').read_text())
    development_hash = hashlib.sha256(development.read_bytes()).hexdigest()
    assert development_hash == manifest['files']['development.json']
    cases = json.loads(development.read_text())
    payloads = {c['id']: context_for(c, 'complete') for c in cases}
    matches = sum(classify(payloads[c['id']]) == c['expected'] for c in cases)
    assert len(cases) == 48 and matches == len(cases)
    result = {'development_sha256': development_hash, 'cases': len(cases),
              'independent_label_matches': matches,
              'unique_complete_payloads': len({json.dumps(p, sort_keys=True) for p in payloads.values()}),
              'expected_classes': dict(Counter(c['expected'] for c in cases)), 'runs': {}}
    for name in ('20260917T201302167860Z', '20260917T201622567827Z'):
        run = ROOT / 'artifacts/controlled_study' / name
        raw = (run / 'predictions.jsonl').read_bytes()
        checksum = hashlib.sha256(raw).hexdigest()
        assert checksum == json.loads((run / 'COMPLETE.json').read_text())['predictions_sha256']
        rows = [json.loads(line) for line in raw.splitlines()]
        info = {'predictions_sha256': checksum, 'rows': len(rows)}
        if name == '20260917T201622567827Z':
            info['matching_saved_payloads'] = sum(json.loads(r['messages'][1]['content']) == payloads[r['case_id']] for r in rows)
            info['complete_payloads'] = sum(r['context_complete'] for r in rows)
            info['future_items'] = sum(r['future_items'] for r in rows)
            assert info['matching_saved_payloads'] == len(rows) == 192
        info['scores'] = {' | '.join(key): sum(r.get('verdict', {}).get('status') == r['expected'] for r in rows if (r['model'], r['prompt']) == key)
                          for key in sorted({(r['model'], r['prompt']) for r in rows})}
        result['runs'][name] = info
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
