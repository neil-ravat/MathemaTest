from scripts.run_transfer_diagnostic import score


def test_errors_and_wrong_answer_forms_are_not_reference_matches():
    case = dict(expected='answer',value='6',units=['a'])
    result = dict(status='ARITHMETIC_CHECKED',judgment=dict(claimed_value='6',answer_unit='A'))
    assert score(case,result)
    assert not score(case,{**result,'status':'CONDITIONAL_ANSWER'})
    assert not score(case,{**result,'judgment':dict(claimed_value='6',answer_unit='V')})
    assert score(dict(expected='withhold'),dict(status='ABSTAIN'))
    assert not score(dict(expected='withhold'),dict(status='ERROR'))
    assert not score(dict(expected='withhold'),dict(status='ABSTAIN',answer='6 A'))
    assert not score(dict(expected='withhold'),dict(status='ABSTAIN',output_validation={'valid':False}))
