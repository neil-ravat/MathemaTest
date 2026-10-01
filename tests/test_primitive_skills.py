import pytest
from src.verification.primitive_skills import explicit_operation_witness


def catalog(text):
    return [dict(evidence_id='B0',source='background',id='background',quote=text)]


@pytest.mark.parametrize('operation',['Addition','Subtraction','Multiplication','Division'])
@pytest.mark.parametrize('background',[
    'Arithmetic is known.',
    'Arithmetic, substitution into supplied formulas and elementary algebra are known. No subject-specific definitions or formulas are granted without source evidence.',
    'Rational arithmetic and elementary algebra are known. No other subject-specific rules are granted.'
])
def test_explicit_arithmetic_grants_all_four_numeric_operations(operation,background):
    w=explicit_operation_witness(operation+' of supplied numbers',catalog(background))
    assert w is not None and w.quote==background and w.basis=='STATED'


@pytest.mark.parametrize('background',[
    'Arithmetic is not known.', 'Only addition is known.',
    'Arithmetic is known. Division is explicitly excluded.',
    'Arithmetic is known except division.',
    'Arithmetic is known. Division is unfamiliar.',
    'Arithmetic is known for integers only.',
    'Arithmetic is known. No division is allowed.',
    'The chapter mentions arithmetic.',
    'Elementary algebra is known.',
    'Addition and multiplication are known.'
])
def test_restricted_unfamiliar_and_unparsed_profiles_are_not_auto_approved(background):
    assert explicit_operation_witness('Division of supplied numbers',catalog(background)) is None


@pytest.mark.parametrize('name',[
    'Formula for average speed','Polynomial long division algorithm',
    'Division by zero','Multiplication of matrices','Division of complex numbers',
    'Division of distance by time to find speed','Addition theorem for probabilities',
    'Division','Multiplication of values',
])
def test_ordinary_skill_matching_never_grants_a_subject_rule(name):
    assert explicit_operation_witness(name,catalog('Arithmetic is known.')) is None
