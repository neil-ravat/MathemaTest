"""Prepare three development controls; use --run --budget-usd to call GPT-4o-mini."""
import argparse
from datetime import datetime, timezone
from decimal import Decimal
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from openai import OpenAI
from dotenv import load_dotenv
from scripts.compare_local_workflows import candidate, cases
from src.verification.curriculum_audit import audit_curriculum

MODEL = 'gpt-4o-mini-2024-07-18'
INPUT_RATE = Decimal('0.15') / 1_000_000
OUTPUT_RATE = Decimal('0.60') / 1_000_000
GROQ_MODEL = 'openai/gpt-oss-120b'


def write_json(path, value):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(value, indent=2))
    temporary.replace(path)


class BudgetedCompletion:
    """Sequential calls only; reserve full context cost before sending a request."""
    def __init__(self, create, budget, ledger):
        self.create, self.budget, self.ledger = create, Decimal(str(budget)), ledger
        if not self.budget.is_finite() or self.budget <= 0:
            raise ValueError('A positive finite USD budget is required')
        self.charged = Decimal(0)
        self.calls = []
        self.stopped = False

    def __call__(self, **request):
        if self.stopped:
            raise RuntimeError('API run stopped; inspect the ledger before retrying')
        if request['model'] != MODEL or not 0 < request['max_tokens'] <= 16384:
            raise ValueError('Unexpected model or output token limit')
        # Conservative upper bound: full 128k input PLUS requested output.
        # Successful usage replaces the reservation; uncertain failures retain it.
        reserve = 128000 * INPUT_RATE + request['max_tokens'] * OUTPUT_RATE
        if self.charged + reserve > self.budget:
            self.stopped = True
            raise RuntimeError('Budget cannot cover the next request reservation')
        self.charged += reserve
        record = dict(stage=request['response_format']['json_schema']['name'],
                      reserved_usd=str(reserve), status='reserved')
        self.calls.append(record)
        self.save()
        try:
            response = self.create(**request)
            usage = response.usage
            if usage is None or usage.prompt_tokens < 0 or usage.completion_tokens < 0:
                raise ValueError('Missing or invalid API usage; retaining reservation')
            # Cached input is deliberately charged at the higher uncached rate.
            actual = usage.prompt_tokens * INPUT_RATE + usage.completion_tokens * OUTPUT_RATE
            if actual > reserve:
                raise ValueError('API usage exceeded reservation; stop and inspect billing')
            self.charged += actual - reserve
            record.update(status='completed', usage=usage.model_dump(),
                          cost_usd=str(actual), response_model=response.model,
                          response_id=response.id)
            self.save()
            return response
        except Exception as exc:
            self.stopped = True
            # Exception messages can contain request details; never log credentials.
            record.update(status='uncertain_or_failed', error_type=type(exc).__name__,
                          http_status=getattr(exc, 'status_code', None),
                          api_error_code=getattr(exc, 'code', None))
            self.save()
            raise RuntimeError(f'API request failed ({type(exc).__name__}); reservation retained') from None

    def save(self):
        write_json(self.ledger, dict(budget_usd=str(self.budget),
            accounted_or_reserved_usd=str(self.charged), calls=self.calls,
            rates_usd_per_million=dict(input=str(INPUT_RATE * 1_000_000),
                                      output=str(OUTPUT_RATE * 1_000_000)),
            scope='This process only; no SDK retries; no automatic resume'))


class GroqCompletion:
    """Bounded Free-plan development run; stop on API failure, no paid fallback."""
    def __init__(self, create, ledger):
        self.create, self.ledger = create, ledger
        self.calls, self.stopped, self.last_started = [], False, None

    def __call__(self, **request):
        if self.stopped or len(self.calls) >= 33:
            self.stopped = True
            raise RuntimeError('Groq run stopped or request limit reached')
        if request['model'] != GROQ_MODEL:
            raise ValueError('Unexpected Groq model')
        # Allow reasoning tokens in addition to the schema output. Preserve prompts.
        request.pop('max_tokens')
        request.update(max_completion_tokens=4096, reasoning_effort='low',
                       extra_body={'include_reasoning': False})
        if self.last_started is not None:
            time.sleep(max(0, 61 - (time.monotonic() - self.last_started)))
        self.last_started = time.monotonic()
        record = dict(stage=request['response_format']['json_schema']['name'],
                      status='started', request=request)
        self.calls.append(record)
        self.save()
        try:
            response = self.create(**request)
            record.update(status='completed', response_model=response.model,
                          usage=response.usage.model_dump() if response.usage else None)
            self.save()
            print('Groq stage:', record['stage'], response.choices[0].finish_reason, flush=True)
            return response
        except Exception as exc:
            self.stopped = True
            record.update(status='failed', error_type=type(exc).__name__,
                          http_status=getattr(exc, 'status_code', None),
                          api_error_code=getattr(exc, 'code', None))
            self.save()
            raise RuntimeError(f'Groq request failed ({type(exc).__name__}); inspect usage.json') from None

    def save(self):
        write_json(self.ledger, dict(provider='groq', model=GROQ_MODEL, calls=self.calls,
            assumed_account_plan='Free (user configured); not verified by API',
            max_requests=33, minimum_request_interval_seconds=61, retries=0))


def run_case(case, completion, checkpoint, *, model=MODEL):
    client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=completion)))
    upstream = audit_curriculum(client, model, model, case['records'], case['target'],
        case['background'], upstream_only=True,
        checkpoint=lambda value: checkpoint(dict(upstream=value)))
    if upstream['status'] != 'UPSTREAM_READY':
        result = dict(case_id=case['id'], status=upstream['status'], upstream=upstream)
    else:
        result = candidate(upstream,
            lambda value: checkpoint(dict(upstream=upstream, audit=value)), completion,
            evidence_first=True, producer_model=model, reviewer_model=model)
        result = dict(case_id=case['id'], status=result['status'], upstream=upstream, audit=result)
    checkpoint(result)
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--run', action='store_true', help='Make paid API calls; default only prepares files')
    parser.add_argument('--budget-usd', type=Decimal)
    parser.add_argument('--provider', choices=['openai', 'groq'], default='openai')
    args = parser.parse_args()
    is_groq = args.provider == 'groq'
    model = GROQ_MODEL if is_groq else MODEL
    key_name = 'GROQ_API_KEY' if is_groq else 'OPENAI_API_KEY'
    if args.run:
        load_dotenv(ROOT/'.env', override=False)
        if not is_groq and (args.budget_usd is None or not args.budget_usd.is_finite() or args.budget_usd <= 0):
            parser.error('--run requires a positive finite --budget-usd')
        if not os.environ.get(key_name, '').startswith('gsk_' if is_groq else 'sk-'):
            parser.error(f'Set {key_name} locally; do not paste it into chat')
    args.output.mkdir(parents=True, exist_ok=False)
    plan = [case for case in cases() if case['subject'] == 'physics']
    hashes = {}
    files = [*sorted((ROOT/'src').rglob('*.py')),
             *sorted((ROOT/'scripts').glob('*.py'))]
    for path in files:
        name = str(path.relative_to(ROOT))
        destination = args.output/'source_snapshot'/name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, destination)
        hashes[name] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest = dict(created=datetime.now(timezone.utc).isoformat(), model=model,
        provider=args.provider, producer=model, reviewer=model, plan=plan, source_hashes=hashes,
        transport_settings=dict(max_completion_tokens=4096, reasoning_effort='low',
            include_reasoning=False, minimum_request_interval_seconds=61) if is_groq else {},
        mode='live' if args.run else 'prepared_only', retries=0,
        budget_usd=str(args.budget_usd) if args.budget_usd is not None else None,
        workflow='GPT proposal -> retrieval -> evidence witnesses -> task facts -> GPT review',
        scope='Previously inspected synthetic development controls; no independent accuracy estimate',
        limitation='Same-model review is not independent validation. No Lean proof in this workflow.')
    write_json(args.output/'manifest.json', manifest)
    if not args.run:
        print(f'Prepared {len(plan)} controls for {model}; no API calls. {args.output}')
        return
    client = OpenAI(api_key=os.environ[key_name], base_url='https://api.groq.com/openai/v1' if is_groq else 'https://api.openai.com/v1',
                    max_retries=0, timeout=90.0)
    completion = (GroqCompletion(client.chat.completions.create, args.output/'usage.json') if is_groq
                  else BudgetedCompletion(client.chat.completions.create, args.budget_usd, args.output/'usage.json'))
    completion.save()
    results = []
    try:
        for case in plan:
            if completion.stopped:
                break
            destination = args.output/(case['id']+'.json')
            result = run_case(case, completion, lambda value: write_json(destination, value), model=model)
            results.append(dict(case_id=case['id'], status=result['status']))
            print(case['id'], result['status'], flush=True)
    finally:
        unchanged = all(hashlib.sha256((ROOT/name).read_bytes()).hexdigest() == digest
                        for name, digest in hashes.items())
        write_json(args.output/'summary.json', dict(results=results, planned=len(plan),
            attempted=len(results), code_unchanged=unchanged, accuracy=None,
            independent_labels=False, accounted_or_reserved_usd=None if is_groq else str(completion.charged)))
        if not unchanged:
            raise ValueError('Source changed during run; do not treat results as frozen')


if __name__ == '__main__':
    main()
