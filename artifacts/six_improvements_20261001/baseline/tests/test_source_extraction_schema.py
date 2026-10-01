import pytest
from pydantic import ValidationError

from src.graph_store.graph_constructor import SourceExtraction


def test_source_schema_rejects_invented_labels_and_misconceptions():
    payload = {'entities': [{'entity_type': 'Concept', 'name': 'Current',
                            'description': 'Charge per time', 'evidence_id': 0, 'semantic_role': 'quantity'}],
               'relationships': [], 'misconceptions': []}
    assert SourceExtraction.model_validate(payload).entities[0].name == 'Current'
    payload['entities'][0]['entity_type'] = 'Instrument'
    with pytest.raises(ValidationError):
        SourceExtraction.model_validate(payload)
    payload['entities'][0]['entity_type'] = 'Concept'
    payload['misconceptions'] = ['Invented student error']
    with pytest.raises(ValidationError):
        SourceExtraction.model_validate(payload)


def test_evidence_offsets_are_exact_and_bad_citations_fail():
    from src.graph_store.graph_constructor import source_evidence_units, localized_evidence
    text = '  Current is charge per time.\n  An ammeter measures current.\n\nUnits follow.  '
    content = {'content': text, 'start_offset': 20, 'end_offset': 20 + len(text)}
    units = source_evidence_units(content)
    assert len(units) == 3
    for unit in units:
        assert unit['content'] == text[unit['start_offset'] - 20:unit['end_offset'] - 20]
    assert localized_evidence({'evidence_id': 1}, units, 'book')['content'] == 'An ammeter measures current.'
    for bad in [-1, len(units), True]:
        with pytest.raises(ValueError):
            localized_evidence({'evidence_id': bad}, units, 'book')
    with pytest.raises(ValueError):
        source_evidence_units({**content, 'end_offset': 999})


def test_candidate_prerequisites_are_separate_from_accepted_edges():
    from src.graph_store.graph_constructor import SourceRelationship
    from src.graph_store.neo4j_client import Neo4jClient
    relation = {'from_entity': 'Charge', 'to_entity': 'Current',
        'relationship_type': 'CANDIDATE_PREREQUISITE_OF', 'reason': 'Current is charge per time', 'evidence_id': 0}
    assert SourceRelationship.model_validate(relation).relationship_type in Neo4jClient.EDGE_TYPES
    relation['relationship_type'] = 'PREREQUISITE_OF'
    with pytest.raises(ValidationError):
        SourceRelationship.model_validate(relation)


def test_duplicate_relationships_cannot_overwrite_citations():
    entities = [{'entity_type': 'Concept', 'name': name, 'description': name, 'evidence_id': 0, 'semantic_role': 'instrument' if name == 'Ammeter' else 'quantity'}
                for name in ['Ammeter', 'Current']]
    edge = {'from_entity': 'Ammeter', 'to_entity': 'Current', 'relationship_type': 'MEASURES',
            'reason': 'Instrument measures current', 'evidence_id': 0}
    with pytest.raises(ValidationError, match='overwrite source evidence'):
        SourceExtraction.model_validate({'entities': entities,
            'relationships': [edge, {**edge, 'evidence_id': 1}], 'misconceptions': []})


@pytest.mark.parametrize('kind,left_role,right_role', [
    ('MEASURES','instrument','quantity'), ('FLOWS_THROUGH','quantity','medium'),
    ('CONTROLS','control','circuit'), ('EXPRESSES','formula','quantity'),
    ('USES_QUANTITY','formula','quantity'), ('HAS_UNIT','quantity','unit')])
def test_role_direction_accepts_valid_edges_and_rejects_reversals(kind,left_role,right_role):
    entities = [{'entity_type': 'Formula' if role == 'formula' else 'Concept',
                 'name': name, 'semantic_role': role, 'description': name, 'evidence_id': 0}
                for name,role in [('left',left_role),('right',right_role)]]
    edge = {'from_entity': 'left', 'to_entity': 'right', 'relationship_type': kind,
            'reason': 'source assertion', 'evidence_id': 0}
    payload = {'entities': entities, 'relationships': [edge], 'misconceptions': []}
    SourceExtraction.model_validate(payload)
    edge.update(from_entity='right',to_entity='left')
    with pytest.raises(ValidationError, match='Invalid direction'):
        SourceExtraction.model_validate(payload)


def test_rhetorical_question_is_not_assertion_evidence():
    from src.graph_store.graph_constructor import source_evidence_units, localized_evidence
    text = 'What does a switch do? A switch makes a conducting link.'
    units = source_evidence_units({'content':text,'start_offset':0,'end_offset':len(text)})
    with pytest.raises(ValueError, match='Question-only'):
        localized_evidence({'evidence_id':0}, units, 'book')
    assert localized_evidence({'evidence_id':1}, units, 'book')['content'].startswith('A switch makes')


def test_case_insensitive_names_cannot_collide_at_persistence():
    entities = [{'entity_type':'Concept','name':name,'semantic_role':'quantity',
                 'description':'Charge per time','evidence_id':0} for name in ['Current','current']]
    with pytest.raises(ValidationError, match='uniquely named'):
        SourceExtraction.model_validate({'entities':entities,'relationships':[],'misconceptions':[]})


@pytest.mark.parametrize('start,end',[(-1,2),(True,4),(0.0,3.0)])
def test_invalid_source_bounds_rejected_even_when_length_matches(start,end):
    from src.graph_store.graph_constructor import source_evidence_units
    with pytest.raises(ValueError, match='integer span'):
        source_evidence_units({'content':'abc','start_offset':start,'end_offset':end})
