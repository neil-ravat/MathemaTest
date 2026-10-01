"""Locked paired comparison on fresh cases; Groq API only, no GPU execution.

Run --lock after completing the separate pre-output reference review, then --run.
All selected cases remain in the report, including unattempted and error outcomes.
"""
import argparse
from collections import Counter
from datetime import datetime,timezone
import fcntl
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
DEFAULT=ROOT/'artifacts/six_improvements_20261001/fresh_comparison'


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def write(path,value):
    path.parent.mkdir(parents=True,exist_ok=True)
    temp=path.with_suffix('.tmp');temp.write_text(json.dumps(value,indent=2,ensure_ascii=False));temp.replace(path)


def lock(run):
    if (run/'lock.json').exists():raise ValueError('Existing evaluation lock must not be replaced')
    plan=json.loads((run/'plan.json').read_text());refs=json.loads((run/'reference_review.json').read_text())
    if len({r['case_id'] for r in refs})!=len(plan) or {r['case_id'] for r in refs}!={r['id'] for r in plan}:
        raise ValueError('Every selected case needs exactly one reference review')
    if any(r['reference_status'] not in {'MODEL_SUPPORTED','REVIEW_REQUIRED','UNCERTAIN'} or not r['rationale'].strip() for r in refs):
        raise ValueError('Finish pre-output reference review before locking')
    # Snapshot the same shared transport/runner for both arms, with source code
    # independently preserved for the baseline and candidate workflows.
    runner=run/'runner.py';runner.write_bytes(Path(__file__).read_bytes())
    paths=[run/'plan.json',run/'protocol.json',run/'reference_review.json',run/'exposure_audit.json',runner]
    for tree in [run/'candidate_snapshot',run.parent/'baseline']:
        paths.extend(tree.rglob('*.py'))
    for case in plan:
        paths.extend(Path(case[k]) for k in ['baseline_corpus','candidate_corpus','original_source_manifest'])
        manifest_path=Path(case['original_source_manifest']);manifest=json.loads(manifest_path.read_text())
        for item in manifest['source_files']:
            source=manifest_path.parent/'source'/item['path']
            if digest(source)!=item['sha256']:raise ValueError('Pinned source changed: '+str(source))
            paths.append(source)
    paths=sorted(set(paths));hashes={str(p.resolve()):digest(p) for p in paths}
    write(run/'lock.json',dict(created=datetime.now(timezone.utc).isoformat(),files=hashes,
        planned_cases=len(plan),planned_arms=len(plan)*2,max_api_requests=96,
        source_claim='Same pinned original source inputs and targets, separate pipeline renderings',
        reference_claim='Assistant provisional source-support review; no independent pedagogical accuracy'))
    print('Locked',len(paths),'files; no model calls.')


def verify(run):
    manifest=json.loads((run/'lock.json').read_text())
    for path,expected in manifest['files'].items():
        if digest(Path(path))!=expected:raise ValueError('Frozen evaluation file changed: '+path)
    return manifest


def summarize(run):
    plan=json.loads((run/'plan.json').read_text());refs={r['case_id']:r for r in json.loads((run/'reference_review.json').read_text())}
    rows=[];arms={}
    for arm in ['baseline','candidate']:
        outcomes=[];usage=[]
        for i,case in enumerate(plan):
            path=run/'results'/f'{i:02}-{arm}.json'
            value=json.loads(path.read_text()) if path.exists() else {}
            status=value.get('status','UNATTEMPTED') if value.get('_finished') else 'UNATTEMPTED'
            row=dict(case_id=case['id'],family=case['family'],book=case['book'],arm=arm,
                reference=refs[case['id']]['reference_status'],status=status,seconds=value.get('seconds',0))
            outcomes.append(row);rows.append(row)
            up=run/'results'/f'{i:02}-{arm}-usage.json'
            if up.exists():usage.extend(json.loads(up.read_text()).get('calls',[]))
        positive=[r for r in outcomes if r['reference']=='MODEL_SUPPORTED']
        negative=[r for r in outcomes if r['reference']=='REVIEW_REQUIRED']
        labeled=positive+negative
        reported=[c['usage'] for c in usage if c.get('usage')]
        arms[arm]=dict(planned=len(plan),status_counts=dict(Counter(r['status'] for r in outcomes)),
            provisional_status_matches=sum(r['status']==r['reference'] for r in labeled),reference_labeled_denominator=len(labeled),
            supported_case_acceptance=sum(r['status']=='MODEL_SUPPORTED' for r in positive),supported_denominator=len(positive),
            false_review_on_supported=sum(r['status']=='REVIEW_REQUIRED' for r in positive),
            unsupported_acceptance=sum(r['status']=='MODEL_SUPPORTED' for r in negative),unsupported_denominator=len(negative),
            valid_judgments=sum(r['status'] in {'MODEL_SUPPORTED','REVIEW_REQUIRED'} for r in outcomes),
            completed=sum(r['status']!='UNATTEMPTED' for r in outcomes),
            api_attempts=sum(c['status']!='blocked_before_request' for c in usage),
            blocked_before_request=sum(c['status']=='blocked_before_request' for c in usage),
            prompt_tokens=sum(u.get('prompt_tokens',0) for u in reported),
            completion_tokens=sum(u.get('completion_tokens',0) for u in reported),
            elapsed_case_seconds=round(sum(r['seconds'] for r in outcomes),3),
            failed_attempt_usage='Unknown when provider omits usage',cash_cost=None)
    result=dict(arms=arms,paired_rows=rows,accuracy=None,independent_labels=False,
        interpretation='Provisional source-support status agreement only; related variants are not independent families; no pedagogical accuracy or statistical significance claim.')
    write(run/'summary.json',result);return result


def worker(run,index,arm,remaining):
    # Load the frozen common transport, then isolate the requested workflow imports.
    sys.path.insert(0,str(run/'candidate_snapshot'))
    from scripts.run_gpt4o_smoke import GroqCompletion,GROQ_MODEL,write_json
    from dotenv import load_dotenv
    from openai import OpenAI
    credential_root=run.parents[2]
    load_dotenv(credential_root/'.env',override=False)
    if not os.environ.get('GROQ_API_KEY'):raise ValueError('Configured Groq credential unavailable')
    common=GroqCompletion
    if arm=='baseline':
        for name in list(sys.modules):
            if name=='src' or name.startswith('src.') or name=='scripts' or name.startswith('scripts.'):
                del sys.modules[name]
        sys.path.insert(0,str(run.parent/'baseline'))
    from scripts.run_gpt4o_smoke import run_case
    plan=json.loads((run/'plan.json').read_text());case=plan[index]
    records=[json.loads(line) for line in Path(case[arm+'_corpus']).read_text().splitlines()]
    if case['variant']=='no_prior_instruction':records=[]
    target=case[arm+'_target']
    payload=dict(id=case['id'],records=records,target=target,background=case['background'])
    destination=run/'results'/f'{index:02}-{arm}.json'
    rate_state=run/'rate_state.json'
    class SharedCompletion(common):
        def save(self):
            super().save()
            write_json(rate_state,self.recent_usage)
    client=OpenAI(api_key=os.environ['GROQ_API_KEY'],base_url='https://api.groq.com/openai/v1',max_retries=0,timeout=90)
    completion=SharedCompletion(client.chat.completions.create,run/'results'/f'{index:02}-{arm}-usage.json',max_requests=min(remaining,20))
    if rate_state.exists():completion.recent_usage=json.loads(rate_state.read_text())
    started=time.monotonic()
    try:
        result=run_case(payload,completion,lambda value:write_json(destination,value),model=GROQ_MODEL)
    except Exception as exc:
        result=dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
    result.update(_finished=True,case_id=case['id'],arm=arm,seconds=round(time.monotonic()-started,3),provider_stopped=completion.stopped)
    write_json(destination,result)
    print(case['id'],arm,result['status'],flush=True)


def execute(run):
    with (run/'execution.lock').open('w') as handle:
        fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        manifest=verify(run);plan=json.loads((run/'plan.json').read_text())
        (run/'results').mkdir(exist_ok=True)
        write(run/'process.json',dict(pid=os.getpid(),state='running',started=datetime.now(timezone.utc).isoformat()))
        try:
            for index,_ in enumerate(plan):
                for arm in (['baseline','candidate'] if index%2==0 else ['candidate','baseline']):
                    verify(run);destination=run/'results'/f'{index:02}-{arm}.json'
                    if destination.exists():
                        if json.loads(destination.read_text()).get('_finished'):continue
                        raise ValueError('Unfinished saved attempt requires inspection; no automatic repeat: '+str(destination))
                    total=summarize(run);used=sum(a['api_attempts'] for a in total['arms'].values());remaining=manifest['max_api_requests']-used
                    if remaining<=0:raise RuntimeError('Frozen API request budget exhausted')
                    write(run/'process.json',dict(pid=os.getpid(),state='running',case_index=index,arm=arm))
                    command=[sys.executable,str(run/'runner.py'),'--directory',str(run),'--worker',str(index),'--arm',arm,'--remaining',str(remaining)]
                    with (run/'results'/f'{index:02}-{arm}.log').open('a') as log:
                        try:
                            subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,timeout=1200)
                        except (subprocess.TimeoutExpired,subprocess.CalledProcessError) as exc:
                            old=json.loads(destination.read_text()) if destination.exists() else {}
                            write(destination,dict(**{k:v for k,v in old.items() if k not in {'status','error','_finished'}},status='ERROR',error=type(exc).__name__,_finished=True))
                    verify(run);result=json.loads(destination.read_text());summarize(run)
                    print(index,arm,result['status'],flush=True)
                    if result.get('provider_stopped'):raise RuntimeError('Provider stop recorded; remaining cases remain unattempted')
            write(run/'process.json',dict(pid=os.getpid(),state='completed'))
        except Exception as exc:
            write(run/'process.json',dict(pid=os.getpid(),state='stopped',reason=str(exc)));raise
        finally:
            summarize(run)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--directory',type=Path,default=DEFAULT)
    parser.add_argument('--lock',action='store_true');parser.add_argument('--run',action='store_true')
    parser.add_argument('--worker',type=int);parser.add_argument('--arm',choices=['baseline','candidate']);parser.add_argument('--remaining',type=int,default=0)
    args=parser.parse_args();run=args.directory.resolve()
    if args.worker is not None:worker(run,args.worker,args.arm,args.remaining)
    elif args.lock:lock(run)
    elif args.run:execute(run)
    else:print(json.dumps(summarize(run),indent=2))


if __name__=='__main__':main()
