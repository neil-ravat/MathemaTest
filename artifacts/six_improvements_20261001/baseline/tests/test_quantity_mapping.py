import pytest
from src.verification.quantity_mapping import check_work_mapping
from tests.test_question_audit import auditor
from src.verification.quantity_mapping import check_heater_mapping
from src.verification.quantity_mapping import check_lens_mapping
from src.verification.assumption_consistency import check_resistance_condition

QUESTION = 'How much work is done moving a charge of 2 C across a potential difference 12 V?'


@pytest.mark.parametrize('source,value,unit,question,status', [
    ('P = 1/f', '4', 'D', '+0.25 m', 'MATCH_WITHIN_SCOPE'),
    ('Lens power P = 1/f when focal length f is in metres. The power unit is the dioptre (D).',
     '4', 'D', '+0.25 m', 'MATCH_WITHIN_SCOPE'),
    ('P = 1/f', '-4', 'D', '-0.25 m', 'MATCH_WITHIN_SCOPE'),
    ('P = 1/f', '0.25', 'D', '+0.25 m', 'CONTRADICTION'),
    ('Focal length is a distance.', '4', 'D', '+0.25 m', 'REVIEW_REQUIRED'),
    ('P = [unreadable symbol]/f', '4', 'D', '+0.25 m', 'REVIEW_REQUIRED'),
    ('It is not true that P = 1/f', '4', 'D', '+0.25 m', 'REVIEW_REQUIRED'),
    ('Incorrect formula:\nP = 1/f', '4', 'D', '+0.25 m', 'REVIEW_REQUIRED'),
    ('P = 2/f\nP = 1/f', '4', 'D', '+0.25 m', 'REVIEW_REQUIRED'),
    ('P = 1/f', '4', 'D', '+0.25 seconds', 'REVIEW_REQUIRED'),
    ('P = 1/f', '4', 'D', '25 cm', 'REVIEW_REQUIRED'),
    ('P = 1/f', '4', 'J', '+0.25 m', 'REVIEW_REQUIRED'),
    ('P = 1/f', '4', 'D', '0 m', 'REVIEW_REQUIRED'),
])
def test_lens_source_rule_and_quantity_boundary(source, value, unit, question, status):
    result = check_lens_mapping('A lens has focal length '+question+'. Find its power.', value, unit, [source])
    assert result['status'] == status
    assert result['general_semantics_verified'] is False


@pytest.mark.parametrize('source', ['Focal length is a distance.', 'P = [unreadable symbol]/f'])
def test_unsupported_lens_completion_stops_before_lean(source):
    instance = auditor('4', source_text=source, updates={
        'calculation_expression': '1/0.25', 'answer_unit': 'D'})
    result = instance.audit_question('A lens has focal length +0.25 m. Find its power.',
                                    source_id='book', before_position=100, background='Arithmetic')
    assert result['calculation_check']['consistent']
    assert result['status'] == 'QUANTITY_REVIEW_REQUIRED'
    assert 'answer' not in result and 'lean' not in result


@pytest.mark.parametrize('claim,unit,source,status', [
    ('24','J','V = W/Q.','MATCH_WITHIN_SCOPE'),
    ('6','J','V = W/Q.','CONTRADICTION'),
    ('24','C','V = W/Q.','REVIEW_REQUIRED'),
    ('24','J','Some other example has work 24 J.','REVIEW_REQUIRED'),
    ('24','J','It is not true that V=W/Q.','REVIEW_REQUIRED'),
])
def test_bound_relation(claim,unit,source,status):
    assert check_work_mapping(QUESTION,claim,unit,[source])['status'] == status


def test_arithmetic_correct_but_wrong_formula_stops_before_answer():
    instance = auditor('6',source_text='V = W/Q.',updates={
        'calculation_expression':'12/2','answer_unit':'J','reason':'Divide voltage by charge.'})
    result = instance.audit_question(QUESTION,source_id='book',before_position=100,background='Arithmetic')
    assert result['status'] == 'QUANTITY_REVIEW_REQUIRED'
    assert result['calculation_check']['consistent']
    assert 'answer' not in result and 'lean' not in result


def test_multiple_states_require_review():
    assert check_work_mapping(QUESTION+' Another charge is 3 C.','24','J',['V=W/Q.'])['status']=='REVIEW_REQUIRED'


HEATER = 'A heater draws 2 A at 30 V. Find its current at 90 V.'


@pytest.mark.parametrize('question,claim,unit,source,status', [
    (HEATER+' Assume constant resistance.','6','A','I = V/R','MATCH_WITHIN_SCOPE'),
    (HEATER,'6','A','I = V/R','MATCH_WITHIN_SCOPE'),
    (HEATER,'2/3','A','I = V/R','CONTRADICTION'),
    (HEATER,'6','V','I = V/R','REVIEW_REQUIRED'),
    (HEATER,'6','A','It is not true that I = V/R','REVIEW_REQUIRED'),
    (HEATER+' Resistance changes.','6','A','I = V/R','REVIEW_REQUIRED'),
    ('A heater draws 200 mA at 30 V. Find its current at 90 V.','600','mA','I = V/R','MATCH_WITHIN_SCOPE'),
    ('A heater is at 30 V when it draws a current of 2 A. What current will it draw at 90 V?','6','A','V = IR','MATCH_WITHIN_SCOPE'),
    ('A heater draws 2 A at 0 V. Find its current at 90 V.','6','A','I = V/R','REVIEW_REQUIRED'),
    ('A heater draws 2 A at 30 V. Find another heater current at 90 V.','6','A','I = V/R','REVIEW_REQUIRED'),
])
def test_heater_mapping_is_bounded(question,claim,unit,source,status):
    condition=check_resistance_condition(question,[source])
    assert check_heater_mapping(question,claim,unit,[source],condition)['status']==status


def test_exact_inverted_ratio_rejected_before_lean():
    instance=auditor('2/3',source_text='I = V/R',updates={
        'calculation_expression':'(30*2)/90','answer_unit':'A','reason':'Use the voltage ratio.'})
    result=instance.audit_question(HEATER+' Assume constant resistance.',
        source_id='book',before_position=100,background='Arithmetic')
    assert result['calculation_check']['consistent']
    assert result['status']=='QUANTITY_REVIEW_REQUIRED'
    assert result['heater_quantity_mapping']['expected_current_amperes']=='6'
    assert 'answer' not in result and 'lean' not in result
