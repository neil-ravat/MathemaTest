from types import SimpleNamespace
import pytest

from src.graph_store.relation_evidence import relation_witness
from src.graph_store.graph_constructor import GraphConstructorAgent, ExtractedEntity, ExtractedRelationship, ExtractionResult


@pytest.mark.parametrize('kind,left,right,quote', [
    ('MEASURES', 'Ammeter', 'current', 'An ammeter measures current.'),
    ('MEASURES', 'Ammeter', 'current', 'Current is measured by an ammeter.'),
    ('FLOWS_THROUGH', 'electric current', 'copper wire', 'The electric current flows through the copper wire.'),
    ('CONTROLS', 'switch', 'circuit', 'The switch controls the circuit.'),
    ('EXPRESSES', 'formula', 'resistance', 'The formula expresses resistance.'),
    ('USES_QUANTITY', 'formula', 'current', 'The formula uses the quantity current.'),
    ('DERIVED_FROM', 'result', 'theorem', 'The result is derived from the theorem.'),
    ('HAS_UNIT', 'charge', 'coulomb', 'The SI unit of charge is coulomb (C).'),
])
def test_explicit_directional_claims_survive(kind,left,right,quote):
    assert relation_witness(kind,left,right,quote)
    assert not relation_witness(kind,right,left,quote)


@pytest.mark.parametrize('quote', [
    'An ammeter and current occur in this paragraph.',
    'An ammeter does not measure current.',
    'If an ammeter measures current, the circuit is closed.',
    'An ammeter measures current only under these conditions.',
    'Does an ammeter measure current?',
    'Someone claimed "an ammeter measures current".',
    'An ammeter measures voltage. Current is mentioned nearby.',
])
def test_mentions_negation_conditions_and_quotes_are_not_unconditional_facts(quote):
    assert not relation_witness('MEASURES','ammeter','current',quote)


def test_storage_boundary_rechecks_even_model_approved_edges():
    agent = GraphConstructorAgent.__new__(GraphConstructorAgent)
    written = []
    agent.neo4j = SimpleNamespace(create_node=lambda **kw: None,
        create_relationship=lambda **kw: written.append(kw))
    entities = [ExtractedEntity('Concept', name, name, {'semantic_role':role})
                for name,role in [('ammeter','instrument'),('current','quantity'),('wire','medium')]]
    relationships = [ExtractedRelationship('ammeter','current','MEASURES',
        {'content':'An ammeter measures current.', 'relationship_review':'MODEL_CHECKED_NOT_GOLD'}),
        ExtractedRelationship('current','wire','FLOWS_THROUGH',
        {'content':'Current and wire occur nearby.', 'relationship_review':'MODEL_CHECKED_NOT_GOLD'})]
    result = ExtractionResult(entities, relationships, [], '', {})
    counts = agent.persist_extraction(result, source_id='development')
    assert counts['relationships'] == 1 and counts['quarantined_relationships'] == 1
    assert written[0]['rel_type'] == 'MEASURES'
    assert 'quarantine_reason' in relationships[1].properties


def test_staged_extraction_blocks_unsupported_edge_despite_reviewer_approval():
    from src.graph_store.grounded_extractor import extract_grounded_source
    text = 'Akhila plays games near parallel lines.'
    def call(stage, system, payload, schema, model):
        if stage == 'entities':
            return {'entities':[dict(name=name, semantic_role=role, description=name, evidence_id=0)
                    for name,role in [('Akhila','quantity'),('parallel lines','medium')]]}
        if stage == 'relationships':
            return {'selected':[dict(candidate_id=0, evidence_id=0, reason='Both are mentioned.')]}
        return {'reviews':{c['claim_id']:dict(verdict='SUPPORTED',reason='Unreliable approval')
                           for c in payload['claims']}}
    result, report = extract_grounded_source(dict(content=text, source_id='dev', chapter=1,
        start_offset=0,end_offset=len(text)),call,model='fixed-producer',reviewer_model='fixed-reviewer')
    assert not result.relationships
    assert report['mechanical_rejections']['edge_0']
    assert len(report['selected_relationships']) == 1


def test_natural_measurement_and_unit_list_wording_without_unit_confusion():
    quote = ('Small quantities of current are expressed in milliampere '
             '(1 mA = 10–3 A) or in microampere (1 µA = 10–6 A).')
    for unit in ['Milliampere (mA)', 'Microampere (µA)']:
        assert relation_witness('HAS_UNIT', 'Electric current', unit, quote)
    assert not relation_witness('HAS_UNIT', 'Electric current', 'Coulomb (C)', quote)
    assert not relation_witness('HAS_UNIT', 'Electric charge', 'Milliampere (mA)', quote)
    assert not relation_witness('HAS_UNIT', 'Electric current', 'Milliampere (mA)', 'If '+quote)
    assert not relation_witness('HAS_UNIT', 'Electric current', 'Microampere (µA)',
        'Current is expressed in milliampere. Microampere is mentioned separately.')
    assert relation_witness('MEASURES', 'Ammeter', 'Electric current',
        'An instrument called ammeter measures electric current in a circuit.')
    assert not relation_witness('MEASURES', 'Ammeter', 'Voltage',
        'An instrument called ammeter measures electric current in a circuit.')
    assert relation_witness('HAS_UNIT', 'Electric current', 'Ampere (A)',
        'The electric current is expressed by a unit called ampere (A), named after Andre-Marie Ampere (1775–1836).')
