"""Bounded electrical and lens quantity mappings; not general physics QA."""
from fractions import Fraction
import re
from src.verification.assumption_consistency import NUMBER, VOLT, AMP, POINT, _value


def check_lens_mapping(question, claimed_value, answer_unit, cited_texts):
    """Require a cited reciprocal rule for single-lens power in SI units."""
    result = dict(status='NOT_ASSESSED', policy='single_lens_power_v1',
                  general_semantics_verified=False)
    if not re.search(r'\blens\b', question, re.I) or not re.search(r'\bpower\b', question, re.I):
        return result
    result['status'] = 'REVIEW_REQUIRED'
    # ponytail: literal rule sentences and explicit metre input only; equivalent
    # prose, alternate notation and compound lenses need separate reviewed rules.
    formulas = [line.strip() for text in cited_texts for line in re.split(r'(?<=[.;])\s+|\n+', text)
                if re.search(r'\bP\s*=', line)]
    rule = (r'(?:Lens power\s+)?P\s*=\s*1\s*/\s*f'
            r'(?:\s+when focal length f is in (?:metres|meters))?\s*[.;]?')
    if not formulas or not all(re.fullmatch(rule, line) for line in formulas):
        return {**result, 'reason': 'No unambiguous cited P = 1/f rule sentence'}
    if re.search(r'\b(?:not|incorrect|invalid|false|wrong|unreadable)\b', ' '.join(cited_texts), re.I):
        return {**result, 'reason': 'Cited lens rule has a negation or unreadable qualifier'}
    if re.search(r'\b(?:another|second|two|combination|combined|changes|approximately|about)\b', question, re.I):
        return {**result, 'reason': 'Multiple lenses, changing or approximate inputs require review'}
    bindings = list(re.finditer(r'\bfocal\s+length\s+(?:(?:of|is)\s+)?'
                               r'(?P<value>[+-]?\d+(?:\.\d+)?)\s*(?:m|metres?|meters?)\b', question, re.I))
    if len(bindings) != 1:
        return {**result, 'reason': 'Requires one explicit signed focal length in metres'}
    if answer_unit.strip().lower() not in {'d', 'dioptre', 'dioptres', 'diopter', 'diopters'}:
        return {**result, 'reason': 'Expected lens power in dioptres'}
    focal = Fraction(bindings[0]['value'])
    if focal == 0:
        return {**result, 'reason': 'Zero focal length is outside the reciprocal rule'}
    expected = 1 / focal
    return {**result, 'status': 'MATCH_WITHIN_SCOPE' if Fraction(claimed_value) == expected else 'CONTRADICTION',
            'cited_formula_lines': formulas, 'question_span': list(bindings[0].span()),
            'question_binding': bindings[0].group(), 'focal_length_metres': str(focal),
            'expected_power_dioptres': str(expected),
            'reason': 'Literal cited reciprocal rule and signed metre input; not general source entailment'}


def check_heater_mapping(question, claimed_value, answer_unit, cited_texts, condition):
    """Check I2=I1*V2/V1 only when the condition guard recognizes this task."""
    result = dict(status='NOT_ASSESSED', policy='two_voltage_current_mapping_v1',
                  general_semantics_verified=False)
    if condition['status'] == 'NOT_ASSESSED':
        return result
    result['status'] = 'REVIEW_REQUIRED'
    if condition['status'] not in {'CONDITION_STATED', 'CONDITION_REQUIRED'}:
        return {**result, 'reason': 'Operating condition is not established'}
    text = ' '.join(question.split())
    if re.search(r'\b(?:another|different|other|approximately|about|either|or)\b', text, re.I):
        return {**result, 'reason': 'Ambiguous device or approximate quantities'}
    if not any(re.fullmatch(r"(?:Ohm(?:'s)?law:)?(?:R=V/I|V=I\*?R|I=V/R)(?:\(\d+(?:\.\d+)*\))?[.;]?",
                           re.sub(r'\s+', '', line))
               for t in cited_texts for line in t.splitlines()):
        return {**result, 'reason': 'No standalone cited Ohm-law formula'}
    request = re.search(r'\b(?:what|find|calculate|determine)\b[\s\S]*?\bcurrent\b', text, re.I)
    if request is None:
        return {**result, 'reason': 'No unambiguous current request'}
    before, after = text[:request.start()], text[request.end():]
    points = list(POINT.finditer(before))
    points += list(re.finditer(rf'\bdraws\s+(?:a current of\s+)?(?P<i>{NUMBER})\s*(?P<iu>{AMP})\s+at\s+'
                              rf'(?P<v>{NUMBER})\s*(?P<vu>{VOLT})(?!\w)', before, re.I))
    targets = list(re.finditer(rf'\b(?:at|to)\s+(?P<v>{NUMBER})\s*(?P<vu>{VOLT})(?!\w)', after, re.I))
    if len(points) != 1 or len(targets) != 1:
        return {**result, 'reason': 'Cannot uniquely bind the initial operating point and requested voltage'}
    p, target = points[0], targets[0]
    if not re.fullmatch(rf'(?:{AMP})', answer_unit.strip(), re.I):
        return {**result, 'reason': 'Expected an explicit current unit'}
    try:
        v1, i1, v2 = _value(p['v'], p['vu']), _value(p['i'], p['iu']), _value(target['v'], target['vu'])
        actual = _value(claimed_value, answer_unit.strip())
    except (ValueError, ZeroDivisionError):
        return {**result, 'reason': 'Unsupported numeric representation'}
    if min(v1, i1, v2) <= 0:
        return {**result, 'reason': 'Nonpositive operating values require sign-convention review'}
    expected = i1*v2/v1
    return {**result, 'status': 'MATCH_WITHIN_SCOPE' if actual == expected else 'CONTRADICTION',
            'question_bindings': dict(initial_voltage_volts=str(v1), initial_current_amperes=str(i1),
                                      requested_voltage_volts=str(v2)),
            'initial_point_text': p.group(), 'requested_voltage_text': target.group(),
            'expected_current_amperes': str(expected), 'claimed_current_amperes': str(actual),
            'condition_status': condition['status'], 'relation': 'I2 = I1 * V2 / V1',
            'reason': 'Exact ratio check conditional on unchanged resistance; not verification of physical constancy'}


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
