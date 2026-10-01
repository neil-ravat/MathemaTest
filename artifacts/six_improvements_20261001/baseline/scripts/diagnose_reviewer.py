"""Bounded matched-format diagnostics; no pedagogical accuracy claims."""
import argparse
from collections import defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_curriculum_audit import ollama_base_url
from src.verification.curriculum_audit import CHALLENGE, GroundedChallenge, Assessment, review_request, validate_review, curriculum_status

ARITHMETIC_SCHEMA=dict(type='object',additionalProperties=False,properties=dict(x=dict(type='integer'),prerequisites=dict(type='array',items=dict(type='string'),minItems=1,maxItems=3)),required=['x','prerequisites'])
FACT_SCHEMA=dict(type='object',additionalProperties=False,properties=dict(present=dict(type='boolean'),quote=dict(type='string',maxLength=240)),required=['present','quote'])

def build_plan(originals):
    plan=[]
    facts=[('axis','Rotate the region around the line x=2.','The axis of rotation','x=2'),('time','The time t is measured in seconds.','The unit of time','seconds'),('rate','Use a conversion rate of 7 tokens per unit.','The conversion rate','7 tokens per unit')]
    for model in ('mistral:latest','qwen2.5-coder:7b'):
        for mode in ('unconstrained','json','schema'):
            for i,(a,b,x) in enumerate(((2,5,6),(3,-4,9),(5,7,-2),(4,-3,0))):
                prompt=f'Solve {a}*x + ({b}) = {a*x+b}. Return x and at most three necessary prerequisite skills in the requested JSON.'
                plan.append(dict(id=f'{model}/{mode}/algebra-{i}',category='arithmetic',model=model,mode=mode,messages=[dict(role='user',content=prompt)],schema=ARITHMETIC_SCHEMA,expected=x,max_tokens=256))
        for mode in ('unconstrained','schema'):
            for name,sentence,fact,needle in facts:
                for present in (True,False):
                    context=sentence if present else 'Complete the exercise using the information supplied.'
                    prompt=f'Context: {context}\nIs this fact explicitly supplied: {fact}? Return JSON with present (boolean) and quote (the exact sentence supplying it, or an empty string if absent). Use only the context.'
                    plan.append(dict(id=f'{model}/{mode}/{name}-{present}',category='fact_presence',model=model,mode=mode,messages=[dict(role='user',content=prompt)],schema=FACT_SCHEMA,expected=present,context=context,needle=needle,max_tokens=256))
        for path in originals:
            saved=json.loads(path.read_text());prior=next(c for c in saved['calls'] if c['stage']=='challenge')
            task,schema=review_request(json.loads(prior['messages'][1]['content']))
            plan.append(dict(id=f'{model}/schema/review-{path.stem}',category='review_replay',model=model,mode='schema',messages=[dict(role='system',content=CHALLENGE),dict(role='user',content=json.dumps(task))],schema=schema,payload=task,assessment=saved['assessment'],max_tokens=2200,input_sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
    return plan

def request_body(case):
    body=dict(model=case['model'],stream=False,keep_alive='2m',messages=case['messages'],options=dict(temperature=0,seed=42,num_ctx=16384,num_predict=case['max_tokens']))
    if case['mode']=='json':body['format']='json'
    elif case['mode']=='schema':body['format']=case['schema']
    return body

def score(case,raw):
    if raw.get('done_reason')!='stop' or raw.get('prompt_eval_count',16384)+case['max_tokens']>16384:
        return dict(complete=False,format_valid=False,correct=False,error='Incomplete output or exhausted context')
    try:
        value=json.loads(raw['message']['content'])
    except (ValueError,KeyError,TypeError) as exc:
        return dict(complete=True,format_valid=False,correct=False,error=str(exc))
    if not isinstance(value,dict):return dict(complete=True,format_valid=False,correct=False,error='Expected object')
    if case['category']=='arithmetic':
        valid=(set(value)=={'x','prerequisites'} and type(value['x']) is int and isinstance(value['prerequisites'],list) and 1<=len(value['prerequisites'])<=3 and all(isinstance(s,str) for s in value['prerequisites']))
        correct=type(value.get('x')) is int and value['x']==case['expected']
        return dict(complete=True,format_valid=valid,answer=value.get('x'),answer_correct=correct,correct=valid and correct)
    if case['category']=='fact_presence':
        valid=(set(value)=={'present','quote'} and type(value['present']) is bool and isinstance(value['quote'],str) and len(value['quote'])<=240)
        grounded=valid and (value['quote'] in case['context'] and case['needle'] in value['quote'] if case['expected'] else value['quote']=='')
        return dict(complete=True,format_valid=valid,correct=bool(grounded and value['present']==case['expected']),answer=value)
    result=dict(complete=True,format_valid=False,grounding_valid=False,status='REVIEW_REQUIRED',correct=None)
    try:
        review=GroundedChallenge.model_validate(value);result.update(format_valid=True,challenge=review.model_dump())
        validate_review(review,case['payload'])
        result.update(grounding_valid=True,status=curriculum_status(Assessment(**case['assessment']),review,grounding_valid=True))
    except ValueError as exc:result['error']=str(exc)
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input',type=Path,required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--time-budget-seconds',type=int,default=660);p.add_argument('--prepare-only',action='store_true');args=p.parse_args()
    if args.time_budget_seconds<=0:p.error('Positive budget required')
    plan=build_plan([args.input/f'{i}.json' for i in (1,2)]);args.output.mkdir(parents=True,exist_ok=False)
    hashes={str(path.relative_to(ROOT)):hashlib.sha256(path.read_bytes()).hexdigest() for path in (Path(__file__),ROOT/'src/verification/curriculum_audit.py',ROOT/'scripts/run_curriculum_audit.py')}
    manifest=dict(scope='Exposed development diagnostics; not independent pedagogical evaluation',created=datetime.now(timezone.utc).isoformat(),plan=plan,source_hashes=hashes,time_budget_seconds=args.time_budget_seconds,retries=0,labels='Deterministic algebra and explicit fact presence; no gold labels for replays')
    (args.output/'manifest.json').write_text(json.dumps(manifest,indent=2))
    if args.prepare_only:print('Prepared',len(plan),'calls; no inference');return
    base=ollama_base_url();deadline=time.monotonic()+args.time_budget_seconds
    for endpoint in ('tags','version'):
        with urlopen(base+'/api/'+endpoint,timeout=20) as response:(args.output/f'ollama-{endpoint}.json').write_bytes(response.read())
    results=[]
    try:
        for i,case in enumerate(plan):
            remaining=deadline-time.monotonic()
            if remaining<=0:break
            body=request_body(case);out=dict(id=case['id'],category=case['category'],model=case['model'],mode=case['mode'],request=body)
            dest=args.output/f'{i+1:03}.json';dest.write_text(json.dumps(out,indent=2));started=time.monotonic()
            try:
                request=Request(base+'/api/chat',data=json.dumps(body).encode(),headers={'Content-Type':'application/json'})
                with urlopen(request,timeout=min(remaining,180)) as response:raw=json.load(response)
                out.update(raw=raw,**score(case,raw))
            except Exception as exc:out.update(error=f'{type(exc).__name__}: {exc}',complete=False,format_valid=False,correct=False)
            out['seconds']=time.monotonic()-started;dest.write_text(json.dumps(out,indent=2));results.append(out)
            print(case['id'],out.get('correct'),out.get('status'),round(out['seconds'],2),flush=True)
            if not out.get('complete') and 'raw' not in out:break
    finally:
        groups=defaultdict(lambda:dict(attempted=0,complete=0,format_valid=0,correct=0))
        for out in results:
            g=groups['/'.join((out['model'],out['mode'],out['category']))]
            for key in g:g[key]+=1 if key=='attempted' else int(bool(out.get(key)))
        unchanged=all(hashlib.sha256((ROOT/path).read_bytes()).hexdigest()==h for path,h in hashes.items())
        (args.output/'summary.json').write_text(json.dumps(dict(planned=len(plan),attempted=len(results),groups=dict(groups),unattempted=[c['id'] for c in plan[len(results):]],code_unchanged=unchanged,accuracy=None,independent_pedagogical_labels=False),indent=2))
        if not unchanged:raise ValueError('Code changed during diagnostics')

if __name__=='__main__':main()
