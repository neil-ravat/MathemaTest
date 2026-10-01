"""Six fresh synthetic audit controls, frozen before local inference; no expert gold."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_curriculum_audit as transport
from src.verification.curriculum_audit import audit_curriculum

BACKGROUND='Rational arithmetic, multiplication, division, substitution of stated numbers into a supplied formula, elementary algebra, and ordinary reading comprehension. No subject-specific definitions or formulas are granted without source or target evidence.'


def cases():
    families=[('math',
        'A weighted mean combines numerical values using specified positive weights.',
        'For two values a and b with positive weights u and v, the weighted mean is (u*a + v*b)/(u+v). Multiply each value by its weight, add the products, then divide by the sum of the weights.',
        'Find the weighted mean of 4 and 12 with respective weights 1 and 3.',
        'Find the weighted mean of 4 and 12. The weight of 4 is 1; the positive weight of 12 has not been specified.',
        'weighted mean definition and calculation',10),
        ('physics',
        'This lesson concerns uniform pressure exerted normally on a surface. Force is measured in newtons and area in square metres.',
        'For a force F acting normally and uniformly over a contact area A, pressure is p = F/A. Divide force in newtons by contact area in square metres to obtain pressure in pascals.',
        'A force of 72 newtons acts normally and uniformly over a contact area of 9 square metres. Find the pressure in pascals.',
        'A force of 72 newtons acts normally and uniformly over a surface. Its contact area is not specified. Find the pressure in pascals.',
        'pressure definition and calculation',8)]
    result=[]
    for family,intro,rule,target,ambiguous,concept,answer in families:
        for kind in ('supported','omitted_rule','missing_task_fact'):
            case_id=f'{family}-{kind}';source='synthetic-'+case_id
            def row(identifier,text,position,role='exposition'):
                return dict(id=identifier,content=text,position=position,source_id=source,module_id=source,
                            kind='exercise' if role=='exercise_material' else 'para',instructional_role=role)
            records=[row('intro',intro,0)]
            if kind!='omitted_rule':records.append(row('rule',rule,1))
            t=row('target',ambiguous if kind=='missing_task_fact' else target,3,'exercise_material')
            records.append(t)
            result.append(dict(id=case_id,subject=family,condition=kind,records=records,target=t,background=BACKGROUND,
                expected_status='MODEL_SUPPORTED' if kind=='supported' else 'REVIEW_REQUIRED',
                expected_reason=concept if kind=='omitted_rule' else ('Unspecified weight or contact area prevents a unique answer.' if kind=='missing_task_fact' else 'All rules and values are explicitly supplied.'),
                reference_answer=answer if kind=='supported' else None,
                scope='Author-constructed complete mini-lesson. Expected audit behavior, not independently reviewed textbook labels.'))
    return result


def summarize(plan,results):
    pairs=list(zip(plan,results));supported=[(c,r) for c,r in pairs if c['condition']=='supported'];other=[(c,r) for c,r in pairs if c['condition']!='supported']
    return dict(planned=len(plan),attempted=len(results),
        all_stages_returned=sum(len(r['calls'])==3 and all('response' in x for x in r['calls']) for r in results),
        expected_status_matches=sum(c['expected_status']==r['status'] for c,r in pairs),
        supported_controls_accepted=sum(r['status']=='MODEL_SUPPORTED' for c,r in supported),
        supported_controls_review_required=sum(r['status']=='REVIEW_REQUIRED' for c,r in supported),
        unsafe_support_on_omitted_or_ambiguous=sum(r['status']=='MODEL_SUPPORTED' for c,r in other),
        appropriate_review_status=sum(r['status']=='REVIEW_REQUIRED' for c,r in other),
        errors=sum(r['status'] not in ('MODEL_SUPPORTED','REVIEW_REQUIRED') for r in results),
        cases=[dict(id=c['id'],expected=c['expected_status'],actual=r['status'],seconds=r.get('seconds'),
                    reviewer_grounding_valid=r.get('reviewer_grounding_valid'),error=r.get('error'),
                    reviewer_grounding_error=r.get('reviewer_grounding_error')) for c,r in pairs],
        unattempted=[c['id'] for c in plan[len(results):]],pedagogical_accuracy=None,independent_labels=False,
        limitation='Status matches alone do not demonstrate correct prerequisite or gap identification. Review rationale separately; no direct-model, vector/graph ablation or PDF extraction measured.')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--time-budget-seconds',type=int,default=900);p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    if args.time_budget_seconds<=0:p.error('Positive budget required')
    run=args.output;run.mkdir(parents=True,exist_ok=False);plan=cases()
    assert len(plan)==6 and {c['subject'] for c in plan}=={'math','physics'}
    assert (1*4+3*12)/(1+3)==10 and 72/9==8
    for c in plan:
        assert any(r['id']=='rule' for r in c['records'])==(c['condition']!='omitted_rule')
    hashes={}
    for path in (ROOT/'src/verification/curriculum_audit.py',ROOT/'scripts/run_curriculum_audit.py',Path(__file__).resolve()):
        name=str(path.relative_to(ROOT));dest=run/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest);hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    manifest=dict(created=datetime.now(timezone.utc).isoformat(),scope='Fresh author-constructed local development controls; not independent gold',plan=plan,source_hashes=hashes,
                  producer='qwen2.5-coder:7b',reviewer='mistral:latest',endpoint=transport.ollama_base_url(),time_budget_seconds=args.time_budget_seconds,temperature=0,seed=42,context_tokens=16384,retries=0)
    manifest_path=run/'manifest.json';manifest_path.write_text(json.dumps(manifest,indent=2));manifest_hash=hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    if args.prepare_only:print('Prepared only',run);return
    for endpoint in ('tags','version'):
        with urlopen(transport.ollama_base_url()+'/api/'+endpoint,timeout=10) as response:(run/f'ollama-{endpoint}.json').write_bytes(response.read())
    transport.DEADLINE=time.monotonic()+args.time_budget_seconds
    transport.REQUEST_TIMEOUT_SECONDS=180
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=transport.local_completion)))
    results=[];print('RUN',run,flush=True)
    try:
        for i,case in enumerate(plan,1):
            if time.monotonic()>=transport.DEADLINE:break
            def checkpoint(value):
                temp=run/f'{i:02}.tmp';temp.write_text(json.dumps(value,indent=2));temp.replace(run/f'{i:02}.json')
            started=time.monotonic()
            result=audit_curriculum(client,manifest['producer'],manifest['reviewer'],case['records'],case['target'],case['background'],checkpoint=checkpoint)
            result.update(seconds=round(time.monotonic()-started,2),control_id=case['id']);checkpoint(result);results.append(result)
            (run/'summary.json').write_text(json.dumps(summarize(plan,results),indent=2))
            print(case['id'],result['status'],result['seconds'],flush=True)
            if result['status']=='INTERRUPTED' or 'timed out' in result.get('error','').lower() or 'TimeoutError' in result.get('error',''):break
    finally:
        summary=summarize(plan,results)
        summary['code_unchanged']=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in hashes.items())
        summary['manifest_unchanged']=hashlib.sha256(manifest_path.read_bytes()).hexdigest()==manifest_hash
        (run/'summary.json').write_text(json.dumps(summary,indent=2))
        if not summary['code_unchanged'] or not summary['manifest_unchanged']:raise ValueError('Frozen inputs changed')

if __name__=='__main__':main()
