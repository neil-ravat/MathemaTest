"""Local prompt-only diagnostic; synthetic labels, not end-to-end accuracy."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.compare_local_workflows import SINGLE, SingleDecision
from scripts import run_curriculum_audit as transport

BACKGROUND = ('Arithmetic, substitution into supplied formulas and elementary algebra are known. '
              'No subject-specific definitions or formulas are granted without source evidence.')


def cases():
    rows = [
        ('circle-stated', 'A circle has radius 4. Find its circumference.',
         'Formula for circumference of a circle', 'Circumference of a circle is 2 times pi times its radius.',
         BACKGROUND, 'SUPPORTED', 'The source states the requested rule.'),
        ('circle-absent', 'A circle has radius 4. Find its circumference.',
         'Formula for circumference of a circle', 'The radius is a distance from the centre of a circle to its boundary.',
         BACKGROUND, 'UNRESOLVED', 'The radius definition and arithmetic alone do not establish circumference.'),
        ('buoyancy-stated', 'An immersed object displaces 0.004 cubic metres of water of density 1000 kilograms per cubic metre. Gravitational acceleration is 10 metres per second squared. Find the buoyant force.',
         'Formula for buoyant force', 'Buoyant force equals displaced fluid density times displaced volume times gravitational acceleration.',
         BACKGROUND, 'SUPPORTED', 'The source states the force relationship.'),
        ('buoyancy-absent', 'An immersed object displaces 0.004 cubic metres of water of density 1000 kilograms per cubic metre. Gravitational acceleration is 10 metres per second squared. Find the buoyant force.',
         'Formula for buoyant force', 'Buoyancy is an upward force exerted by a fluid on an immersed object.',
         BACKGROUND, 'UNRESOLVED', 'The qualitative definition does not establish the quantitative force law.'),
        ('ordinary-operation', 'Multiply the supplied values 6 and 7.', 'Multiplication of two supplied values',
         'The task supplies two integers.', BACKGROUND, 'SUPPORTED', 'Multiplication is ordinary granted arithmetic.'),
        ('explicit-prior-rule', 'Find simple interest for principal 80, rate 0.05 per year and time 2 years.',
         'Simple interest formula', 'The principal is the starting amount.',
         BACKGROUND + ' The learner already knows the simple interest rule I = P*r*t, with annual rate r and time t in years.',
         'SUPPORTED', 'The background explicitly grants this specific rule.'),
        ('derived-rule', 'A sample has mass 12 and density 3. Find its volume.',
         'Obtain volume from mass and density', 'Density d = m/V, where m is mass and V is volume; d and V are positive.',
         BACKGROUND, 'SUPPORTED', 'Granted algebra gives d*V=m, then V=m/d; no additional subject law is needed.'),
        ('method-name-only', 'Calibration inputs are x=4 and y=7. Find the calibration score.',
         'Calibration score formula', 'The calibration score uses inputs x and y. Its formula is introduced later.',
         BACKGROUND, 'UNRESOLVED', 'Several different score functions fit this statement; no unique rule is supplied.'),
    ]
    return [dict(id=i, payload=dict(target=t, requirement=q, evidence_catalog=[
        dict(evidence_id='B0', source='background', id='background', quote=b),
        dict(evidence_id='E0', source='passage', id='rule', quote=e)]), expected=s, label_reason=why)
        for i, t, q, e, b, s, why in rows]


def score(plan, results):
    expected = {c['id']: c['expected'] for c in plan}
    return {arm: dict(completed=sum(r['arm'] == arm for r in results),
        matches=sum(r['arm'] == arm and r.get('decision', {}).get('status') == expected[r['case_id']] for r in results),
        false_support=sum(r['arm'] == arm and expected[r['case_id']] == 'UNRESOLVED' and r.get('decision', {}).get('status') == 'SUPPORTED' for r in results),
        errors=sum(r['arm'] == arm and 'error' in r for r in results))
        for arm in ('previous', 'revised')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--prepare-only', action='store_true')
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=False)
    previous_path = ROOT/'artifacts/workflow_comparison_20261001/manifest.json'
    previous = json.loads(previous_path.read_text())['candidate_prompts']['single']
    plan = cases()
    hashes = {}
    for path in (Path(__file__).resolve(), ROOT/'scripts/compare_local_workflows.py', ROOT/'scripts/run_curriculum_audit.py', ROOT/'src/verification/curriculum_audit.py'):
        name = str(path.relative_to(ROOT)); dest = args.output/'source_snapshot'/name
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, dest)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    schema = SingleDecision.model_json_schema()
    schema['properties']['evidence_ids']['items']['enum'] = ['B0', 'E0']
    manifest = dict(created=datetime.now(timezone.utc).isoformat(), plan=plan,
        prompts=dict(previous=previous, revised=SINGLE), schema=schema, source_hashes=hashes,
        previous_manifest_sha256=hashlib.sha256(previous_path.read_bytes()).hexdigest(),
        model='qwen2.5-coder:7b', temperature=0, seed=42, max_tokens=500, context_tokens=16384,
        time_budget_seconds=900, per_call_timeout_seconds=120, retries=0,
        order='Alternate previous-first and revised-first by case index',
        scope='Eight synthetic requirement-level controls, no independent expert labels; prompt-only comparison, not full audit.',
        adoption_rule='Keep experimental. Prefer revised prompt only if it reduces unsupported acceptance without losing supported controls; inspect rationale and citations as well as statuses.')
    manifest_path = args.output/'manifest.json'
    manifest_path.write_text(json.dumps(manifest, indent=2))
    manifest_hash = hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if args.prepare_only:
        print('Prepared 16 calls'); return
    for endpoint in ('tags', 'version'):
        with urlopen(transport.ollama_base_url()+'/api/'+endpoint, timeout=10) as response:
            (args.output/f'ollama-{endpoint}.json').write_bytes(response.read())
    transport.DEADLINE = time.monotonic()+900
    transport.REQUEST_TIMEOUT_SECONDS = 120
    results = []
    try:
        for i, case in enumerate(plan):
            for arm in (('previous', 'revised') if i % 2 == 0 else ('revised', 'previous')):
                row = dict(case_id=case['id'], arm=arm, messages=[
                    dict(role='system', content=manifest['prompts'][arm]),
                    dict(role='user', content=json.dumps(case['payload']))])
                started = time.monotonic()
                try:
                    response = transport.local_completion(model=manifest['model'], messages=row['messages'],
                        temperature=0, seed=42, max_tokens=500,
                        response_format={'type':'json_schema', 'json_schema':{'name':'requirement', 'strict':True, 'schema':schema}})
                    row['response'] = response.model_dump()
                    if response.choices[0].finish_reason != 'stop':
                        raise ValueError('Incomplete output')
                    decision = SingleDecision.model_validate_json(response.choices[0].message.content)
                    ids = set(decision.evidence_ids)
                    if not ids <= {'B0', 'E0'} or (decision.status == 'UNRESOLVED' and ids) or (decision.status != 'UNRESOLVED' and not ids):
                        raise ValueError('Invalid evidence references')
                    row['decision'] = decision.model_dump()
                except Exception as exc:
                    row['error'] = f'{type(exc).__name__}: {exc}'
                row['seconds'] = round(time.monotonic()-started, 3)
                results.append(row)
                (args.output/f'{i+1:02}-{arm}.json').write_text(json.dumps(row, indent=2))
                print(case['id'], arm, row.get('decision', {}).get('status', row.get('error')), flush=True)
                if 'timeout' in row.get('error', '').lower() or 'timed out' in row.get('error', '').lower():
                    raise TimeoutError('Stop after timeout; no queued retries')
    finally:
        unchanged = all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest() == h for n, h in hashes.items())
        manifest_unchanged = hashlib.sha256(manifest_path.read_bytes()).hexdigest() == manifest_hash
        (args.output/'summary.json').write_text(json.dumps(dict(planned_calls=16, completed=len(results),
            arms=score(plan, results), code_unchanged=unchanged, manifest_unchanged=manifest_unchanged,
            accuracy=None, independent_labels=False), indent=2))
        if not unchanged or not manifest_unchanged:
            raise ValueError('Frozen code or manifest changed')


if __name__ == '__main__':
    main()
