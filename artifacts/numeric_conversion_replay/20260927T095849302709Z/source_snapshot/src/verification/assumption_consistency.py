"""Bounded electrical consistency checks; not a general physics verifier.

Only an explicit voltage/current operating point, a cited Ohm-law formula and
an unambiguous positive numeric resistance claim are checked. Other language is
reported as unchecked, never treated as verified by absence of a contradiction.
"""
from fractions import Fraction
import re

NUMBER = r'[+-]?(?:\d+(?:\.\d+)?|\.\d+)'
VOLT = r'(?-i:mV|kV|V)|volts?'
AMP = r'(?-i:mA|µA|μA|A)|amperes?|amps?'
OHM = r'(?-i:kΩ|Ω|Ω)|kiloohms?|ohms?'
POINT = re.compile(rf'(?<![\w.])(?P<v>{NUMBER})\s*(?P<vu>{VOLT})\s+when\s+'
                   rf'(?:it|the (?:heater|resistor|conductor))\s+draws\s+(?:a current of\s+)?'
                   rf'(?P<i>{NUMBER})\s*(?P<iu>{AMP})\b', re.I)
CLAIM = re.compile(rf'\bresistance\b[^.!?\n]{{0,100}}?(?<![\w.])(?P<r>{NUMBER})\s*'
                   rf'(?P<ru>{OHM})(?!\w)', re.I)
SCALES = {'mV':Fraction(1,1000), 'kV':Fraction(1000), 'mA':Fraction(1,1000),
          'µA':Fraction(1,1000000), 'μA':Fraction(1,1000000), 'kΩ':Fraction(1000),
          'kiloohm':Fraction(1000), 'kiloohms':Fraction(1000)}


def _value(text, unit):
    if len(text) > 30:
        raise ValueError('Numeric claim exceeds supported size')
    return Fraction(text) * SCALES.get(unit, SCALES.get(unit.lower(), Fraction(1)))


def check_assumption_consistency(question, reason, assumptions, cited_texts):
    result = dict(policy='electrical_operating_point_v1', status='NOT_ASSESSED',
                  checks=[], unchecked=[], all_assumptions_verified=False)
    sentences = [s.strip() for text in [reason, *assumptions]
                 for s in re.split(r'[.!?](?=\s|$)', text) if s.strip()]
    claims = []
    for sentence in sentences:
        matches = list(CLAIM.finditer(sentence))
        if not matches:
            result['unchecked'].append(sentence)
            continue
        if (len(matches) != 1 or re.search(r'\b(?:not|never|other|another|second|different|changes?|varies|vary|from|to|or|either|between|approximately|about|roughly|nearly|if|could|might|would|were|rises?|falls?|becomes?|increases?|decreases?|higher|lower|heated|cooled|after)\b', sentence, re.I)):
            result['unchecked'].append(sentence)
            continue
        claims.append((sentence, matches[0]))
    if not claims:
        result['reason'] = 'No unambiguous positive numeric resistance claim recognized'
        return result
    # Only current cited evidence authorizes the relation; no assumed external law.
    supported = any(re.search(r'R=V/I|V=IR', re.sub(r'\s+', '', text)) for text in cited_texts)
    points = list(POINT.finditer(question))
    changing_state = re.search(r'\b(?:heated|cooled)\b|\b(?:resistance|temperature)\b[^.!?]{0,40}\b(?:changes?|becomes?|increases?|decreases?)\b', question, re.I)
    if not supported or len(points) != 1 or changing_state:
        result['reason'] = 'Requires one explicit operating point, no explicit state change, and a cited R=V/I or V=IR formula'
        result['unchecked'].extend(s for s, _ in claims)
        return result
    point = points[0]
    try:
        voltage = _value(point['v'], point['vu'])
        current = _value(point['i'], point['iu'])
        if current == 0:
            raise ValueError('Zero current cannot establish finite resistance by division')
        expected = voltage/current
        for sentence, match in claims:
            actual = _value(match['r'], match['ru'])
            result['checks'].append(dict(claim=sentence, question_operating_point=point.group(),
                voltage_volts=str(voltage), current_amperes=str(current),
                resistance_from_question_ohms=str(expected), stated_resistance_ohms=str(actual),
                consistent=actual == expected))
    except ValueError as exc:
        result['reason'] = str(exc)
        result['checks'] = []
        result['unchecked'].extend(s for s, _ in claims)
        return result
    result['status'] = 'CONSISTENT_WITHIN_SCOPE' if all(c['consistent'] for c in result['checks']) else 'CONTRADICTION'
    return result


def check_resistance_condition(question, cited_texts):
    """Flag bounded two-voltage heater/resistor current questions.

    Checks whether unchanged resistance is *stated*, never whether it is physically
    true. Background/model assertions cannot silently supply a question condition.
    Other question forms remain unassessed; this is not a general assumption solver.
    """
    result = dict(policy='two_voltage_resistance_condition_v1', status='NOT_ASSESSED',
                  physical_conditions_verified=False)
    voltages = list(re.finditer(rf'(?<![\w.]){NUMBER}\s*(?:{VOLT})(?!\w)', question, re.I))
    currents = list(re.finditer(rf'(?<![\w.]){NUMBER}\s*(?:{AMP})(?!\w)', question, re.I))
    if (not re.search(r'\b(?:heater|resistor|conductor)\b', question, re.I)
            or not re.search(r'\b(?:what|find|calculate|determine)\b[\s\S]*\bcurrent\b', question, re.I)
            or len(voltages) < 2):
        return result
    if len(voltages) != 2 or len(currents) != 1:
        return {**result, 'status':'REVIEW_REQUIRED', 'reason':'Ambiguous or multiple operating points'}
    if not any(re.search(r'R=V/I|V=IR|I=V/R', re.sub(r'\s+', '', text)) for text in cited_texts):
        return {**result, 'status':'REVIEW_REQUIRED', 'reason':'No explicit cited Ohm-law relationship'}
    # Conservative: contradictory or interrogative condition statements require review.
    if re.search(r'\b(?:not|never|heated|cooled|unless)\b|\b(?:resistance|temperature)\b[^.!?]{0,45}'
                 r'\b(?:changes?|varies|vary|increases?|decreases?|doubles?|halves?)\b', question, re.I):
        return {**result, 'status':'REVIEW_REQUIRED', 'reason':'Negated, changing or conditional operating state'}
    stated = re.search(r'\bresistance\s+(?:remains?|stays?|is|is assumed to be)\s+(?:constant|unchanged|the same)\b|'
                       r'\b(?:constant|unchanged)\s+resistance\b', question, re.I)
    if stated:
        sentence_start = max(question.rfind(p, 0, stated.start()) for p in '.!?') + 1
        following = re.search(r'[.!?]', question[stated.end():])
        sentence_end = stated.end()+following.end() if following else len(question)
        clause = question[sentence_start:sentence_end]
        if clause.rstrip().endswith('?') and re.search(r'\b(?:does|is|will|could|might|whether)\b[^.!?]*\bresistance\b', clause, re.I):
            return {**result, 'status':'REVIEW_REQUIRED', 'reason':'Resistance constancy is asked, not asserted'}
        return {**result, 'status':'CONDITION_STATED', 'source_phrase':stated.group()}
    return {**result, 'status':'CONDITION_REQUIRED',
            'condition':'The heater/resistor resistance remains unchanged between the two operating points.',
            'reason':'The numerical transfer requires an unstated unchanged-resistance assumption'}
