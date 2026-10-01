import json
import pytest
from scripts.run_ncert_solver_revision import revised_request, validate_revised


def response(value='300', expression='0.5*10*60', claim='300'):
    return dict(done=True, done_reason='stop', message=dict(content=json.dumps(dict(
        status='PASS', answer=value+' C', reason='Q=It, converting minutes to seconds.',
        numeric_value=value, answer_unit='C', arithmetic_checks=[dict(expression=expression, claimed_value=claim)]))))


def test_direct_solver_checks_arithmetic_and_final_scalar():
    body = revised_request(dict(target_raw='How much charge?', expected_answer='SECRET'))
    assert json.loads(body['messages'][1]['content']) == {'question': 'How much charge?'}
    assert 'SECRET' not in json.dumps(body)
    assert validate_revised(response())[0]['status'] == 'PASS'
    with pytest.raises(ValueError, match='Incorrect arithmetic'):
        validate_revised(response(claim='301'))
    with pytest.raises(ValueError, match='matching arithmetic'):
        validate_revised(response(value='301'))
    bad = response()
    bad['done_reason'] = 'length'
    with pytest.raises(ValueError, match='Incomplete'):
        validate_revised(bad)


def test_missing_data_is_preserved_and_conflicting_abstention_rejected():
    raw = response()
    answer = json.loads(raw['message']['content'])
    answer.update(status='ABSTAIN', answer='Unavailable', reason='Referenced dimensions are absent.',
                  numeric_value=None, answer_unit=None, arithmetic_checks=[])
    raw['message']['content'] = json.dumps(answer)
    assert validate_revised(raw)[0]['status'] == 'ABSTAIN'
    answer['answer'] = '300 C'
    raw['message']['content'] = json.dumps(answer)
    with pytest.raises(ValueError, match='Conflicting'):
        validate_revised(raw)
