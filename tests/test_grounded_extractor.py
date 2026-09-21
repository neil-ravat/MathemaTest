import pytest
from src.graph_store.grounded_extractor import candidates_for, extract_grounded_source, validate_reviews


def test_review_requires_exact_coverage_without_duplicate_ids():
    for rows in [[], [{'claim_id':'x','verdict':'SUPPORTED'}]*2,
                 [{'claim_id':'y','verdict':'SUPPORTED'}]]:
        with pytest.raises(ValueError):
            validate_reviews(rows, ['x'])


def test_rejected_unit_claim_is_retained_in_report_not_persistable_graph():
    text = 'The unit of Current is Ampere; the unit of Charge is Coulomb.'
    entities = [{'entity_type':'Concept','name':name,'semantic_role':role,
                 'description':name,'evidence_id':0} for name,role in
                [('Current','quantity'),('Ampere','unit'),('Coulomb','unit')]]
    seen = []
    def call(stage, system, payload, schema, model):
        seen.append((stage,model))
        if stage == 'entities':
            assert schema['properties']['entities']['items']['properties']['evidence_id']['enum'] == [0]
            assert 'start_offset' not in payload['excerpts'][0]
            return {'entities':entities}
        if stage == 'relationships':
            assert len(payload['candidates']) == 2
            return {'selected':[{'candidate_id':c['candidate_id'],'evidence_id':0,'reason':'test'}
                                for c in payload['candidates']]}
        return {'reviews':{c['claim_id']: {'reason':'test',
            'verdict':'UNSUPPORTED' if c['claim'].get('to_entity') == 'Coulomb' else 'SUPPORTED'}
            for c in payload['claims']}}
    result, report = extract_grounded_source({'content':text,'source_id':'test', 'chapter':1,
        'start_offset':100,'end_offset':100+len(text)},call,model='producer',reviewer_model='reviewer')
    assert seen == [('entities','producer'),('relationships','producer'),('source_review','reviewer')]
    assert len(result.relationships) == 1 and result.relationships[0].to_entity == 'Ampere'
    assert len(report['selected_relationships']) == 2
    assert not report['expert_gold'] and report['accepted_prerequisites'] == 0
    assert result.relationships[0].properties['relationship_review'] == 'MODEL_CHECKED_NOT_GOLD'
    assert result.entities[0].properties['start_offset'] == 100


def test_candidates_cannot_reverse_measurement_or_promote_prerequisites():
    candidates = candidates_for([{'name':'meter','semantic_role':'instrument'},
                                 {'name':'current','semantic_role':'quantity'}])
    assert candidates == [{'candidate_id':0,'from_entity':'meter',
                           'relationship_type':'MEASURES','to_entity':'current'}]


def test_unit_witness_does_not_confuse_nearby_quantities():
    from src.graph_store.grounded_extractor import unit_relation_witness
    text = ('The SI unit of electric charge is coulomb (C). '
            'The electric current is expressed by a unit called ampere (A).')
    assert unit_relation_witness('Electric charge','Coulomb (C)',text)
    assert unit_relation_witness('Electric current','Ampere (A)',text)
    assert not unit_relation_witness('Electric current','Coulomb (C)',text)
    assert not unit_relation_witness('Electric charge','Ampere (A)',text)
    assert not unit_relation_witness('Current','Ampere','Current, ampere and coulomb are mentioned.')
