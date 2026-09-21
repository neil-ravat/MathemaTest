"""Compare complete decomposed development results with immutable historical baselines."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.controlled_benchmark import DEST, digest
from scripts.run_controlled_study import MODELS, context_for, summarize, decode


def require(condition, message):
    if not condition:
        raise ValueError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_run(path, gold, benchmark, decomposed=False):
    manifest = json.loads((path / 'manifest.json').read_text())
    complete = json.loads((path / 'COMPLETE.json').read_text())
    rows = [json.loads(line) for line in (path / 'predictions.jsonl').read_text().splitlines()]
    prompts = ['decomposed'] if decomposed else ['original', 'evidence']
    require(manifest['phase'] == 'development' and manifest['arms'] == ['complete'], 'Wrong phase or arm')
    require(manifest['prompts'] == prompts and set(manifest['models']) == set(MODELS), 'Wrong protocols or models')
    require(manifest['case_count'] == 48 and len(gold) == 48, 'Expected all 48 development cases')
    require(manifest['benchmark_manifest_hash'] == digest(benchmark), 'Benchmark provenance mismatch')
    require(complete['predictions_sha256'] == sha(path / 'predictions.jsonl'), 'Prediction hash mismatch')
    expected_keys = {(m, p, cid) for m in MODELS for p in prompts for cid in gold}
    require(len(rows) == len(expected_keys) and {(r['model'], r['prompt'], r['case_id']) for r in rows} == expected_keys,
            'Missing, duplicate, or unexpected matched cases')
    require(complete['calls'] == sum(r['model_calls'] if decomposed else 1 for r in rows), 'Call count mismatch')
    require(not decomposed or complete['rows'] == len(rows), 'Row count mismatch')
    require(manifest['temperature'] == 0 and manifest['seed'] == 42 and manifest['max_tokens'] == 500,
            'Generation settings changed')
    source_hashes = manifest.get('source_sha256')
    if source_hashes is None:
        paths = ['scripts/run_controlled_study.py', 'scripts/controlled_benchmark.py', 'src/config/settings.py',
                 'src/verification/verdicts.py', 'src/vector_store/embeddings.py', 'scripts/run_local_pilot.py']
        source_hashes = {name: sha(path / 'source_snapshot' / name) for name in paths}
    else:
        require(bool(source_hashes), 'Missing source hashes')
        require(all(sha(path / 'source_snapshot' / name) == value for name, value in source_hashes.items()),
                'Source snapshot hash mismatch')
    require(digest(source_hashes) == manifest['code_hash'], 'Code hash mismatch')
    if decomposed:
        required = {'scripts/run_decomposed_study.py', 'scripts/run_controlled_study.py',
                    'scripts/controlled_benchmark.py', 'src/config/settings.py',
                    'src/verification/verdicts.py', 'scripts/run_local_pilot.py'}
        require(required <= source_hashes.keys(), 'Incomplete source provenance')
        require(sha(path / 'requirements-local.lock.txt') == manifest['requirements_sha256'], 'Dependency lock mismatch')
        require(sha(ROOT / 'scripts/run_decomposed_study.py') == source_hashes['scripts/run_decomposed_study.py'],
                'Decision implementation changed; replay archived code explicitly')
        from scripts.run_decomposed_study import Evidence, decide
    if not decomposed:
        for name in ('scripts/run_controlled_study.py', 'src/verification/verdicts.py'):
            require(sha(ROOT / name) == sha(path / 'source_snapshot' / name), 'Historical decoder changed')
    for row in rows:
        case = gold[row['case_id']]
        require(all(row[k] == case[k] for k in ('family', 'category', 'expected')), 'Gold metadata mismatch')
        require(row['arm'] == 'complete' and row['context_complete'] and row['future_items'] == 0, 'Context mismatch')
        require(row['messages'][0] == {'role': 'system', 'content': manifest['prompt_texts'][row['prompt']]},
                'Recorded prompt mismatch')
        require(len(row['messages']) == 2 and row['messages'][1]['role'] == 'user'
                and json.loads(row['messages'][1]['content']) == context_for(case, 'complete'), 'Payload mismatch')
        require(not (row.get('error_type') and row.get('verdict')), 'Ambiguous error with verdict')
        require(row.get('error_type') or row.get('verdict'), 'Missing outcome')
        if not decomposed and row.get('verdict'):
            response = row['response']['choices'][0]
            require(response['finish_reason'] == 'stop' and decode(response['message']['content'],
                    context_for(case, 'complete')) == row['verdict'], 'Historical decode mismatch')
        if decomposed:
            if row.get('verdict'):
                response = row['response']['choices'][0]
                require(response['finish_reason'] == 'stop', 'Successful truncated response')
                evidence = Evidence.model_validate(json.loads(response['message']['content'])).model_dump()
                require(evidence == row['evidence'], 'Raw evidence mismatch')
                verdict, computed = decide(evidence, context_for(case, 'complete'))
                require(verdict == row['verdict'] and computed == row['computed_value'], 'Decision replay mismatch')
            require(row['model_calls'] == 1 and row['stages'][0]['stage'] == 'evidence'
                    and row['stages'][0]['messages'] == row['messages'], 'Evidence-stage provenance mismatch')
    return rows, manifest


def paired_differences(baseline, revised, gold):
    result = {}
    for model in MODELS:
        for protocol in ('original', 'evidence'):
            old = {r['case_id']: r for r in baseline if r['model'] == model and r['prompt'] == protocol}
            new = {r['case_id']: r for r in revised if r['model'] == model}
            families = defaultdict(list)
            gained = lost = 0
            for cid, case in gold.items():
                before = old[cid].get('verdict', {}).get('status') == case['expected']
                after = new[cid].get('verdict', {}).get('status') == case['expected']
                families[case['family']].append(int(after) - int(before))
                gained += after and not before
                lost += before and not after
            means = [sum(values) / len(values) for _, values in sorted(families.items())]
            rng = random.Random(42)
            samples = sorted(sum(rng.choices(means, k=len(means))) / len(means) for _ in range(1000))
            result[f'{model} | {protocol}'] = {'difference': sum(means) / len(means),
                'family_bootstrap_95_interval': [samples[24], samples[974]], 'gained_cases': gained,
                'lost_cases': lost, 'per_family_difference': {f: sum(v) / len(v) for f, v in families.items()}}
    return result


def build_report(baseline, revised, gold, provenance):
    summaries = summarize(baseline + revised)
    paired = paired_differences(baseline, revised, gold)
    lines = ['# Decomposed development study', '',
        'Exploratory comparison on the same 48 synthetic development cases per model. Errors and abstentions '
        'remain in all accuracy denominators. The always-PASS baseline is 24/48. No held-out results are used.', '',
        '| Model | Protocol | Correct / 48 | Errors | Abstentions | Mean seconds/case |',
        '|---|---|---:|---:|---:|---:|']
    for key, value in summaries.items():
        model, protocol, _ = key.split(' | ')
        lines.append(f'| {model} | {protocol} | {value["exact_matches"]}/48 | '
                     f'{sum(value["errors"].values())} | {value["verdicts"].get("ABSTAIN", 0)} | {value["mean_seconds"]:.2f} |')
    lines += ['', '## Paired changes', '',
              '| Model | Compared with | Difference (percentage points) | Family-bootstrap 95% interval | Gained | Lost |',
              '|---|---|---:|---|---:|---:|']
    for key, value in paired.items():
        model, protocol = key.split(' | ')
        lo, hi = value['family_bootstrap_95_interval']
        lines.append(f'| {model} | {protocol} | {100*value["difference"]:.1f} | '
                     f'{100*lo:.1f} to {100*hi:.1f} | {value["gained_cases"]} | {value["lost_cases"]} |')
    lines += ['', 'Intervals resample eight development families (1,000 draws; seed 42), not independent training runs. '
              'They are descriptive and do not establish generalization or confirmatory significance.', '', '## Category and class results', '']
    for key, value in summaries.items():
        lines += [f'### {key}', '', '| Category | Correct / attempts |', '|---|---:|']
        lines += [f'| {cat} | {v["matches"]}/{v["attempts"]} |' for cat, v in value['per_category'].items()]
        lines += ['', '| Class | Support | Predicted | Precision | Recall |', '|---|---:|---:|---:|---:|']
        fmt = lambda x: 'N/A' if x is None else f'{x:.3f}'
        lines += [f'| {c} | {v["support"]} | {v["predicted"]} | {fmt(v["precision"])} | {fmt(v["recall"])} |'
                  for c, v in value['per_class'].items()]
        lines.append('')
    unique_payloads = len({json.dumps(context_for(c, 'complete'), sort_keys=True) for c in gold.values()})
    calls = sum(r['model_calls'] for r in revised)
    lines += ['## Cost, provenance, and limits', '',
        f'- There are {unique_payloads} unique full-context payloads among 48 cases. Each family’s missing/future pair '
        'has identical admissible input; these are not 48 independent tasks or separate missing/future capabilities.',
        f'- Added inference calls: {calls}; historical comparison calls: {len(baseline)}. The decomposed method uses '
        'one evidence-generation call and deterministic decision processing per case, with no correction retries.',
        f'- Added summed case latency: {sum(r["seconds"] for r in revised):.2f} seconds. '
        'Per-protocol mean latency above is observed local time, not a controlled speed benchmark.',
        '- Historical baselines are noncontemporaneous. Hardware load, runtime, and scheduling may differ; no causal speed claim is supported.',
        '- The old model listing records names and timestamps, not model weight digests. Matching listings cannot prove identical weights.',
        '- Model dependency extraction and substitutions are not formally verified; a valid integer expression can still misrepresent supplied definitions.',
        '- The revised method adds a deterministic arithmetic component; any gain measures the combined pipeline, not improved LLM judgment alone.',
        '- Development cases and their prior failures informed this intervention. This is an exploratory development result; '
        'a fresh passing gate and separate evaluation are required before any generalization claim.',
        '- The original prompt baseline was adapted to the shared evidence-output contract.',
        f'- Baseline run: `{provenance["baseline"]}`; revised run: `{provenance["revised"]}`.',
        '- Source snapshot, prediction hashes, frozen development data, payloads, and matched case sets were checked. '
        'Full manifests and their hashes are retained in analysis.json.', '']
    return '\n'.join(lines), {'summary': summaries, 'paired_differences': paired, 'added_calls': calls, 'unique_payloads': unique_payloads, 'provenance': provenance}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--baseline', required=True, type=Path)
    parser.add_argument('--revised', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    benchmark = json.loads((DEST / 'manifest.json').read_text())
    require(sha(DEST / 'development.json') == benchmark['files']['development.json'], 'Development data hash mismatch')
    gold = {c['id']: c for c in json.loads((DEST / 'development.json').read_text())}
    baseline, bm = read_run(args.baseline, gold, benchmark)
    revised, rm = read_run(args.revised, gold, benchmark, True)
    # Old metadata cannot prove weight identity; nevertheless changed listings must not silently pass.
    identity = lambda m: {x['id']: x for x in m['model_metadata']['data'] if x['id'] in MODELS}
    require(identity(bm) == identity(rm), 'Historical model listing differs; investigate before comparison')
    provenance = {'baseline': str(args.baseline.resolve()), 'revised': str(args.revised.resolve()),
                  'baseline_manifest': bm, 'revised_manifest': rm,
                  'baseline_manifest_sha256': sha(args.baseline / 'manifest.json'),
                  'revised_manifest_sha256': sha(args.revised / 'manifest.json')}
    report, analysis = build_report(baseline, revised, gold, provenance)
    args.output.mkdir(parents=True, exist_ok=False)
    (args.output / 'RESULTS.md').write_text(report)
    (args.output / 'analysis.json').write_text(json.dumps(analysis, indent=2))
    print(args.output / 'RESULTS.md')


if __name__ == '__main__':
    main()
