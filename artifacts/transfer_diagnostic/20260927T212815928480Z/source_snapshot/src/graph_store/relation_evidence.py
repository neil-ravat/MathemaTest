"""Conservative lexical witnesses, not general semantic verification.

Unknown wording is quarantined. This trades coverage for explicit directional
source support; it does not validate the source's truth or entity descriptions.
"""
import re


VERBS = {
    'MEASURES': r'(?:measures|is used to measure)',
    'FLOWS_THROUGH': r'flows through',
    'CONTROLS': r'controls',
    'EXPRESSES': r'(?:expresses|represents)',
    'USES_QUANTITY': r'uses(?: the quantity)?',
    'DERIVED_FROM': r'is derived from',
}


def normalize(text):
    return ' '.join(text.casefold().split()).strip(' .;')


def name_pattern(name):
    # Only a simple printed symbol alias may be omitted, not descriptive clauses.
    name = re.sub(r'\s*\([A-Za-zΩµμ]{1,2}\)', '', normalize(name))
    name = re.sub(r'^(?:the|a|an)\s+', '', name)
    return r'(?:the |an |a )?' + re.escape(name) if name else r'(?!)'


def relation_witness(kind, subject, obj, text):
    """Return the matching source sentence, or None. Never infer from co-occurrence."""
    if not all(isinstance(x, str) and x.strip() for x in (kind, subject, obj, text)):
        return None
    clean = normalize(text)
    # Do not promote negated, conditional, questioned or qualified claims to plain facts.
    if re.search(r'\b(?:not|no|never|may|might|could|would|should|if|unless|assuming|suppose|only)\b|[?"“”]', clean):
        return None
    left, right = name_pattern(subject), name_pattern(obj)
    alias = r'(?:\s*\([a-zωµμ]{1,2}\))?'
    if kind == 'HAS_UNIT':
        patterns = [rf'(?:the )?(?:si )?unit (?:of|for) {left} (?:is called|is named|is|called) {right}{alias}',
                    rf'{left} is expressed by (?:a )?unit called {right}{alias}(?:, named after [a-z0-9 ,()–-]+)?']
        # Explicit unit lists assert membership, not the numeric conversion in parentheses.
        # NCERT uses "current" as the shortened name of "electric current" here.
        quantity = 'current' if normalize(subject) == 'electric current' else subject
        list_pattern = rf'(?:small quantities of )?{name_pattern(quantity)} (?:are|is) expressed in (?P<units>.+)'
        for clause in re.split(r'[.;]\s*', clean):
            match = re.fullmatch(list_pattern, clause.strip())
            if match:
                items = re.split(r' (?:or|and) in ', match['units'])
                unit_item = r'(?:[a-zµμ]+)(?:\s*\([^()]+\))?'
                if (all(re.fullmatch(unit_item, item) for item in items)
                        and any(re.fullmatch(rf'{right}(?:\s*\([^()]+\))?', item) for item in items)):
                    return clause.strip()
    elif kind in VERBS:
        patterns = [rf'{left} {VERBS[kind]} {right}{alias}']
        if kind == 'MEASURES':
            patterns.append(rf'(?:an instrument called )?{left} measures {right}(?: in (?:a |the )?circuit)?{alias}')
            patterns.append(rf'{right} is measured (?:by|with) {left}{alias}')
    else:
        return None
    # Full clause matching excludes incidental mentions and trailing qualifications.
    for clause in re.split(r'[.;]\s*', clean):
        clause = clause.strip()
        if any(re.fullmatch(pattern, clause) for pattern in patterns):
            return clause
    return None


def unit_relation_witness(quantity, unit, text):
    return relation_witness('HAS_UNIT', quantity, unit, text) is not None


def definition_witness(name, text):
    """Recognize explicit naming/definition wording; unknown wording needs review."""
    clean = normalize(text)
    if re.search(r'\b(?:not|never|if|unless|may|might|could|would)\b|[?"“”]', clean):
        return False
    term = name_pattern(name)
    return bool(re.search(rf'(?<!\w){term} (?:is defined as|means|refers to) .+', clean)
                or re.fullmatch(rf'.+ (?:is|are) (?:called|defined as) {term}', clean))
