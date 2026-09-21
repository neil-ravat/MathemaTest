import json
from types import SimpleNamespace

import pytest

from src.config.settings import Settings
from src.retrieval.hybrid_orchestrator import RetrievalResult
from src.verification.auditor_prover import AuditorProver
from src.verification.auditor_prover import QuestionJudgment
from pydantic import ValidationError
from src.verification.lean_compiler import LeanCompilationResult


def auditor(claim='300', citation='prior', updates=None, source_text='Current is charge per time.'):
    judgment = {'status': 'PASS', 'reason': 'I*t, converting minutes to seconds',
        'missing_prerequisites': [], 'cited_passage_ids': [citation], 'assumptions': [],
        'calculation_expression': '0.5*10*60', 'claimed_value': claim, 'answer_unit': 'C'}
    judgment.update(updates or {})
    response = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
        message=SimpleNamespace(content=json.dumps(judgment)))], model_dump=lambda: {'raw_judgment': judgment})
    instance = AuditorProver.__new__(AuditorProver)
    instance.model = 'test-double'
    def retrieve(*args, **kwargs):
        assert kwargs['source_id'] == 'book' and kwargs['before_position'] == 100
        return [RetrievalResult('prior', source_text, 'vector', 1,
                               {'source_id': 'book', 'start_offset': 0, 'end_offset': 99})]
    instance.retriever = SimpleNamespace(retrieve_for_audit=retrieve)
    instance.openai = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
    instance.lean_compiler = SimpleNamespace(compile=lambda code, **kwargs:
        LeanCompilationResult(True, code, '', [], [], [], 'COMPILED_UNREVIEWED'))
    return instance


def test_false_numeric_claim_rejected_before_lean():
    result = auditor('2').audit_question('Charge?', source_id='book', before_position=100, background='arithmetic')
    assert result['status'] == 'REJECTED_CALCULATION'
    assert 'lean' not in result and 'answer' not in result


def test_arithmetic_acceptance_does_not_certify_source_or_units():
    result = auditor().audit_question('Charge?', source_id='book', before_position=100, background='arithmetic')
    assert result['status'] == 'ARITHMETIC_CHECKED' and result['answer'] == '300 C'
    assert not result['units_verified'] and not result['question_fidelity_verified']
    assert result['educational_gold_label'] is None


def test_invalid_citation_retains_raw_response_and_is_error():
    result = auditor(citation='future').audit_question('Charge?', source_id='book', before_position=100, background='arithmetic')
    assert result['status'] == 'ERROR' and 'Non-retrieved citation' in result['error']
    assert 'response' in result and 'lean' not in result


def test_retrieval_failure_does_not_become_gap():
    instance = auditor()
    def fail(*args, **kwargs):
        raise ConnectionError('graph offline')
    instance.retriever.retrieve_for_audit = fail
    with pytest.raises(ConnectionError):
        instance.audit_question('Charge?', source_id='book', before_position=100, background='arithmetic')


def test_dummy_keys_are_only_allowed_for_loopback():
    assert Settings(_env_file=None, openai_api_key='ollama', openai_base_url='http://127.0.0.1:11434/v1').validate_openai_key()
    assert not Settings(_env_file=None, openai_api_key='ollama', openai_base_url='https://example.com/v1').validate_openai_key()


def test_expression_schema_rejects_units():
    payload = {'status': 'PASS', 'reason': 'Current times seconds',
        'missing_prerequisites': [], 'cited_passage_ids': ['prior'], 'assumptions': [],
        'calculation_expression': '(0.5 A) * (10 minutes)',
        'claimed_value': '300', 'answer_unit': 'C'}
    with pytest.raises(ValidationError):
        QuestionJudgment.model_validate(payload)


def test_contradictory_physical_assumption_rejected_before_lean():
    instance = auditor('8', source_text='Ohm law: R = V/I.', updates={
        'assumptions':['The resistance of the heater remains constant at 100 ohms.'],
        'reason':'Apply Ohm law at constant resistance.',
        'calculation_expression':'(120*4)/60','answer_unit':'A'})
    result = instance.audit_question('The voltage is 60 V when it draws a current of 4 A. What current at 120 V?',
        source_id='book',before_position=100,background='arithmetic')
    assert result['status'] == 'REJECTED_ASSUMPTION'
    assert result['calculation_check']['consistent']
    assert result['assumption_consistency']['checks'][0]['resistance_from_question_ohms'] == '15'
    assert 'answer' not in result and 'lean' not in result
    assert result['judgment']['claimed_value'] == '8' and 'response' in result
