"""Necessary numeric-input check, not semantic parameter verification.

Keep derived values expanded in the calculation. A matching number may refer to
another quantity/state, so presence never certifies a correct substitution.
"""
import ast
from fractions import Fraction
import re


def guard_gap_claim(status, reason, *, context_complete=False):
    """Completeness is caller provenance, never a model assertion."""
    if not context_complete and status in {'FAIL_GAP', 'CONTROLLED_GAP'}:
        return ('ABSTAIN' if status == 'FAIL_GAP' else 'UNCERTAIN',
                'Incomplete retrieved context cannot establish a pedagogical gap. Candidate missing support: ' + reason)
    return status, reason


def _charge_time_conversion(tree, question, background):
    """Recognize only I * converted_seconds with one stated current and duration.

    No model explanation supplies conversion evidence. Require an explicit,
    standalone conversion clause in the caller's declared background.
    """
    clauses = re.split(r'[;\n]', background)
    conversion = next((c.strip().rstrip('.') for c in clauses if re.fullmatch(
        r'\s*1 minute = 60 seconds\.?\s*', c)), None)
    if conversion is None or not re.search(r'\b(?:find|calculate|what)\b[\s\S]*\bcharge\b', question, re.I):
        return []
    if re.search(r'\b(?:not|negative|varies|varying|changes?|another|each|respectively|initial|final|approximately|about)\b', question, re.I):
        return []
    number = r'(\d+(?:\.\d+)?)'
    # Do not combine a numbered heading with the article "A" on the next line.
    currents = list(re.finditer(r'(?<![\w.+-])'+number+r'[ \t]*(?:A|amperes?)\b', question))
    times = list(re.finditer(r'(?<![\w.+-])'+number+r'\s+minutes?\b', question, re.I))
    if len(currents) != 1 or len(times) != 1 or re.search(r'\b(?:seconds?|hours?)\b', question, re.I):
        return []
    current, minutes = Fraction(currents[0][1]), Fraction(times[0][1])
    if current <= 0 or minutes <= 0:
        return []
    node = tree.body
    if not (isinstance(node, ast.BinOp) and isinstance(node.op, ast.Mult)
            and all(isinstance(n, ast.Constant) and type(n.value) in (int, float)
                    for n in (node.left, node.right))):
        return []
    seconds = minutes * 60
    return [dict(kind='minutes_to_seconds', input_minutes=str(minutes), factor='60',
                 result_seconds=str(seconds), current_amperes=str(current),
                 question_time_span=list(times[0].span()), question_current_span=list(currents[0].span()),
                 background_clause=conversion)]


def check_numeric_inputs(expression, question, background, cited_texts):
    tree = ast.parse(expression, mode='eval')
    used = {Fraction(ast.get_source_segment(expression, n)) for n in ast.walk(tree)
            if isinstance(n, ast.Constant) and type(n.value) in (int, float)}
    # Ignore passage IDs, equation indices attached to letters, and model reasoning.
    available = set()
    for text in [question, background, *cited_texts]:
        available.update(Fraction(m.group()) for m in re.finditer(
            r'(?<![\w.])(?:\d+(?:\.\d+)?|\.\d+)(?!\w|\.\d)', text))
    ordinals = []
    for match in re.finditer(r'(?<![\w.+-])(\d+)(st|nd|rd|th)\b', question, re.I):
        number = int(match[1])
        suffix = 'th' if 10 <= number % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(number % 10,'th')
        if number > 0 and match[2].lower() == suffix:
            available.add(Fraction(number))
            ordinals.append(dict(text=match.group(), value=str(number), question_span=list(match.span())))
    derivations = _charge_time_conversion(tree, question, background)
    if derivations:
        d = derivations[0]
        node = tree.body
        operands = sorted(Fraction(ast.get_source_segment(expression, n)) for n in (node.left, node.right))
        if operands != sorted([Fraction(d['current_amperes']), Fraction(d['result_seconds'])]):
            derivations = []
    derived = {Fraction(d['result_seconds']) for d in derivations}
    missing = sorted(used - available - derived)
    status = 'SOURCE_REVIEW_REQUIRED' if missing else 'INPUTS_SUPPORTED_BY_CONVERSION' if used-available else 'LITERALS_PRESENT'
    return dict(status=status, verified_conversions=derivations, recognized_ordinals=ordinals,
                unsupported_literals=[str(v) for v in missing],
                parameter_meanings_verified=False,
                reason='Every calculation input must occur in the question, declared background or cited source. '
                       'A bounded current-times-duration form may use a logged minute-to-second derivation. '
                       'Numeric occurrence does not verify quantity identity, operating state or formula applicability.')
