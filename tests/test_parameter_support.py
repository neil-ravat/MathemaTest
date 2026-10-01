from src.verification.parameter_support import check_numeric_inputs, guard_gap_claim
from tests.test_question_audit import auditor
import pytest


def test_missing_parameter_cannot_be_supplied_by_model_reasoning():
    result = auditor('30', source_text='G(x) = k * x.', updates={
        'calculation_expression': '5*6', 'reason': 'Assume k = 5.',
        'assumptions': ['k = 5'], 'answer_unit': 'units'}).audit_question(
        'Compute G for x = 6.', source_id='book', before_position=100, background='Integer arithmetic.')
    assert result['status'] == 'SOURCE_REVIEW_REQUIRED'
    assert result['numeric_input_support']['unsupported_literals'] == ['5']
    assert 'answer' not in result and 'lean' not in result


def test_explicit_inputs_and_expanded_derivation_pass_necessary_check():
    result = check_numeric_inputs('120/(60/4)', '60 V, 4 A, then 120 V.', '', ['I = V/R.'])
    assert result['status'] == 'LITERALS_PRESENT'
    assert not result['parameter_meanings_verified']
    assert check_numeric_inputs('120/15', '60 V, 4 A, then 120 V.', '', [])['unsupported_literals'] == ['15']


def test_ids_are_not_numeric_evidence_and_decimal_sentence_end_works():
    assert check_numeric_inputs('3*6', 'x = 6.', '', ['See d3.'])['unsupported_literals'] == ['3']
    assert check_numeric_inputs('.5*10*60', '0.5 A for 10 minutes.', '60 seconds per minute.', [])['status'] == 'LITERALS_PRESENT'


def test_gap_guard_uses_caller_scope_for_both_schemas():
    assert guard_gap_claim('FAIL_GAP', 'Missing rule')[0] == 'ABSTAIN'
    assert guard_gap_claim('CONTROLLED_GAP', 'Missing rule')[0] == 'UNCERTAIN'
    assert guard_gap_claim('FAIL_LOGIC', 'Contradiction')[0] == 'FAIL_LOGIC'
    assert guard_gap_claim('CONTROLLED_GAP', 'Missing rule', context_complete=True)[0] == 'CONTROLLED_GAP'


QUESTION = 'A current of 0.5 A flows for 10 minutes. Find the charge.'
BACKGROUND = 'Rational arithmetic; 1 minute = 60 seconds; SI units.'


def test_logged_conversion_accepts_saved_shape_and_application():
    r = check_numeric_inputs('0.5*600', QUESTION, BACKGROUND, [])
    assert r['status'] == 'INPUTS_SUPPORTED_BY_CONVERSION'
    assert r['verified_conversions'][0]['result_seconds'] == '600'
    assert r['verified_conversions'][0]['input_minutes'] == '10'
    out = auditor(updates={'calculation_expression':'0.5*600'}).audit_question(
        QUESTION,source_id='book',before_position=100,background=BACKGROUND)
    assert out['status']=='ARITHMETIC_CHECKED' and out['answer']=='300 C'
    assert not out['units_verified']


@pytest.mark.parametrize('expression,question,background', [
    ('0.5*601',QUESTION,BACKGROUND),
    ('600/0.5',QUESTION,BACKGROUND),
    ('0.5+600',QUESTION,BACKGROUND),
    ('0.5*600','A current of 0.5 A flows for 9 minutes. Find the charge.',BACKGROUND),
    ('0.5*600',QUESTION,'Arithmetic'),
    ('0.5*600',QUESTION,'Do not assume 1 minute = 60 seconds'),
    ('0.5*600',QUESTION+' Another interval lasts 5 minutes.',BACKGROUND),
    ('0.5*600',QUESTION+' The current varies.',BACKGROUND),
    ('0.5*600','A current of 0.5 A flows for -10 minutes. Find the charge.',BACKGROUND),
])
def test_conversion_does_not_authorize_arbitrary_or_ambiguous_inputs(expression,question,background):
    assert check_numeric_inputs(expression,question,background,[])['status']=='SOURCE_REVIEW_REQUIRED'


def test_fractional_minutes_and_reversed_product():
    r=check_numeric_inputs('90*0.5','0.5 A flows for 1.5 minutes. Find the charge.',BACKGROUND,[])
    assert r['status']=='INPUTS_SUPPORTED_BY_CONVERSION'
    assert r['verified_conversions'][0]['result_seconds']=='90'


def test_native_heading_and_wrapped_duration_do_not_create_an_extra_current():
    question='Example 11.1\nA current of 0.5 A flows for 10\n minutes. Find the charge.'
    r=check_numeric_inputs('(0.5 * 600)',question,BACKGROUND,[])
    assert r['status']=='INPUTS_SUPPORTED_BY_CONVERSION'


@pytest.mark.parametrize('ordinal,value', [('7th','7'),('11th','11'),('12th','12'),('13th','13'),('21st','21'),('22nd','22'),('23rd','23')])
def test_question_ordinals_have_logged_numeric_provenance(ordinal,value):
    result=check_numeric_inputs(value,f'Find the {ordinal} term.','',[])
    assert result['status']=='LITERALS_PRESENT'
    assert result['recognized_ordinals'][0]['value']==value


@pytest.mark.parametrize('text',['11st','7thitem','doc7th','-7th','0th'])
def test_invalid_or_embedded_ordinals_do_not_supply_numbers(text):
    assert check_numeric_inputs('7',text,'',[])['status']=='SOURCE_REVIEW_REQUIRED'
