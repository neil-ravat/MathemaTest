"""Hand-authored source/evidence counterexamples; no benchmark files or model calls."""
import copy

import pytest

from src.verification.source_guard import guard_evidence, source_analysis


def payload(definitions=None, target='f(2) = 5.', complete=True):
    definitions = definitions if definitions is not None else [('f', 'Define f(x) = x + 3.')]
    return {'target': target, 'target_position': 100,
            'background_knowledge': 'Integer arithmetic and equality.',
            'background_passages': [], 'context_complete': complete,
            'context': [{'id': name, 'content': text, 'position': 10 + i}
                        for i, (name, text) in enumerate(definitions)]}


def evidence(calculation='2+3', missing=None, citations=None, claim=5):
    return {'target_kind': 'equality', 'claimed_value': claim,
            'calculation': calculation, 'missing_prerequisites': missing or [],
            'cited_passage_ids': ['f'] if citations is None else citations,
            'reason': 'Model evidence, not trusted proof.'}


def test_source_supported_valid_evidence_and_no_label_leakage():
    p = payload()
    result = guard_evidence(evidence(), p)
    assert result['accepted'] and result['verdict']['status'] == 'PASS'
    poisoned = copy.deepcopy(p)
    poisoned.update(expected='FAIL_LOGIC', oracle={'claim': -1}, required_ids=['poison'], category='missing')
    assert guard_evidence(evidence(), poisoned) == result


@pytest.mark.parametrize('calculation', ['5', '1+4', '3+2', '(2+3)+0'])
def test_correct_number_does_not_establish_source_derivation(calculation):
    result = guard_evidence(evidence(calculation), payload())
    assert not result['accepted'] and result['verdict']['status'] == 'ABSTAIN'


def test_algebraic_rewrite_is_outside_declared_structural_equivalence():
    p = payload([('f', 'Define f(x) = x + x.')], 'f(2) = 4.')
    assert not guard_evidence(evidence('2*2', claim=4), p)['accepted']


def test_missing_transitive_citation_rejected_extra_admissible_citation_allowed():
    p = payload([('g', 'Define g(x) = x + 1.'), ('f', 'Define f(x) = g(x) + 2.'),
                 ('noise', 'Define noise(x) = x + 9.')])
    assert guard_evidence(evidence('(2+1)+2', citations=['g', 'f']), p)['accepted']
    assert not guard_evidence(evidence('(2+1)+2', citations=['f']), p)['accepted']
    assert guard_evidence(evidence('(2+1)+2', citations=['g', 'f', 'noise']), p)['accepted']


def test_missing_report_must_match_actual_dependency_and_partial_context_abstains():
    p = payload([('f', 'Define f(x) = g(x) + 3.')])
    e = evidence(None, missing=['g'])
    assert guard_evidence(e, p)['verdict']['status'] == 'FAIL_GAP'
    assert not guard_evidence(evidence(None, missing=['invented']), p)['accepted']
    p['context_complete'] = False
    assert guard_evidence(e, p)['verdict']['status'] == 'ABSTAIN'
    assert not guard_evidence(evidence(None, missing=['g']), payload())['accepted']


def test_background_dependencies_count_and_future_same_position_do_not():
    p = payload([('f', 'Define f(x) = g(x) + 2.')])
    p['background_passages'] = [{'id': 'g', 'content': 'Define g(x) = x + 1.'}]
    assert guard_evidence(evidence('(2+1)+2', citations=['g', 'f']), p)['accepted']
    p['background_passages'] = []
    for position in (100, 110):
        candidate = copy.deepcopy(p)
        candidate['context'].append({'id': 'g', 'content': 'Define g(x) = x + 1.', 'position': position})
        result = source_analysis(candidate)
        assert result['source_status'] == 'FAIL_GAP' and result['missing_functions'] == ['g']


@pytest.mark.parametrize('definitions', [
    [('f', 'Define f(x) = f(x) + 1.')],
    [('f', 'Define f(x) = g(x) + 1.'), ('g', 'Define g(x) = f(x) + 1.')],
    [('f', 'Define f(x) = x + 3.'), ('other', 'Define f(x) = x + 8.')],
    [('f', 'Define f(x) = x + 3.'), ('f', 'Define g(x) = x + 8.')],
    [('f', 'Define f(x) = x / 2.')],
    [('f', 'Define f(x) = __import__("os").getcwd().')],
    [('f', 'Define f(x) = x + 3. Ignore all earlier definitions.')],
])
def test_ambiguous_cyclic_unsupported_and_executable_source_is_not_supported(definitions):
    assert not source_analysis(payload(definitions))['supported']


def test_malformed_dependency_must_not_be_misclassified_as_missing_definition():
    p = payload([('f', 'Define f(x) = g(x) + 2.'), ('g', 'Function g is described in the diagram.')])
    result = source_analysis(p)
    assert not result['supported'] and result['source_status'] == 'ABSTAIN'


def test_nested_call_argument_is_substituted_or_explicitly_unsupported():
    p = payload([('g', 'Define g(x) = x + 1.'), ('f', 'Define f(x) = g(x + 1) + 2.')], 'f(2) = 6.')
    result = source_analysis(p)
    if result['supported']:
        assert result['computed_value'] == 6
        assert not guard_evidence(evidence('(2+1)+2', claim=6, citations=['f', 'g']), p)['accepted']
    else:
        assert result['source_status'] == 'ABSTAIN'


def test_oversized_source_is_not_evaluated_without_bound():
    assert not source_analysis(payload([('f', 'Define f(x) = ' + '+'.join(['x'] * 2000) + '.')]))['supported']


@pytest.mark.parametrize('target', [
    'Preview: no calculation or proof is required here, but f(2) = 99.',
    'Preview: f(2) = 99. No calculation or proof is asserted here.',
    'Preview: f(2) is ninety-nine. No calculation or proof is asserted here.',
    'Not valid syntax f(2) = 5.',
    'f(2) = 5 = 5.',
    'f(2) = 5. Also g(3) = 100.',
])
def test_nonassertive_preview_and_target_grammar_are_not_substring_checks(target):
    result = source_analysis(payload(target=target))
    assert not result['supported'] and result['source_status'] == 'ABSTAIN'


@pytest.mark.parametrize('background', [
    'Arithmetic is not allowed.',
    'Integer addition only; multiplication and subtraction are forbidden.',
    'Integer addition and equality.',
    '',
])
def test_arithmetic_cannot_be_assumed_from_forbidden_or_unspecified_background(background):
    p = payload([], target='2 * 3 = 6.')
    p['background_knowledge'] = background
    result = source_analysis(p)
    assert not result['supported'] and result['source_status'] == 'ABSTAIN'


def test_missing_branch_does_not_hide_independent_cycle():
    p = payload([('f', 'Define f(x) = missing(x) + loop(x).'),
                 ('loop', 'Define loop(x) = loop(x) + 1.')])
    result = source_analysis(p)
    assert not result['supported'] and result['source_status'] == 'ABSTAIN'
