"""Prepare or run bounded development controls through OpenAI or Groq."""
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
    """Bounded Free-plan requests; at most one retry for rate/schema failures."""
    def __init__(self, create, ledger, max_requests=33):
        self.create, self.ledger = create, ledger
        self.max_requests = max_requests
        self.calls, self.stopped, self.recent_usage = [], False, []

    def __call__(self, **request):
        if self.stopped or len(self.calls) >= self.max_requests:
            self.stopped = True
            raise RuntimeError('Groq run stopped or request limit reached')
        if request['model'] != GROQ_MODEL:
            raise ValueError('Unexpected Groq model')
        # Honor stage budgets. Low reasoning preserves room for the final schema;
        # completion retries, if needed, are recorded by the workflow itself.
        stage = request['response_format']['json_schema']['name']
        limit = request.pop('max_tokens')
        if not 0 < limit <= 4096:
            raise ValueError('Completion budget must be within 1..4096 tokens')
        request.update(max_completion_tokens=limit, reasoning_effort='low',
                       extra_body={'include_reasoning': False})
        # Conservative estimate, never a tokenizer guarantee. Do not send an
        # obviously oversized request and then pretend quota waiting can fix it.
        estimate = (len(json.dumps(request).encode()) + 2) // 3 + limit
        if estimate > 7600:
            self.calls.append(dict(stage=stage,status='blocked_before_request',estimated_tokens=estimate,
                                   reason='Request estimate exceeds 7600-token safety budget'))
            self.save()
            raise ValueError('Request too large for configured capacity; no API call made')
        for attempt in range(2):
            if len(self.calls) >= self.max_requests:
                self.stopped = True
                raise RuntimeError('Groq request limit reached')
            now = time.monotonic()
            self.recent_usage = [(t,n) for t,n in self.recent_usage if now-t < 61]
            while self.recent_usage and sum(n for _,n in self.recent_usage)+estimate > 8000:
                delay = max(0, 61-(time.monotonic()-self.recent_usage[0][0]))
                print(f'Groq quota pacing: {delay:.0f}s', flush=True)
                while delay > 0:
                    time.sleep(min(delay,30));delay-=min(delay,30)
                self.recent_usage.pop(0)
            record = dict(stage=stage, attempt=attempt+1, status='started', request=request)
            self.calls.append(record)
            self.save()
            try:
                response = self.create(**request)
                usage = response.usage.model_dump() if response.usage else None
                self.recent_usage.append((time.monotonic(), usage['total_tokens'] if usage else estimate))
                record.update(status='completed', response_model=response.model, usage=usage)
                self.save()
                print('Groq stage:', stage, response.choices[0].finish_reason, flush=True)
                return response
            except Exception as exc:
                status, code = getattr(exc, 'status_code', None), getattr(exc, 'code', None)
                record.update(status='failed', error_type=type(exc).__name__,
                              http_status=status, api_error_code=code)
                self.save()
                if attempt == 0 and (status == 429 or (status == 400 and code == 'json_validate_failed')):
                    print(f'Groq {stage}: {status}/{code}; one bounded retry', flush=True)
                    for delay in ([30,30,1] if status == 429 else [2]):time.sleep(delay)
                    continue
                # A request-specific size/schema rejection does not make a
                # different later case unsafe to attempt. Authentication, quota,
                # transport and other uncertain failures stop this worker.
                self.stopped = status not in {400,413}
                raise RuntimeError(f'Groq request failed ({type(exc).__name__}); inspect usage.json') from None

    def save(self):
        write_json(self.ledger, dict(provider='groq', model=GROQ_MODEL, calls=self.calls,
            assumed_account_plan='Free (user configured); not verified by API',
            max_requests=self.max_requests, pacing='Rolling reported usage plus request-size estimate against 8000 tokens/minute',
            maximum_provider_retries_per_stage=1, request_estimate_limit=7600,
            retryable_errors=['429', '400/json_validate_failed']))


def development_cases():
    """Known regressions plus new synthetic variants; labels never enter prompts."""
    plan = [case for case in cases() if case['subject'] == 'physics']
    families = [
        ('density', 'chemistry', 'Density describes a material using its mass and volume.',
         'Density equals mass divided by volume. Mass in grams divided by volume in cubic centimetres gives density in grams per cubic centimetre.',
         'A sample has mass 132 grams and volume 12 cubic centimetres. Find its density in grams per cubic centimetre.',
         'A sample has mass 132 grams. Its volume is not specified. Find its density in grams per cubic centimetre.', 11),
        ('weighted_mean', 'math', 'A weighted mean combines values with assigned positive weights.',
         'For values a and b with positive weights u and v, the weighted mean is (u*a + v*b)/(u+v). Multiply each value by its weight, add the products, and divide by the sum of weights.',
         'Find the weighted mean of 7 and 19 with respective weights 2 and 4.',
         'Find the weighted mean of 7 and 19. The weight of 7 is 2; the positive weight of 19 is not specified.', 15)]
    for family, subject, intro, rule, complete, missing, answer in families:
        for condition in ('supported', 'omitted_rule', 'missing_task_fact'):
            identifier = family+'-'+condition
            def row(name, text, position, exercise=False):
                return dict(id=name, content=text, position=position, source_id=identifier,
                    module_id=identifier, kind='exercise' if exercise else 'para',
                    instructional_role='exercise_material' if exercise else 'exposition')
            records = [row('intro', intro, 0)]
            if condition != 'omitted_rule':
                records.append(row('rule', rule, 1))
            target = row('target', missing if condition == 'missing_task_fact' else complete, 3, True)
            records.append(target)
            plan.append(dict(id=identifier, subject=subject, condition=condition, records=records,
                target=target, background=plan[0]['background'], expected='MODEL_SUPPORTED' if condition=='supported' else 'REVIEW_REQUIRED',
                reference_answer=answer if condition=='supported' else None))
    return plan


def run_case(case, completion, checkpoint, *, model=MODEL, protocol='evidence-v2'):
    if protocol=='evidence-v2':
        from src.verification.evidence_audit import audit_evidence
        result=audit_evidence(completion,model,case['records'],case['target'],case['background'],checkpoint)
        result['case_id']=case['id'];checkpoint(result)
        return result
    if protocol!='legacy':raise ValueError('Unknown curriculum protocol')
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
    parser.add_argument('--run', action='store_true', help='Call the selected provider; default only prepares files')
    parser.add_argument('--budget-usd', type=Decimal)
    parser.add_argument('--provider', choices=['openai', 'groq'], default='openai')
    parser.add_argument('--suite', choices=['smoke', 'development'], default='smoke')
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
    plan = development_cases() if args.suite=='development' else [case for case in cases() if case['subject']=='physics']
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
        transport_settings=dict(max_completion_tokens='Stage-specific: proposal/review 2048, witness/task_facts 1024; one bounded completion retry, cap 4096', reasoning_effort='low',
            include_reasoning=False, pacing='Rolling reported usage plus request-size estimate, 8000 tokens/minute') if is_groq else {},
        mode='live' if args.run else 'prepared_only', retries=1 if is_groq else 0,
        budget_usd=str(args.budget_usd) if args.budget_usd is not None else None,
        workflow='GPT proposal -> retrieval -> evidence witnesses -> task facts -> GPT review',
        scope='Synthetic development controls; includes inspected regressions and new variants of familiar families; no independent accuracy estimate',
        limitation='Same-model review is not independent validation. No Lean proof in this workflow.')
    write_json(args.output/'manifest.json', manifest)
    if not args.run:
        print(f'Prepared {len(plan)} controls for {model}; no API calls. {args.output}')
        return
    client = OpenAI(api_key=os.environ[key_name], base_url='https://api.groq.com/openai/v1' if is_groq else 'https://api.openai.com/v1',
                    max_retries=0, timeout=90.0)
    completion = (GroqCompletion(client.chat.completions.create, args.output/'usage.json', max_requests=110 if args.suite=='development' else 33) if is_groq
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
