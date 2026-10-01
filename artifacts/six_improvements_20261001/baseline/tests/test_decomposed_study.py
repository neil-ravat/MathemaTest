"""Focused checks of evidence-to-decision rules and model-input isolation."""
import copy
import json

import pytest
from pydantic import ValidationError

from scripts.run_controlled_study import context_for, gate_cases
from scripts.run_decomposed_study import Evidence, EvidenceError, calculate, decide, DEST


def evidence(**changes):
    return dict(target_kind='equality', claimed_value=3, calculation='2 + 1',
                missing_prerequisites=[], cited_passage_ids=['bump'], reason='Substitute x=2.', **changes)


def test_decision_rules_on_all_seven_public_fixtures():
    records = {
        'earlier_definition': ('2+1', 3, [], ['bump'], 'PASS'),
        'future_definition': (None, 6, ['glim'], [], 'FAIL_GAP'),
        'same_chapter_prior': ('2*3', 6, [], ['glim'], 'PASS'),
        'later_definition': (None, 2, ['tilt'], [], 'FAIL_GAP'),
        'false_statement': ('2+1', 9, [], ['bump'], 'FAIL_LOGIC'),
        'background_knowledge': ('2+3', 5, [], [], 'PASS'),
        'intentional_preview': (None, None, [], [], 'PASS'),
    }
    for case in gate_cases():
        calculation, claimed, missing, citations, status = records[case['id']]
        e = evidence()
        e.update(target_kind='preview' if claimed is None else 'equality',
                 calculation=calculation, claimed_value=claimed,
                 missing_prerequisites=missing, cited_passage_ids=citations)
        p = context_for(case, 'complete')
        assert decide(e, p)[0]['status'] == status
        if missing:
            p['context_complete'] = False
            assert decide(e, p)[0]['status'] == 'ABSTAIN'


def test_reject_conflicting_or_inadmissible_evidence():
    payload = context_for(gate_cases()[0], 'complete')
    modifications = [
        {'claimed_value': 4},
        {'target_kind': 'preview', 'calculation': None, 'claimed_value': None},
        {'missing_prerequisites': ['unknown']},
        {'missing_prerequisites': [''], 'calculation': None},
        {'cited_passage_ids': ['glim']},  # a future fixture definition
        {'cited_passage_ids': ['invented']},
    ]
    for change in modifications:
        e = evidence(); e.update(change)
        with pytest.raises(EvidenceError):
            decide(e, payload)
    e = evidence(); e['status'] = 'PASS'
    with pytest.raises(ValidationError):
        decide(e, payload)
    e = evidence(); e['calculation'] = None
    assert decide(e, payload)[0]['status'] == 'ABSTAIN'
    e.update(target_kind='other', claimed_value=None, cited_passage_ids=[])
    payload['target'] = 'Prove a general theorem.'
    assert decide(e, payload)[0]['status'] == 'ABSTAIN'


@pytest.mark.parametrize('expression', [
    '__import__("os").getcwd()', 'True', 'x+1', '2**3', '6/2',
    '3.0', '999999999999999999', '1+', '1=' , '('*300+'1'+')'*300,
    '+'.join(['1']*200), '1'*2001,
])
def test_calculator_rejects_unsupported_or_unbounded_text(expression):
    with pytest.raises((EvidenceError, SyntaxError)):
        calculate(expression)


def test_numeric_calculation_and_metadata_do_not_choose_verdict():
    assert calculate('-(2 + 3) * (+4 - 1)') == -15
    cases = json.loads((DEST/'development.json').read_text())
    for case in cases:
        payload = context_for(case, 'complete')
        altered = copy.deepcopy(case)
        altered.update(expected='ABSTAIN', required_ids=['poison'], oracle={'claim': 'poison'},
                       category='poison', family='poison')
        assert context_for(altered, 'complete') == payload
        assert not {'expected', 'required_ids', 'oracle', 'family', 'category'} & payload.keys()
    payload = context_for(gate_cases()[0], 'complete')
    e = evidence()
    # The model's explanatory prose does not determine status.
    e['reason'] = 'This is FAIL_LOGIC, FAIL_GAP, and ABSTAIN.'
    verdict, computed = decide(e, payload)
    assert verdict['status'] == 'PASS' and computed == 3
    e['calculation'] = '2+2'
    verdict, computed = decide(e, payload)
    assert verdict['status'] == 'FAIL_LOGIC' and computed == 4
