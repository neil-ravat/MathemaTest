import pytest
from src.verification.assumption_consistency import check_assumption_consistency

QUESTION = 'The voltage is 60 V when it draws a current of 4 A. What current at 120 V?'


def check(claim, question=QUESTION, evidence='R = V/I'):
    return check_assumption_consistency(question, '', [claim], [evidence])


@pytest.mark.parametrize('v,i,r,expected', [('60','4','100','CONTRADICTION'),
    ('60','4','15','CONSISTENT_WITHIN_SCOPE'),('24','2','12','CONSISTENT_WITHIN_SCOPE'),
    ('24','2','15','CONTRADICTION'),('9','0.5','18','CONSISTENT_WITHIN_SCOPE')])
def test_operating_point_not_hardcoded(v,i,r,expected):
    result=check(f'The resistance is {r} ohms.',f'The voltage is {v} V when it draws {i} A.')
    assert result['status']==expected
    assert result['all_assumptions_verified'] is False


def test_milliampere_and_kiloohm_conversion():
    assert check('The resistance remains constant at 15 kΩ.',
                 'The voltage is 60 V when it draws 4 mA.')['status']=='CONSISTENT_WITHIN_SCOPE'


@pytest.mark.parametrize('claim', ['Resistance stays constant.', 'The resistance is not 100 ohms.',
    'Another resistor has resistance 100 ohms.', 'The resistance changes from 15 ohms to 100 ohms.',
    'The resistance is approximately 15 ohms.', 'If the resistance were 100 ohms.',
    'The resistance is 15 ohms or 100 ohms.', 'The resistance becomes 100 ohms after heating.'])
def test_unsupported_or_ambiguous_language_not_certified(claim):
    result=check(claim)
    assert result['status']=='NOT_ASSESSED' and result['unchecked']


def test_missing_law_multiple_points_zero_current_and_unknown_units_not_certified():
    assert check('Resistance is 100 ohms.', evidence='Voltage and current are mentioned.')['status']=='NOT_ASSESSED'
    for question in [QUESTION+' Another device has 10 V when it draws 2 A.',
                     'There is 60 V when it draws 0 A.',
                     'There is 60 MV when it draws 4 A.',
                     QUESTION+' The resistance changes to 100 ohms.']:
        assert check('Resistance is 100 ohms.',question)['status']=='NOT_ASSESSED'
