import json
from decimal import Decimal
from types import SimpleNamespace

import jsonschema
import pytest

from scripts.run_gpt4o_smoke import BudgetedCompletion, GroqCompletion, GROQ_MODEL, MODEL, cases, run_case, development_cases


def response(value, prompt_tokens=100, completion_tokens=100):
    usage = dict(prompt_tokens=prompt_tokens, completion_tokens=completion_tokens,
                 total_tokens=prompt_tokens+completion_tokens)
    raw = dict(model=MODEL, id='mock', usage=usage,
               choices=[dict(finish_reason='stop', message=dict(content=json.dumps(value)))])
    return SimpleNamespace(model=MODEL, id='mock',
        usage=SimpleNamespace(**usage, model_dump=lambda: usage),
        choices=[SimpleNamespace(finish_reason='stop', message=SimpleNamespace(content=json.dumps(value)))],
        model_dump=lambda: raw)


@pytest.mark.parametrize('selected_model', [MODEL, GROQ_MODEL])
def test_gpt4o_routes_every_stage_and_preserves_grounding(selected_model):
    case = next(c for c in cases() if c['id'] == 'physics-supported')
    stages = []
    def complete(**request):
        assert request['model'] == selected_model
        schema = request['response_format']['json_schema']['schema']
        stage = request['response_format']['json_schema']['name']
        stages.append(stage)
        payload = json.loads(request['messages'][1]['content'])
        assert not {'expected', 'reference_answer', 'condition'} & payload.keys()
        if stage == 'prerequisites':
            value = dict(givens=[], requirements=[dict(name='Average speed definition',
                necessity='Relate distance and time.', search_query='Average speed')])
        elif stage == 'requirement_0':
            evidence = next(e for e in payload['evidence_catalog'] if 'total distance divided' in e['quote'])
            value = dict(evidence_id=evidence['evidence_id'], established_knowledge='Speed is distance divided by time.',
                needed_knowledge='Average speed definition', basis='STATED', derivation='')
        elif stage == 'task_facts':
            value = dict(status='SUFFICIENT', missing_facts=[], rationale='Distance and time supplied.')
        else:
            assert stage == 'challenge'
            value = dict(context_readings={e['id']:'Read source.' for e in payload['review_context']},
                requirements_complete=True, evidence_entails_requirements=True,
                assumptions_explicit=True, issues=[], observations=[])
        jsonschema.validate(value, schema)
        # Every object sent to OpenAI must have specified, required keys only.
        def check(node):
            if isinstance(node, dict):
                if node.get('type') == 'object':
                    assert node.get('additionalProperties') is False
                    assert set(node.get('required', [])) == set(node.get('properties', {}))
                for child in node.values():
                    check(child)
            elif isinstance(node, list):
                for child in node:
                    check(child)
        check(schema)
        return response(value)
    result = run_case(case, complete, lambda _: None, model=selected_model)
    assert result['status'] == 'MODEL_SUPPORTED', result
    assert stages == ['prerequisites', 'requirement_0', 'task_facts', 'challenge']
    assert result['audit']['validated_quotes']


def test_budget_blocks_before_call_and_stops_after_uncertain_failure(tmp_path):
    requests = []
    request = dict(model=MODEL, max_tokens=500,
                   response_format={'json_schema': {'name': 'test'}})
    def create(**kwargs):
        requests.append(kwargs)
        return response({})
    small = BudgetedCompletion(create, '0.01', tmp_path/'small.json')
    with pytest.raises(RuntimeError, match='Budget'):
        small(**request)
    assert not requests
    guard = BudgetedCompletion(create, '1', tmp_path/'usage.json')
    guard(**request)
    assert guard.charged == Decimal('0.000075')
    def fail(**kwargs):
        raise TimeoutError('uncertain request')
    guard.create = fail
    with pytest.raises(RuntimeError, match='reservation retained'):
        guard(**request)
    assert guard.charged == Decimal('0.019575')
    with pytest.raises(RuntimeError, match='stopped'):
        guard(**request)
    assert len(guard.calls) == 2
    assert json.loads((tmp_path/'usage.json').read_text())['calls'][-1]['status'] == 'uncertain_or_failed'
    assert guard.calls[-1]['http_status'] is None
    assert guard.calls[-1]['api_error_code'] is None


def test_groq_adapter_bounds_calls_and_stops_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr('scripts.run_gpt4o_smoke.time.sleep', lambda _: None)
    seen = []
    def create(**request):
        seen.append(request)
        if len(seen) == 2:
            raise TimeoutError()
        return response({})
    guard = GroqCompletion(create, tmp_path/'groq.json')
    request = dict(model=GROQ_MODEL, max_tokens=500, response_format={'json_schema': {'name': 'task_facts'}})
    guard(**request)
    assert seen[0]['max_completion_tokens'] == 4096 and 'max_tokens' not in seen[0]
    assert seen[0]['reasoning_effort'] == 'high'
    with pytest.raises(RuntimeError, match='Groq request failed'):
        guard(**request)
    with pytest.raises(RuntimeError, match='stopped'):
        guard(**request)
    assert len(seen) == 2


def test_groq_retries_only_once_and_preserves_failed_attempt(tmp_path, monkeypatch):
    monkeypatch.setattr('scripts.run_gpt4o_smoke.time.sleep', lambda _: None)
    class FormatError(Exception):
        status_code=400
        code='json_validate_failed'
    def fail(**kwargs):
        raise FormatError()
    guard=GroqCompletion(fail,tmp_path/'groq.json')
    with pytest.raises(RuntimeError,match='Groq request failed'):
        guard(model=GROQ_MODEL,max_tokens=2200,response_format={'json_schema':{'name':'challenge'}})
    assert [c['attempt'] for c in guard.calls]==[1,2]
    assert all(c['status']=='failed' for c in guard.calls)
    assert guard.stopped


def test_broader_development_plan_covers_three_families_and_preserves_omissions():
    plan=development_cases()
    assert len(plan)==9 and len({c['id'] for c in plan})==9
    assert sum(c['expected']=='MODEL_SUPPORTED' for c in plan)==3
    assert 132/12==11 and (2*7+4*19)/(2+4)==15
    for case in plan:
        assert any(r['id']=='rule' for r in case['records'])==(case['condition']!='omitted_rule')
        assert case['records'][-1]==case['target']
