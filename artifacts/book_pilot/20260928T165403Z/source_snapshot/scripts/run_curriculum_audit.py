"""General source-backed curriculum audit on explicit development targets.

Consumes source-ordered JSONL records, not a particular textbook format.
No labels or held-out selection are inferred by this runner.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from urllib.request import urlopen, Request
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.verification.curriculum_audit import audit_curriculum, PROPOSE, ASSESS, CHALLENGE


CONTEXT_TOKENS = 16384
REQUEST_TIMEOUT_SECONDS = 600
DEADLINE = None


def local_completion(**kwargs):
    body = dict(model=kwargs['model'], stream=False, keep_alive='5m',
        messages=kwargs['messages'], format=kwargs['response_format']['json_schema']['schema'],
        options=dict(temperature=kwargs['temperature'], seed=kwargs['seed'],
                     num_predict=kwargs['max_tokens'], num_ctx=CONTEXT_TOKENS))
    request = Request('http://127.0.0.1:11434/api/chat', data=json.dumps(body).encode(),
                      headers={'Content-Type':'application/json'})
    remaining = REQUEST_TIMEOUT_SECONDS if DEADLINE is None else min(REQUEST_TIMEOUT_SECONDS, DEADLINE-time.monotonic())
    if remaining <= 0:
        raise TimeoutError('Session time budget exhausted before model call')
    with urlopen(request, timeout=remaining) as response:
        raw = json.load(response)
    # Preserve the raw completion even if the context/output budget is exhausted.
    reason = raw.get('done_reason', 'unknown')
    if raw.get('prompt_eval_count', CONTEXT_TOKENS) + kwargs['max_tokens'] > CONTEXT_TOKENS:
        reason = 'context_budget_exhausted'
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,
        message=SimpleNamespace(content=raw.get('message', {}).get('content', '')))], model_dump=lambda: raw)


def main():
    global DEADLINE
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--corpus',type=Path,required=True)
    p.add_argument('--target-id',action='append',required=True)
    p.add_argument('--background',required=True)
    p.add_argument('--time-budget-seconds',type=int,default=None)
    args=p.parse_args()
    if args.time_budget_seconds is not None:
        if args.time_budget_seconds <= 0:raise ValueError('Positive time budget required')
        DEADLINE=time.monotonic()+args.time_budget_seconds
    records=[json.loads(line) for line in args.corpus.read_text().splitlines() if line.strip()]
    by_id={r['id']:r for r in records}
    if len(by_id)!=len(records):raise ValueError('Duplicate corpus record IDs')
    targets=[by_id[id] for id in args.target_id]
    run=ROOT/'artifacts/general_curriculum_audit'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    hashes={}
    for src in [*sorted((ROOT/'src').rglob('*.py')),Path(__file__).resolve()]:
        dest=run/'source_snapshot'/src.relative_to(ROOT);dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(src,dest);hashes[str(src.relative_to(ROOT))]=hashlib.sha256(src.read_bytes()).hexdigest()
    manifest=dict(scope='Development feasibility; no independent reference labels',corpus=str(args.corpus),
        corpus_sha256=hashlib.sha256(args.corpus.read_bytes()).hexdigest(),source_hashes=hashes,
        target_ids=args.target_id,background=args.background,model='qwen2.5-coder:7b',reviewer='mistral:latest',
        prompts=[PROPOSE,ASSESS,CHALLENGE],temperature=0,seed=42,max_tokens_by_stage=dict(prerequisites=2200,assessment=4096,challenge=2200),retries=0,
        time_budget_seconds=args.time_budget_seconds,context_tokens=CONTEXT_TOKENS,transport='native Ollama /api/chat; explicit context and schema')
    (run/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print(run,flush=True)
    results=[]
    try:
        with urlopen('http://127.0.0.1:11434/api/tags',timeout=20) as response:
            (run/'model_metadata.json').write_bytes(response.read())
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=local_completion)))
        for target in targets:
            if DEADLINE is not None and time.monotonic() >= DEADLINE:
                break
            destination=run/(str(len(results)+1)+'.json')
            def checkpoint(value):
                temporary=destination.with_suffix('.tmp')
                temporary.write_text(json.dumps(value,indent=2))
                temporary.replace(destination)
            result=audit_curriculum(client,manifest['model'],manifest['reviewer'],records,target,args.background,checkpoint=checkpoint)
            results.append(result)
            checkpoint(result)
            print(target['id'],result['status'],len(result['calls']),flush=True)
            if result['status']=='INTERRUPTED':break
    finally:
        unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest for name,digest in hashes.items())
        corpus_unchanged=hashlib.sha256(args.corpus.read_bytes()).hexdigest()==manifest['corpus_sha256']
        (run/'summary.json').write_text(json.dumps(dict(planned=len(targets),attempted=len(results),completed=sum(r['status']!='INTERRUPTED' for r in results),
            statuses=[r['status'] for r in results],unattempted_target_ids=args.target_id[len(results):],code_unchanged=unchanged,corpus_unchanged=corpus_unchanged,
            accuracy=None,independent_labels=False),indent=2))
        if not unchanged or not corpus_unchanged:raise ValueError('Frozen input/code changed during run')


if __name__=='__main__':main()
