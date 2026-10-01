"""Bounded work/charge/potential-difference mapping; not general physics QA."""
from fractions import Fraction
import re


def check_work_mapping(question, claimed_value, answer_unit, cited_texts):
    result = dict(status='NOT_ASSESSED', policy='single_charge_potential_work_v1',
                  general_semantics_verified=False)
    text = ' '.join(question.split())
    if not re.search(r'\b(?:work|energy)\b', text, re.I):
        return result
    # Only direct work-done questions, not force/displacement or multiple states.
    if not re.search(r'\bcharge\b', text, re.I) or not re.search(r'\bpotential difference\b', text, re.I):
        return result
    result['status'] = 'REVIEW_REQUIRED'
    if re.search(r'\b(?:not|negative|decreases?|changes?|varies|another|second|initial|final)\b', text, re.I):
        return {**result, 'reason': 'Negation or multiple operating conditions require review'}
    number = r'(\d+(?:\.\d+)?)'
    charge = list(re.finditer(r'(?<![\w.+-])'+number+r'\s*(?:C|coulombs?)\b', text))
    voltage = list(re.finditer(r'(?<![\w.+-])'+number+r'\s*(?:V|volts?)\b', text))
    if len(charge) != 1 or len(voltage) != 1:
        return {**result, 'reason': 'Requires exactly one positive charge and potential difference in C and V'}
    if not any(re.fullmatch(r'(?:V=W/Q|W=V\*?Q|W=Q\*?V)(?:\(\d+(?:\.\d+)*\))?[.;]?',
                            re.sub(r'\s+', '', line))
               for t in cited_texts for line in t.splitlines()):
        return {**result, 'reason': 'No explicit cited work-charge-potential formula'}
    if answer_unit.strip().lower() not in {'j', 'joule', 'joules'}:
        return {**result, 'reason': 'Expected work unit J for this bounded relation'}
    q, v = Fraction(charge[0][1]), Fraction(voltage[0][1])
    if q <= 0 or v <= 0:
        return {**result, 'reason': 'Nonpositive quantities require sign-convention review'}
    expected = q*v
    return {**result, 'status': 'MATCH_WITHIN_SCOPE' if Fraction(claimed_value) == expected else 'CONTRADICTION',
            'question_bindings': {'charge_coulombs': str(q), 'potential_difference_volts': str(v)},
            'source_spans': [list(charge[0].span()), list(voltage[0].span())],
            'span_text': text, 'expected_work_joules': str(expected),
            'reason': 'Question quantities bound by explicit units; W=VQ checked against cited relation'}
