"""Conservative recognition of explicit arithmetic grants, not subject-rule inference."""
import re
from .support_witness import SupportWitness

_OPERATIONS = ('addition', 'subtraction', 'multiplication', 'division')
# A deliberately small input grammar: unknown clauses fall back to model review.
_SKILLS = {'arithmetic', 'rational arithmetic', 'elementary algebra',
           'substitution into supplied formulas', *_OPERATIONS}
_RESTRICTIONS = {
    'no subject-specific definitions or formulas are granted without source evidence',
    'no subject-specific formulas are granted without source evidence',
    'no other subject-specific rules are granted',
}


def explicit_operation_witness(requirement, catalog):
    name = ' '.join(requirement.lower().strip().rstrip('.').split())
    match = re.fullmatch(r'(addition|subtraction|multiplication|division) of (?:two )?(?:supplied )?(?:rational )?numbers', name)
    if not match:
        return None
    operation = match[1]
    backgrounds = [e for e in catalog if e.get('source') == 'background']
    if len(backgrounds) != 1:
        return None
    entry = backgrounds[0]
    sentences = [s.strip().lower() for s in entry['quote'].split('.') if s.strip()]
    grants = set()
    for sentence in sentences:
        if sentence in _RESTRICTIONS:
            continue
        positive = re.fullmatch(r'(.+?) (?:is|are) known', sentence)
        if not positive:
            return None
        skills = set(re.split(r',\s*|\s+and\s+', positive[1]))
        if not skills or not skills <= _SKILLS:
            return None
        grants.update(skills)
    if operation not in grants and not grants.intersection({'arithmetic', 'rational arithmetic'}):
        return None
    return SupportWitness(evidence_id=entry['evidence_id'], quote=entry['quote'],
        established_knowledge=f'The explicit learner profile grants {operation} of numbers directly or as part of arithmetic.',
        needed_knowledge=requirement, basis='STATED', derivation='')
