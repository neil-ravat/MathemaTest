"""Saved-upstream regression replays; only task-fact and needed review calls are live."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import time
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from openai import OpenAI
from scripts.compare_local_workflows import candidate
from scripts.run_gpt4o_smoke import GroqCompletion, GROQ_MODEL, write_json

HERE=Path(__file__).resolve().parent
SOURCE=ROOT/'artifacts/groq_development_revision_20261001_01'
PLAN=[('physics-omitted_rule','RULE_NOT_ESTABLISHED'),
      ('density-omitted_rule','RULE_NOT_ESTABLISHED'),
      ('weighted_mean-omitted_rule','RULE_NOT_ESTABLISHED'),
      ('density-missing_task_fact','MISSING_TASK_FACT'),
      ('weighted_mean-supported','SUFFICIENT')]


def main():
    if (HERE/'manifest.json').exists():
        raise ValueError('Already run; do not overwrite')
    hashes={}
    for name in ('scripts/compare_local_workflows.py','scripts/run_gpt4o_smoke.py',
                 'src/verification/curriculum_audit.py','src/verification/support_witness.py',
                 'src/verification/primitive_skills.py'):
        source=ROOT/name;dest=HERE/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest);hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    write_json(HERE/'manifest.json',dict(plan=PLAN,source_hashes=hashes,
        scope='Inspected development controls. Reuse saved proposal/retrieval/witnesses; task facts and any final review are live.',
        independent_labels=False,reasoning_effort='high task facts; low final review'))
    load_dotenv(ROOT/'.env',override=False)
    client=OpenAI(api_key=os.environ['GROQ_API_KEY'],base_url='https://api.groq.com/openai/v1',max_retries=0,timeout=90)
    live=GroqCompletion(client.chat.completions.create,HERE/'usage.json',max_requests=12)
    prior=ROOT/'artifacts/groq_effort_diagnostic_20261001/summary.json'
    time.sleep(max(0,61-(time.time()-prior.stat().st_mtime)))
    results=[]
    try:
        for case_id,expected_fact_status in PLAN:
            if live.stopped:break
            saved=json.loads((SOURCE/(case_id+'.json')).read_text())
            old={c['stage']:c for c in saved['audit']['calls']}
            def complete(**request):
                stage=request['response_format']['json_schema']['name']
                if not stage.startswith('requirement_'):
                    return live(**request)
                previous=old[stage]
                assert request['messages']==previous['messages']
                assert request['response_format']['json_schema']['schema']==previous['schema']
                raw=previous['response']
                choices=[SimpleNamespace(finish_reason=c['finish_reason'],message=SimpleNamespace(content=c['message']['content'])) for c in raw['choices']]
                return SimpleNamespace(choices=choices,model_dump=lambda:{**raw,'replay_origin':str(SOURCE/(case_id+'.json'))})
            destination=HERE/(case_id+'.json')
            audit=candidate(saved['upstream'],lambda value:write_json(destination,value),complete,
                evidence_first=True,producer_model=GROQ_MODEL,reviewer_model=GROQ_MODEL)
            write_json(destination,audit)
            actual=audit.get('task_facts',{}).get('status')
            results.append(dict(case_id=case_id,status=audit['status'],expected_task_status=expected_fact_status,
                actual_task_status=actual,task_status_matches=actual==expected_fact_status,
                final_review_skipped='review_skipped_reason' in audit,error=audit.get('error')))
            print(case_id,audit['status'],actual,flush=True)
    finally:
        write_json(HERE/'summary.json',dict(results=results,attempted=len(results),planned=len(PLAN),
            code_unchanged=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in hashes.items()),
            task_status_matches=sum(r['task_status_matches'] for r in results),accuracy=None,independent_labels=False))


if __name__=='__main__':main()
