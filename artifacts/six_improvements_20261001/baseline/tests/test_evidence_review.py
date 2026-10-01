import pytest
from scripts.build_evidence_review import validate_groups, block


def test_related_variants_and_exposed_cases_cannot_leak_into_test():
    a=dict(id='a',split='development',groups=['ap'],exposed=True)
    assert validate_groups([a])['test_cases']==0
    with pytest.raises(ValueError,match='Group crosses'):
        validate_groups([a,dict(id='b',split='test',groups=['ap'],exposed=False)])
    with pytest.raises(ValueError,match='Exposed'):
        validate_groups([{**a,'split':'test'}])
    with pytest.raises(ValueError,match='grouping'):
        validate_groups([{**a,'groups':[]}])


def test_model_markdown_remains_inside_a_literal_block():
    assert block('```\n![image](url)\n```').startswith('````\n')
