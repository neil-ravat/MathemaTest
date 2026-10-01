"""Offline source-guard replay of complete saved development and fixture results."""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.controlled_benchmark import DEST, digest
from scripts.report_decomposed_study import read_run, require, sha
from scripts.run_controlled_study import MODELS, context_for, gate_cases, summarize
from scripts.run_decomposed_study import Evidence, decide, error_fields


def replay_original(row, payload):
    """Reconstruct saved successes and failures without any model calls."""
    if 'response' not in row:
        require(row.get('error_type') == 'runtime_or_truncation' and row.get('error'), 'Unexplained missing response')
        return  # A transport failure cannot be regenerated offline.
    try:
        choice = row['response']['choices'][0]
        if choice['finish_reason'] != 'stop':
            raise ValueError('Truncated response')
        evidence = Evidence.model_validate(json.loads(choice['message']['content'])).model_dump()
        verdict, computed = decide(evidence, payload)
    except Exception as exc:
        require(row.get('error_type') == error_fields(exc)['error_type'] and not row.get('verdict'),
                'Historical failure replay mismatch')
    else:
        require(not row.get('error_type') and row['evidence'] == evidence
                and row['verdict'] == verdict and row['computed_value'] == computed, 'Historical success replay mismatch')


def read_inputs(development, gate):
    benchmark = json.loads((DEST / 'manifest.json').read_text())
    require(sha(DEST / 'development.json') == benchmark['files']['development.json'], 'Development hash mismatch')
    cases = {'development': {c['id']: c for c in json.loads((DEST / 'development.json').read_text())},
             'gate': {c['id']: c for c in gate_cases()}}
    dev, dm = read_run(development, cases['development'], benchmark, True)
    gm = json.loads((gate / 'manifest.json').read_text())
    complete = json.loads((gate / 'COMPLETE.json').read_text())
    require(complete['predictions_sha256'] == sha(gate / 'predictions.jsonl'), 'Gate prediction hash mismatch')
    fixtures = [json.loads(line) for line in (gate / 'predictions.jsonl').read_text().splitlines()]
    require(gm['phase'] == 'gate' and gm['case_count'] == 7, 'Wrong gate scope')
    for field in ('arms', 'prompts', 'models', 'code_hash', 'source_sha256', 'requirements_sha256',
                  'benchmark_manifest_hash', 'model_metadata', 'prompt_texts', 'temperature', 'seed', 'max_tokens'):
        require(gm[field] == dm[field], f'Gate/development protocol mismatch: {field}')
    model_digests = lambda m: {r['name']: r['digest'] for r in m['ollama_tags']['models'] if r['name'] in MODELS}
    require(set(model_digests(dm)) == set(MODELS) and model_digests(gm) == model_digests(dm), 'Model digest mismatch')
    require(all(sha(gate / 'source_snapshot' / p) == h for p, h in gm['source_sha256'].items()), 'Gate snapshot mismatch')
    require(sha(gate / 'requirements-local.lock.txt') == gm['requirements_sha256'], 'Gate dependency mismatch')
    require(len(fixtures) == complete['rows'] == complete['calls'] == 14 and
            {(r['model'], r['case_id'], r['prompt'], r['arm']) for r in fixtures} ==
            {(m, cid, 'decomposed', 'complete') for m in MODELS for cid in cases['gate']}, 'Incomplete or duplicate gate records')
    for phase, rows in [('development', dev), ('gate', fixtures)]:
        for row in rows:
            case = cases[phase][row['case_id']]
            payload = context_for(case, 'complete')
            require(all(row[k] == case[k] for k in ('family', 'category', 'expected')), 'Case metadata mismatch')
            require(row['messages'] == [{'role': 'system', 'content': dm['prompt_texts']['decomposed']},
                    {'role': 'user', 'content': json.dumps(payload)}], 'Original prompt/payload mismatch')
            require(row['model_calls'] == 1 and row['context_complete'] and row['future_items'] == 0,
                    'Original context/call mismatch')
            replay_original(row, payload)
    return {'development': dev, 'gate': fixtures}, cases


def guarded_row(row, payload):
    from src.verification.source_guard import guard_evidence
    result = {k: row[k] for k in ('case_id', 'family', 'category', 'expected', 'model', 'arm', 'future_items')}
    result.update(prompt='source_guard', original_status=row.get('verdict', {}).get('status'),
                  original_error_type=row.get('error_type'), model_calls=0, accepted=False, original_seconds=row['seconds'])
    started = time.monotonic()
    if row.get('error_type'):
        result.update(error_type=row['error_type'], error=row['error'], rejection_reason='historical_error')
    else:
        guard = guard_evidence(row['evidence'], payload)
        require(not guard['accepted'] or guard['verdict']['status'] == row['verdict']['status'], 'Guard changed an accepted label')
        require(guard['accepted'] or guard['verdict']['status'] == 'ABSTAIN', 'Guard repaired a rejected answer')
        result.update(guard)
    result['seconds'] = time.monotonic() - started
    return result


def metrics(rows):
    stats = summarize(rows)
    for model in MODELS:
        selected = [r for r in rows if r['model'] == model]
        accepted = [r for r in selected if r['accepted']]
        accepted_correct = sum(r['verdict']['status'] == r['expected'] for r in accepted)
        wrong_withheld = sum(r['original_status'] in ('PASS', 'FAIL_GAP', 'FAIL_LOGIC') and r['original_status'] != r['expected']
                             and not r['accepted'] for r in selected)
        correct_withheld = sum(r['original_status'] == r['expected'] and not r['accepted'] for r in selected)
        key = f'{model} | source_guard | complete'
        stats[key].update({'guard_attempts': sum(r['original_error_type'] is None for r in selected),
            'guard_attempt_coverage_all_cases': sum(r['original_error_type'] is None for r in selected) / len(selected),
            'accepted_count': len(accepted), 'accepted_coverage_all_cases': len(accepted) / len(selected),
            'conditional_accuracy_accepted': accepted_correct / len(accepted) if accepted else None,
            'accepted_correct': accepted_correct, 'wrong_answers_withheld': wrong_withheld,
            'correct_labels_withheld': correct_withheld,
            'rejection_reasons': dict(Counter(r['rejection_reason'] for r in selected if not r['accepted']))})
        families = defaultdict(list)
        for r in selected:
            families[r['family']].append(int(r.get('verdict', {}).get('status') == r['expected'])
                                          - int(r['original_status'] == r['expected']))
        means = [sum(v)/len(v) for _, v in sorted(families.items())]
        rng = random.Random(42)
        draws = sorted(sum(rng.choices(means, k=len(means)))/len(means) for _ in range(1000))
        stats[key]['paired_exact_match_difference'] = sum(means)/len(means)
        stats[key]['paired_family_bootstrap_95_interval'] = [draws[24], draws[974]]
    return stats


def build_report(originals, guarded, baseline):
    output = {}
    lines = ['# Offline source-guard replay', '',
        'This post-hoc development experiment makes zero new model calls. The guard may retain a previously valid '
        'answer or withhold it as ABSTAIN. Historical errors remain errors; no answer is repaired using the source baseline.', '']
    for phase in ('development', 'gate'):
        old = summarize(originals[phase]); new = metrics(guarded[phase])
        output[phase] = {'unguarded': old, 'guarded': new}
        lines += [f'## {phase.title()}', '',
                  '| Model | Original correct/all | Guarded correct/all | Guard attempts | Accepted/all | Correct/accepted | Wrong withheld | Correct withheld |',
                  '|---|---:|---:|---:|---:|---:|---:|---:|']
        intervals = []
        for model in MODELS:
            a = old[f'{model} | decomposed | complete']; b = new[f'{model} | source_guard | complete']
            conditional = f'{b["accepted_correct"]}/{b["accepted_count"]}' if b['accepted_count'] else 'N/A (0 accepted)'
            lines.append(f'| {model} | {a["exact_matches"]}/{a["attempts"]} | {b["exact_matches"]}/{b["attempts"]} | '
                         f'{b["guard_attempts"]} | {b["accepted_count"]}/{b["attempts"]} | {conditional} | '
                         f'{b["wrong_answers_withheld"]} | {b["correct_labels_withheld"]} |')
            if phase == 'development':
                lo, hi = b['paired_family_bootstrap_95_interval']
                intervals += ['', f'{model}: guarded minus original exact match {100*b["paired_exact_match_difference"]:.1f} '
                          f'percentage points; paired family-bootstrap interval {100*lo:.1f} to {100*hi:.1f}.', '']
        lines += intervals
        lines += ['', 'Errors and abstentions remain in the primary denominator. Guard attempts exclude historical errors; '
                  'accepted coverage uses all cases. Conditional accuracy applies only to accepted outputs.', '']
        for model in MODELS:
            b = new[f'{model} | source_guard | complete']
            lines += [f'### {model}', '', '| Category | Guarded correct/all |', '|---|---:|']
            lines += [f'| {c} | {v["matches"]}/{v["attempts"]} |' for c, v in b['per_category'].items()]
            lines += ['', '| Class | Support | Predicted | Precision | Recall |', '|---|---:|---:|---:|---:|']
            fmt = lambda x: 'N/A' if x is None else f'{x:.3f}'
            lines += [f'| {c} | {v["support"]} | {v["predicted"]} | {fmt(v["precision"])} | {fmt(v["recall"])} |'
                      for c, v in b['per_class'].items()]
            lines += ['', 'Rejection reasons: ' + json.dumps(b['rejection_reasons'], sort_keys=True) + '.', '']
    lines += ['## Standalone source baseline and limits', '', '| Dataset | Correct/all | Supported/all |', '|---|---:|---:|']
    baseline_summary = {}
    for phase in ('development', 'gate'):
        rows = [r for r in baseline if r['phase'] == phase]
        value = {'cases': len(rows), 'correct': sum(r['source']['source_status'] == r['expected'] for r in rows),
                 'supported': sum(r['source']['supported'] for r in rows)}
        baseline_summary[phase] = value
        lines.append(f'| {phase} | {value["correct"]}/{value["cases"]} | {value["supported"]}/{value["cases"]} |')
    lines += ['', 'The baseline reads public target/definitions only and runs once per case: 48 development cases plus '
        '7 public fixtures, not duplicated per model. It is a narrow grammar interpreter designed after inspecting these tasks. '
        'Strong performance demonstrates that this grammar can be solved symbolically; it establishes no added LLM value.', '',
        'The guard verifies restricted dependency, substitution-structure, and citation consistency. It is not a formal proof '
        'checker for general mathematics or a validated textbook auditor. Unsupported source grammar is withheld.', '',
        'Development contains eight families and only 40 distinct full-context inputs among 48 cases. Missing/future pairs '
        'share admissible input. Development intervals resample families 1,000 times with seed 42; they are descriptive, '
        'not confirmatory. Fixture results are a diagnostic replay, not a fresh inference gate or held-out generalization test.', '',
        'All old prompts, source snapshots, model metadata/digests, input payloads and completed-run hashes are checked; '
        'raw responses are replayed through the historical decoder/decision rule. Saved transport failures can only be '
        'preserved, not regenerated offline. Row seconds measure guard-only processing; original_seconds preserves '
        'historical inference latency. Conditional accepted-only accuracy is not full-dataset accuracy.', '']
    output['source_baseline'] = baseline_summary
    return '\n'.join(lines), output


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--development', required=True, type=Path)
    parser.add_argument('--gate', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    originals, cases = read_inputs(args.development, args.gate)
    from src.verification.source_guard import source_analysis
    guarded = {phase: [guarded_row(r, context_for(cases[phase][r['case_id']], 'complete')) for r in rows]
               for phase, rows in originals.items()}
    baseline = [{'phase': phase, 'case_id': c['id'], 'expected': c['expected'],
                 'source': source_analysis(context_for(c, 'complete'))}
                for phase, group in cases.items() for c in group.values()]
    report, analysis = build_report(originals, guarded, baseline)
    sources = ['scripts/replay_source_guard.py', 'src/verification/source_guard.py',
               'scripts/report_decomposed_study.py', 'scripts/run_decomposed_study.py',
               'scripts/run_controlled_study.py', 'scripts/controlled_benchmark.py',
               'scripts/run_local_pilot.py', 'src/verification/verdicts.py',
               'docs/source_guard_protocol.md', 'requirements-local.lock.txt']
    hashes = {p: sha(ROOT / p) for p in sources}
    manifest = {'protocol': 'source_guard_replay_v1', 'new_model_calls': 0, 'source_sha256': hashes,
                'code_hash': digest(hashes), 'development_data_sha256': sha(DEST / 'development.json'),
                'inputs': {phase: {'path': str(path.resolve()), 'manifest_sha256': sha(path/'manifest.json'),
                                  'predictions_sha256': sha(path/'predictions.jsonl'), 'complete_sha256': sha(path/'COMPLETE.json')}
                           for phase, path in [('development', args.development), ('gate', args.gate)]}}
    args.output.mkdir(parents=True, exist_ok=False)
    for path in sources:
        target = args.output / 'source_snapshot' / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((ROOT / path).read_bytes())
    records = [{**r, 'phase': phase} for phase, rows in guarded.items() for r in rows]
    (args.output/'guarded_predictions.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records))
    (args.output/'source_baseline.json').write_text(json.dumps(baseline, indent=2))
    (args.output/'analysis.json').write_text(json.dumps(analysis, indent=2))
    (args.output/'manifest.json').write_text(json.dumps(manifest, indent=2))
    (args.output/'RESULTS.md').write_text(report)
    (args.output/'COMPLETE.json').write_text(json.dumps({'rows': len(records), 'new_model_calls': 0,
        'files': {p: sha(args.output/p) for p in ('guarded_predictions.jsonl','source_baseline.json','analysis.json','manifest.json','RESULTS.md')}}, indent=2))
    print(args.output/'RESULTS.md')


if __name__ == '__main__':
    main()
