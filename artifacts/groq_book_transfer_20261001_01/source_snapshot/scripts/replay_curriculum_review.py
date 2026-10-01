"""Replay only reviewer calls on preserved development assessments.

Preserves original runs; does not claim fresh end-to-end accuracy.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.run_curriculum_audit import local_completion, CONTEXT_TOKENS
from src.verification.curriculum_audit import (CHALLENGE, GroundedChallenge, Assessment,
    curriculum_status, review_request, validate_review)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input',type=Path)
    args=parser.parse_args()
    summary=json.loads((args.input/'summary.json').read_text())
    if summary['completed']!=summary['planned']:raise ValueError('A complete original run is required')
    originals=[args.input/(str(i)+'.json') for i in range(1,summary['completed']+1)]
    run=ROOT/'artifacts/curriculum_review_replay'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in originals}
    code_hashes={}
    for p in [*sorted((ROOT/'src').rglob('*.py')),Path(__file__).resolve(),ROOT/'scripts/run_curriculum_audit.py']:
        dest=run/'source_snapshot'/p.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(p,dest)
        code_hashes[str(p.relative_to(ROOT))]=hashlib.sha256(p.read_bytes()).hexdigest()
    (run/'manifest.json').write_text(json.dumps(dict(scope='Exposed reviewer-only replay; proposal, retrieval and assessment unchanged',
        inputs=hashes,code_hashes=code_hashes,prompt=CHALLENGE,schema=GroundedChallenge.model_json_schema(),
        model='mistral:latest',temperature=0,seed=42,max_tokens=2200,context_tokens=CONTEXT_TOKENS,retries=0),indent=2))
    print(run,flush=True);results=[]
    try:
        for i,path in enumerate(originals,1):
            saved=json.loads(path.read_text())
            prior=next(c for c in saved['calls'] if c['stage']=='challenge')
            payload,schema=review_request(json.loads(prior['messages'][1]['content']))
            messages=[dict(role='system',content=CHALLENGE),dict(role='user',content=json.dumps(payload))]
            out=dict(target_id=saved['target']['id'],previous_status=saved['status'],messages=messages,
                     schema=schema,status='REVIEW_REQUIRED',reviewer_grounding_valid=False)
            dest=run/(str(i)+'.json');dest.write_text(json.dumps(out,indent=2))
            try:
                response=local_completion(model='mistral:latest',messages=messages,temperature=0,seed=42,max_tokens=2200,
                    response_format={'json_schema':{'schema':schema}})
                out['response']=response.model_dump()
                if response.choices[0].finish_reason!='stop':raise ValueError('Incomplete reviewer output')
                review=GroundedChallenge.model_validate_json(response.choices[0].message.content)
                out['challenge']=review.model_dump()
                validate_review(review,payload)
                out['reviewer_grounding_valid']=True
                out['status']=curriculum_status(Assessment(**saved['assessment']),review,grounding_valid=True)
            except KeyboardInterrupt:
                out.update(status='INTERRUPTED',error='Reviewer replay interrupted')
            except Exception as exc:
                out['error']=f'{type(exc).__name__}: {exc}'
            dest.write_text(json.dumps(out,indent=2));results.append(out)
            print(out['target_id'],out['previous_status'],'->',out['status'],flush=True)
            if out['status']=='INTERRUPTED':break
    finally:
        unchanged=all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
        code_unchanged=all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest()==h for p,h in code_hashes.items())
        (run/'summary.json').write_text(json.dumps(dict(planned=len(originals),attempted=len(results),
            results=[{k:r[k] for k in ('target_id','previous_status','status')} for r in results],
            original_inputs_unchanged=unchanged,code_unchanged=code_unchanged),indent=2))
        if not unchanged or not code_unchanged:raise ValueError('Frozen inputs or code changed')


if __name__=='__main__':main()
