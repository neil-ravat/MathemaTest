import pytest
from scripts.run_ncert_live_pipeline import validate_direct


def test_direct_pass_requires_an_answer_and_no_invented_citations():
    j = dict(status='PASS',cited_passage_ids=[],missing_prerequisites=[],
             calculation_expression='2*12',claimed_value='24',answer_unit='J')
    validate_direct(j)
    with pytest.raises(ValueError):
        validate_direct({**j,'claimed_value':None})
    with pytest.raises(ValueError):
        validate_direct({**j,'cited_passage_ids':['missing']})
    with pytest.raises(ValueError):
        validate_direct({**j,'claimed_value':'24 J'})
