"""Prepare and lock a paired exploratory comparison; never call a model here."""
import hashlib
import importlib.util
import json
from pathlib import Path
import random
import re
import shutil
import subprocess
import sys
from datetime import datetime,timezone

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_book_pilot import target_context
BASE=ROOT/'artifacts/six_improvements_20261001'


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False))


def exposures(root):
    ids=set();files=0
    def walk(v):
        if isinstance(v,dict):
            for k,x in v.items():
                if k in {'target_id','target_ids','case_id'}:
                    for value in x if isinstance(x,list) else [x]:
                        if isinstance(value,str) and re.match(r'm\d+:',value):ids.add(value)
                if k=='target' and isinstance(x,dict) and isinstance(x.get('id'),str):ids.add(x['id'])
                walk(x)
        elif isinstance(v,list):
            for x in v:walk(x)
    for artifact_root in [root/'artifacts',ROOT/'artifacts']:
        for path in artifact_root.rglob('*.json'):
            if any(p in {'source_snapshot','baseline','candidate_snapshot','six_improvements_20261001'} for p in path.parts):continue
            if path.stat().st_size>20_000_000:continue
            if not (path.name in {'plan.json','manifest.json','pending_cases.json'} or path.name.startswith('case')):continue
            try:walk(json.loads(path.read_text()));files+=1
            except (ValueError,OSError):continue
    return ids,files


def main():
    run=BASE/'fresh_comparison';run.mkdir(exist_ok=False)
    # Freeze candidate before selecting or inspecting the new textbook cases.
    hashes={}
    for folder in ['src','scripts']:
        for source in (ROOT/folder).rglob('*.py'):
            relative=source.relative_to(ROOT);dest=run/'candidate_snapshot'/relative
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(source,dest)
            hashes[str(relative)]=hashlib.sha256(source.read_bytes()).hexdigest()
    write(run/'candidate_code.json',hashes)
    # The preserved baseline renders the same pinned XML in its own interpreter.
    code=r'''
import sys,json,hashlib
from pathlib import Path
sys.path.insert(0,sys.argv[1])
from scripts.prepare_openstax import extract_module
from scripts.prepare_context_corpus import source_metadata
from scripts.run_book_pilot import target_context
source=Path(sys.argv[2]);dest=Path(sys.argv[3]);dest.mkdir(parents=True)
original=[json.loads(line) for line in (source/'corpus.jsonl').read_text().splitlines()]
modules={r['module_id']:r for r in original};rows=[]
for mid,meta in sorted(modules.items(),key=lambda pair:pair[1]['module_order']):
 path=source/'source/modules'/mid/'index.cnxml'
 extracted=extract_module(path,mid,meta['chapter'],meta['module_order'],len(rows));roles=source_metadata(path)
 for row in extracted:
  row.update({k:meta[k] for k in ['source_id','source_url','attribution','license']})
  row.update(roles.get(row['anchor'],{'instructional_role':'unknown'}))
 rows.extend(extracted)
(dest/'corpus.jsonl').write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in rows))
(dest/'targets.json').write_text(json.dumps(target_context(rows,source),ensure_ascii=False))
'''
    books=[('calculus',ROOT/'data/openstax_calculus_v1',BASE/'corpus_candidate'),
           ('physics',BASE/'physics_source',BASE/'physics_candidate')]
    exposed,files=exposures(ROOT.parents[1]);write(run/'exposure_audit.json',dict(files_scanned=files,excluded_target_ids=sorted(exposed),scope='Known local recorded target exposure only; pretraining and unrecorded exposure unknown'))
    rng=random.Random(20261002);plan=[];excluded=[]
    background='Arithmetic and elementary algebra are known. No subject-specific formulas are granted without source evidence.'
    for book,source,candidate in books:
        baseline=run/f'{book}_baseline'
        subprocess.run([sys.executable,'-c',code,str(BASE/'baseline'),str(source),str(baseline)],check=True,cwd=BASE/'baseline')
        candidate_rows=[json.loads(line) for line in (candidate/'corpus.jsonl').read_text().splitlines()]
        targets=target_context(candidate_rows,source)
        old={x['target']['id']:x for x in json.loads((baseline/'targets.json').read_text())}
        pool=[]
        for item in targets:
            target=item['target'];reasons=[]
            if target['id'] in exposed:reasons.append('Previously recorded target')
            if not 1<=target['chapter']<=3:reasons.append('Outside prespecified chapters 1--3')
            if not 25<=len(target['content'])<=1200:reasons.append('Outside prespecified target length 25--1200')
            if item['input_issues']:reasons.append('Text-only evaluation: input requires review')
            if target['id'] not in old:reasons.append('No matching baseline source anchor')
            if reasons:excluded.append(dict(book=book,id=target['id'],reasons=reasons))
            else:pool.append(item)
        pool.sort(key=lambda x:x['target']['id']);rng.shuffle(pool)
        if len(pool)<2:raise ValueError('Insufficient fresh text-only targets for '+book)
        for i,item in enumerate(pool[:2],1):
            target=item['target'];old_target=old[target['id']]['target']
            case_id=f'{book}-{i}'
            plan.append(dict(id=case_id,book=book,family=case_id,variant='original',source_target_id=target['id'],
                background=background,baseline_target=old_target,candidate_target=target,
                baseline_corpus=str(baseline/'corpus.jsonl'),candidate_corpus=str(candidate/'corpus.jsonl'),
                original_source_manifest=str(source/'manifest.json')))
        # A prespecified source-ablation control for the first selected family.
        # Removing prior instruction is NOT a claim that the original book has a gap.
        first=plan[-2]
        plan.append(dict(first,id=first['id']+'-no-instruction',variant='no_prior_instruction'))
    write(run/'selection_exclusions.json',excluded)
    write(run/'plan.json',plan)
    write(run/'reference_review.json',[dict(case_id=c['id'],reference_status='UNREVIEWED',necessary_prerequisites=[],source_evidence=[],rationale='',reviewer='Assistant; provisional, not independent expert ground truth') for c in plan])
    write(run/'protocol.json',dict(created=datetime.now(timezone.utc).isoformat(),seed=20261002,
        planned_cases=len(plan),families=4,books=2,paired_arms=['baseline','candidate'],
        selection='Two unused text-only targets per book from chapters 1--3, uniform seeded shuffle; first family also has a no-prior-instruction source ablation',
        source_identity='Same original XML source anchors and learner background; each arm uses its own frozen extraction/eligibility workflow',
        background=background,model='openai/gpt-oss-120b',temperature=0,seed_inference=42,
        transport='Configured Groq API only; no GPU rental, local GPU, paid fallback or model download',
        request_capacity_estimate=7600,max_output_tokens=4096,reasoning_effort='low',
        retries='One provider rate/schema retry; candidate also has one recorded completion-length retry. Baseline has its original no-completion-retry policy.',
        arm_order='Alternate baseline/candidate first by case; related ablations stay in their source family',
        labels='Assistant source review before model outputs; provisional, not independent educational validity',
        metrics=['provisional_reference_status_agreement','supported_case_acceptance','false_review_on_supported','unsupported_acceptance','valid_judgment_rate','errors','unattempted','prompt_tokens','completion_tokens','request_count','elapsed_seconds'],
        analysis='Retain all selected cases. Never credit ERROR as a successful abstention. Report paired outcomes and denominators; no pooled accuracy, significance or population generalization claim.',
        freeze='Candidate code is already copied. Freeze reviewed references, source corpora, plan, runner and transport before inference; run from snapshots. Do not repair or replace cases within the run.'))
    print('Prepared',len(plan),'cases across two books. Reference review and inference lock remain; no model calls.')


if __name__=='__main__':main()
