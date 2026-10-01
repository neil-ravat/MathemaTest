"""Frozen exploratory source-book run; no independent gold labels."""
from pathlib import Path
import hashlib
import json
import os
import shutil
import sys
import time

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from dotenv import load_dotenv
from openai import OpenAI
from scripts.run_gpt4o_smoke import GroqCompletion,GROQ_MODEL,run_case,write_json
from scripts.run_book_pilot import CORPUS,SOURCE

HERE=Path(__file__).resolve().parent


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (HERE/'manifest.json').exists():raise ValueError('Run already exists; do not overwrite')
    plan=json.loads((HERE/'plan.json').read_text())
    assert digest(CORPUS)==plan['corpus_sha256']
    source_manifest=json.loads((SOURCE/'manifest.json').read_text())
    for item in source_manifest['source_files']:
        assert digest(SOURCE/'source'/item['path'])==item['sha256']
    records=[json.loads(l) for l in CORPUS.read_text().splitlines()]
    hashes={}
    for path in [*sorted((ROOT/'src').rglob('*.py')),*sorted((ROOT/'scripts').glob('*.py'))]:
        name=str(path.relative_to(ROOT));dest=HERE/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(path,dest);hashes[name]=digest(path)
    manifest=dict(plan=plan,source_hashes=hashes,plan_sha256=digest(HERE/'plan.json'),
        source_manifest_sha256=digest(SOURCE/'manifest.json'),runner_sha256=digest(Path(__file__)),
        model=GROQ_MODEL,provider='groq',request_cap=60,time_budget_seconds=1200,
        scope='Six source-book exercises. New full-pipeline outputs, same development book. No independent labels or accuracy estimate.',
        reasoning_effort='high task facts, low other stages',retries_per_stage=1)
    write_json(HERE/'manifest.json',manifest)
    load_dotenv(ROOT/'.env',override=False)
    client=OpenAI(api_key=os.environ['GROQ_API_KEY'],base_url='https://api.groq.com/openai/v1',max_retries=0,timeout=90)
    live=GroqCompletion(client.chat.completions.create,HERE/'usage.json',max_requests=60)
    live.save();results=[];started=time.monotonic()
    try:
        for n,item in enumerate(plan['selection'],1):
            if live.stopped or time.monotonic()-started>1200:break
            target=item['target'];dest=HERE/f'case-{n:02}.json'
            if item['input_issues']:
                result=dict(case_id=target['id'],status='INPUT_REVIEW_REQUIRED',input_issues=item['input_issues'])
                write_json(dest,result)
            else:
                case=dict(id=target['id'],target=target,records=records,background=plan['background'])
                result=run_case(case,live,lambda value:write_json(dest,value),model=GROQ_MODEL)
            results.append(dict(id=target['id'],file=dest.name,status=result['status']))
            print(n,target['id'],result['status'],flush=True)
            write_json(HERE/'progress.json',dict(planned=6,completed=len(results),results=results))
    finally:
        unchanged=all(digest(ROOT/name)==h for name,h in hashes.items())
        write_json(HERE/'summary.json',dict(results=results,planned=6,completed=len(results),
            code_unchanged=unchanged,plan_unchanged=digest(HERE/'plan.json')==manifest['plan_sha256'],
            corpus_unchanged=digest(CORPUS)==plan['corpus_sha256'],elapsed_seconds=round(time.monotonic()-started,2),
            accuracy=None,independent_labels=False))
        if not unchanged:raise ValueError('Source changed during inference')


if __name__=='__main__':main()
