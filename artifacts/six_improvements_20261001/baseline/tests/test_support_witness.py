import json
import pytest
from src.verification.support_witness import SupportWitness, witness_decision, parse_witness, witness_schema

CATALOG = [dict(evidence_id='B0', quote='Arithmetic is known.'),
           dict(evidence_id='E0', quote='Density d=m/V; d and V are positive.')]


def test_inspected_context_does_not_become_support_and_derived_support_needs_evidence():
    w = SupportWitness(evidence_id='B0', quote='Arithmetic is known.',
        established_knowledge='Arithmetic operations only.', needed_knowledge='A subject rule.',
        basis='INSUFFICIENT', derivation='')
    d = witness_decision(w, CATALOG, 2)
    assert d.status == 'UNRESOLVED' and not d.evidence_ids and d.requirement_index == 2
    w = w.model_copy(update=dict(evidence_id='E0', quote='Density d=m/V;', basis='DERIVED',
        derivation='Multiply by V to obtain d*V=m; divide by positive d to obtain V=m/d.'))
    assert witness_decision(w, CATALOG, 0).status == 'SUPPORTED'
    for changes in [dict(quote='Volume V=m/d.'), dict(evidence_id='B0'), dict(derivation='')]:
        with pytest.raises(ValueError):
            witness_decision(w.model_copy(update=changes), CATALOG, 0)


def test_native_witness_cannot_rewrite_source_or_supply_unknown_id():
    data=dict(evidence_id='E0',established_knowledge='The density relation.',needed_knowledge='The density relation.',basis='STATED',derivation='')
    assert 'quote' not in witness_schema(CATALOG)['properties']
    assert parse_witness(json.dumps(data),CATALOG).quote==CATALOG[1]['quote']
    for changes in [dict(quote='A rewritten source.'),dict(evidence_id='invented')]:
        with pytest.raises(ValueError):
            parse_witness(json.dumps({**data,**changes}),CATALOG)
