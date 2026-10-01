"""Bounded Ollama GPT-OSS-20B development continuation; no gold accuracy."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import time
from types import SimpleNamespace
from urllib.request import Request, urlopen

from scripts.compare_local_workflows import candidate
from src.verification.curriculum_audit import audit_curriculum, GroundedChallenge, validate_review

ROOT = Path(__file__).resolve().parent
OUT = ROOT / 'results'
MODEL = 'gpt-oss:20b'
CONTEXT = 32768


def save(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


def api(endpoint, body=None, timeout=10):
    request = Request('http://127.0.0.1:11434/api/' + endpoint,
        data=None if body is None else json.dumps(body).encode(),
        headers={'Content-Type': 'application/json'})
    with urlopen(request, timeout=timeout) as response:
        return json.load(response)


def request_body(request):
    stage = request['response_format']['json_schema']['name']
    limit = max(request.get('max_tokens', request.get('max_completion_tokens', 0)), 2048)
    if stage in ('challenge', 'task_facts'):
        limit = 4096
    return dict(model=MODEL, stream=False, keep_alive='5m',
        messages=request['messages'], format=request['response_format']['json_schema']['schema'],
        think='high' if stage == 'task_facts' else 'low',
        options=dict(temperature=0, seed=42, num_ctx=CONTEXT, num_predict=limit))


def main():
    OUT.mkdir(exist_ok=False)
    hashes=json.loads((ROOT/'checksums.json').read_text())
    for name, digest in hashes.items():
        assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest, name
    hardware=subprocess.check_output(['nvidia-smi'],text=True)
    (OUT/'nvidia-smi.txt').write_text(hardware)
    for endpoint in ('version','tags'):
        save(OUT/f'ollama-{endpoint}.json',api(endpoint))
    save(OUT/'ollama-show.json',api('show',dict(model=MODEL)))
    save(OUT/'manifest.json',dict(started=datetime.now(timezone.utc).isoformat(),
        model=MODEL, hashes=hashes, context_tokens=CONTEXT, inference_budget_seconds=600,
        max_calls=35, retries=0, temperature=0, seed=42,
        scope='Replay failed review of case 3, then cases 4–6 from frozen source-book plan. Ollama quantized runtime differs from Groq; not a hardware-only comparison. No expert labels.',
        reasoning_effort='high task_facts; low others'))
    calls=[]; started=time.monotonic(); deadline=started+600

    def completion(**request):
        if len(calls)>=35 or time.monotonic()>=deadline:
            raise TimeoutError('Bounded run limit reached')
        body=request_body(request)
        record=dict(stage=request['response_format']['json_schema']['name'],request=body,status='started')
        calls.append(record); save(OUT/'usage.json',calls)
        begin=time.monotonic()
        try:
            raw=api('chat',body,timeout=min(240,deadline-time.monotonic()))
            record.update(status='completed',response=raw,seconds=round(time.monotonic()-begin,3))
            save(OUT/'ollama-ps.json',api('ps'))
            reason=raw.get('done_reason','unknown')
            if raw.get('prompt_eval_count',CONTEXT)+body['options']['num_predict']>CONTEXT:
                reason='context_budget_exhausted'
            return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,
                message=SimpleNamespace(content=raw.get('message',{}).get('content','')))],model_dump=lambda:raw)
        except Exception as exc:
            record.update(status='failed',error=f'{type(exc).__name__}: {exc}')
            raise
        finally:
            save(OUT/'usage.json',calls)
            print(record['stage'],record['status'],round(time.monotonic()-begin,1),flush=True)

    results=[]
    try:
        request=json.loads((ROOT/'review_request.json').read_text())
        try:
            response=completion(**request)
            if response.choices[0].finish_reason!='stop':
                raise ValueError('Incomplete review output')
            review=GroundedChallenge.model_validate_json(response.choices[0].message.content)
            validate_review(review,json.loads(request['messages'][1]['content']))
            result=dict(status='VALID_REVIEW',review=review.model_dump())
        except Exception as exc:
            result=dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
        save(OUT/'case-03-review-replay.json',result)
        results.append(dict(case=3,replay=True,**result))
        records=[json.loads(line) for line in (ROOT/'corpus.jsonl').read_text().splitlines()]
        plan=json.loads((ROOT/'plan.json').read_text())
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
        for n,item in enumerate(plan['selection'][3:],4):
            if deadline-time.monotonic()<60 or any(c['status']=='failed' for c in calls):break
            target=item['target']; dest=OUT/f'case-{n:02}.json'
            if item['input_issues']:
                result=dict(status='INPUT_REVIEW_REQUIRED',issues=item['input_issues'])
            else:
                upstream=audit_curriculum(client,MODEL,MODEL,records,target,plan['background'],
                    upstream_only=True,checkpoint=lambda value:save(dest,dict(upstream=value)))
                result=dict(status=upstream['status'],upstream=upstream)
                if upstream['status']=='UPSTREAM_READY':
                    audit=candidate(upstream,lambda value:save(dest,dict(upstream=upstream,audit=value)),
                        completion,evidence_first=True,producer_model=MODEL,reviewer_model=MODEL)
                    result.update(status=audit['status'],audit=audit)
            save(dest,result); results.append(dict(case=n,id=target['id'],status=result['status']))
            save(OUT/'progress.json',results)
            print('CASE',n,result['status'],flush=True)
    finally:
        save(OUT/'summary.json',dict(results=results,calls=len(calls),
            elapsed_seconds=round(time.monotonic()-started,2),accuracy=None,independent_labels=False,
            inputs_unchanged=all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h for name,h in hashes.items())))
        try:api('generate',dict(model=MODEL,keep_alive=0),timeout=30)
        except Exception:pass
        print('FINISHED; SLEEP STUDIO TO STOP GPU BILLING',flush=True)


if __name__=='__main__':main()
