import pytest

from src.verification.rational_calculator import check_calculation


@pytest.mark.parametrize('expression,claim,result', [
    ('0.5*10*60', '300', '300'),
    ('0.1+0.2', '0.3', '3/10'),
    ('-(3+1)/2', '-2', '-2'),
    ('1/(2/3)', '3/2', '3/2'),
    ('1/-2', '-0.5', '-1/2'),
    ('+(.25)/(-.5)', '1/-2', '-1/2'),
])
def test_exact_arithmetic_and_original_expression_proof(expression, claim, result):
    checked = check_calculation(expression, claim)
    assert checked['consistent'] and checked['exact_result'] == result
    assert ': Int)' in checked['lean_code'] and 'by decide' in checked['lean_code']


def test_false_claim_is_not_replaced_by_computed_tautology():
    checked = check_calculation('0.5*10*60', '2')
    assert checked['exact_result'] == '300' and not checked['consistent']
    assert '(10 : Int)' in checked['lean_code'] and '(60 : Int)' in checked['lean_code']
    assert '(300 : Int)' not in checked['lean_code']


@pytest.mark.parametrize('expression', [
    '__import__("os").system("echo unsafe")', 'x+1', '(1).real', '2**3',
    '1//2', 'True+1', '1/(2-2)', '1000000000001', '0.0000000000001',
    '1000000000000*2/2', '1e3', '0xff', '1_000', '1+'*100+'1', '1'*2001,
])
def test_rejects_unsupported_or_unbounded_expressions(expression):
    with pytest.raises(ValueError):
        check_calculation(expression, '1')


@pytest.mark.parametrize('claim', ['1+1', 'x', '1/0', 'nan', 'inf', '1e3', '(1)', '1/2/3'])
def test_claim_is_only_numeric(claim):
    with pytest.raises(ValueError):
        check_calculation('1', claim)
