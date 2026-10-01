"""Build a traceable development report from completed, explicitly selected runs."""
import argparse
from collections import defaultdict
import hashlib
import json
from pathlib import Path
import random
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.controlled_benchmark import DEST
from scripts.run_controlled_study import MODELS, summarize


def read_completed(path, phase, count):
    manifest=json.loads((path/'manifest.json').read_text())
    raw=(path/'predictions.jsonl').read_bytes()
    complete=json.loads((path/'COMPLETE.json').read_text())
    assert manifest['phase']==phase
    assert hashlib.sha256(raw).hexdigest()==complete['predictions_sha256']
    rows=[json.loads(line) for line in raw.splitlines()]
    assert len(rows)==complete['calls']==count
    assert len({(r['model'],r['prompt'],r['arm'],r['case_id']) for r in rows})==count
    return rows


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--gate',type=Path,required=True)
    parser.add_argument('--development',type=Path,required=True)
    parser.add_argument('--retrieval',type=Path,required=True)
    args=parser.parse_args()
    gate=read_completed(args.gate,'gate',28)
    rows=read_completed(args.development,'development',192)
    gold={c['id']:c for c in json.loads((DEST/'development.json').read_text())}
    assert all(r['expected']==gold[r['case_id']]['expected'] and r['context_complete'] for r in rows)
    audit=json.loads(args.retrieval.read_text())
    summary=summarize(rows)
    assert len(summary)==4 and all(s['attempts']==48 for s in summary.values())
    assert any(r['prompt']=='evidence' and r.get('verdict',{}).get('status')!=r['expected'] for r in gate), 'This report is specifically for the failed-gate development study'
    lines=['# Controlled study results', '',
           'The seven-fixture gate failed. The held-out evaluation was not authorized by these results. '
           'This report describes synthetic development data only; it supplies no educational-validity or publication-readiness claim.', '',
           '## Full-context verdict comparison', '',
           '| Model | Prompt | Correct / 48 | Invalid outputs | Abstentions | Family-bootstrap interval |',
           '|---|---|---:|---:|---:|---|']
    for key,s in summary.items():
        model,prompt,_=key.split(' | ')
        low,high=s['exact_match_family_bootstrap_95_interval']
        lines.append(f'| {model} | {prompt} | {s["exact_matches"]}/48 | {sum(s["errors"].values())} | {s["verdicts"].get("ABSTAIN",0)} | {100*low:.1f}%–{100*high:.1f}% |')
    lines += ['', 'All 48 cases were attempted for every model/prompt combination. Errors and abstentions remain in the denominator. '
              'The always-PASS baseline is 24/48 because three of six categories have PASS labels. '
              'Both prompts receive the same evidence-output contract. The original prompt is therefore an adapted baseline.', '',
              '## Paired prompt differences', '']
    paired={}
    for model in MODELS:
        groups=defaultdict(list)
        index={(r['case_id'],r['prompt']):r for r in rows if r['model']==model}
        for cid,c in gold.items():
            ok=lambda p: int(index[cid,p].get('verdict',{}).get('status')==c['expected'])
            groups[c['family']].append(ok('evidence')-ok('original'))
        means=[sum(v)/len(v) for v in groups.values()]
        rng=random.Random(42)
        samples=sorted(sum(rng.choices(means,k=len(means)))/len(means) for _ in range(1000))
        paired[model]={'difference':sum(means)/len(means),'family_bootstrap_95_interval':[samples[24],samples[974]]}
        lines.append(f'- {model}: revised minus original = {100*paired[model]["difference"]:.1f} percentage points; paired family-bootstrap interval {100*samples[24]:.1f} to {100*samples[974]:.1f}.')
    lines += ['', 'These exploratory intervals resample only eight development families, not model training runs. '
              'They do not establish generalization beyond the narrow generator.', '', '## Retrieval mechanics', '',
              '| Arm | Required passages recovered / available | Cases containing future passages |',
              '|---|---:|---:|']
    for arm,s in audit['summary'].items():
        lines.append(f'| {arm} | {s["recovered_required"]}/{s["available_required"]} | {s["future_context_cases"]}/48 |')
    lines += ['', 'These are retrieval-only checks, not end-to-end model scores. Repeated prerequisites across case variants are counted '
              'as case-specific occurrences, not unique passages. Future or absent definitions are excluded from available-prerequisite denominators. '
              'The graph uses explicit references; it shows no coverage advantage over the filtered vector method on this sample.', '',
              '## Gate and diagnosis', '']
    for key,s in summarize(gate).items():
        lines.append(f'- {key}: {s["exact_matches"]}/7 exact fixture verdicts.')
    lines += ['', 'Observed failures persist with complete earlier context. Some saved responses compute a correct equality or identify '
              'an absent definition but choose an incompatible verdict. These are not explained solely by retrieval coverage. '
              'Citation validation catches invalid IDs and inadmissible positions, not every semantic contradiction.', '',
              'Separate plain-arithmetic controls are retained alongside this report. Qwen returned the requested two integers. '
              'Mistral stated the correct sum in prose; its substitution response hit the shorter 40-token control limit and is inconclusive. '
              'These four controls are excluded from benchmark metrics.', '',
              '## Provenance and next decision', '',
              f'- Gate records: `{args.gate}`.', f'- Development records: `{args.development}`.',
              f'- Retrieval records: `{args.retrieval}`.',
              '- Every run retains prompts, model responses, source provenance, and failures. The development run includes 192 calls, '
              'the gate 28, and the plain controls 4: 224 local calls in this phase.',
              '- 83 offline regression tests passed. Restricted retrieval had zero future passages in all 48 development cases.',
              '- Latencies are observed local-call times, not isolated hardware benchmarks: short control calls and a CPU embedding audit '
              'overlapped parts of the run. Retrieval preparation is timed separately.',
              '- Do not promote these results into the manuscript as evidence of reliable auditing. The next bounded experiment should '
              'separate computation/evidence production from verdict selection and test a consistency check on development data. '
              'That is a proposed change, not a demonstrated fix.',
              '- Any changed protocol needs a fresh passing seven-fixture gate before the held-out phase. Human educational validation '
              'and broader mathematical coverage remain outside this synthetic study.', '']
    out=ROOT/'artifacts/controlled_study'
    with (out/'RESULTS.md').open('x') as f:f.write('\n'.join(lines))
    with (out/'analysis.json').open('x') as f:json.dump({'development':summary,'paired_differences':paired,
        'gate':summarize(gate),'heldout_started':(DEST/'HELDOUT_STARTED.json').exists()},f,indent=2)
    print(out/'RESULTS.md')


if __name__=='__main__':
    main()
