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


def test_approved_paraphrase_cannot_add_uncited_claims_or_unmentioned_entities():
    text = 'The unit of current is ampere. I = Q/t.'
    def call(stage, system, payload, schema, model):
        if stage == 'entities':
            return {'entities': [dict(name=name, semantic_role=role, description=description, evidence_id=eid)
                for name, role, description, eid in [
                    ('ampere', 'unit', 'One coulomb per second, named after a scientist.', 0),
                    ('voltage', 'quantity', 'Voltage is mentioned in the source.', 0),
                    ('I = Q/t', 'formula', 'Current is charge per time.', 1)]]}
        if stage == 'relationships':
            return {'selected': []}
        return {'reviews': {c['claim_id']: dict(verdict='SUPPORTED', reason='Overconfident reviewer')
                            for c in payload['claims']}}
    result, report = extract_grounded_source(dict(content=text, source_id='dev', chapter=1,
        start_offset=0, end_offset=len(text), formula_layout_verified=False),
        call, model='producer', reviewer_model='reviewer')
    assert [e.name for e in result.entities] == ['ampere']
    assert result.entities[0].description == 'The unit of current is ampere.'
    assert result.entities[0].properties['formula_layout_verified'] is False
    assert set(report['entity_mechanical_rejections']) == {'entity_1', 'entity_2'}
    assert report['entities'][0]['description'].startswith('One coulomb')
    assert not report['expert_gold']


def test_definition_role_needs_more_than_a_mention_even_if_reviewer_approves():
    text = 'Charge flows through a conductor. A closed current path is called an electric circuit.'
    def call(stage, system, payload, schema, model):
        if stage == 'entities':
            return {'entities': [dict(name=n,semantic_role='definition',description=n,evidence_id=i)
                                 for i,n in enumerate(['conductor','electric circuit'])]}
        return {'reviews': {c['claim_id']:dict(verdict='SUPPORTED',reason='Approved') for c in payload['claims']}}
    result, report = extract_grounded_source(dict(content=text,start_offset=0,end_offset=len(text),source_id='dev',chapter=1),
        call,model='producer',reviewer_model='reviewer')
    assert [e.name for e in result.entities] == ['electric circuit']
    assert 'role requires review' in report['entity_mechanical_rejections']['entity_0']


def test_explicit_quantity_symbols_record_omissions_without_promoting_them():
    text = 'For charge Q, in time t, the current I, use the stated relation.'
    def call(stage, system, payload, schema, model):
        if stage == 'entities':
            return {'entities':[dict(name='current',semantic_role='quantity',description='current',evidence_id=0)]}
        assert stage=='source_review'
        return {'reviews':{c['claim_id']:dict(verdict='UNSUPPORTED' if c['claim']['name']=='time' else 'SUPPORTED',reason='test') for c in payload['claims']}}
    result, report = extract_grounded_source(dict(content=text,start_offset=10,end_offset=10+len(text),source_id='dev',chapter=1),call,model='producer',reviewer_model='reviewer')
    assert {e.name for e in result.entities if e.properties['entity_review']=='MODEL_CHECKED_NOT_GOLD'} == {'current'}
    assert {m['name'] for m in report['quantity_symbol_mentions']} == {'charge','time','current'}
    assert len(report['quantity_symbol_mentions']) == 3
    for m in report['quantity_symbol_mentions']:
        assert text[m['start_offset']-10:m['end_offset']-10]==m['source_phrase']


def test_literal_mentions_survive_uncertain_semantics_without_creating_edges():
    text = 'For charge Q, in time t, use the relation. Do not assign charge Q, globally.'
    def call(stage, system, payload, schema, model):
        if stage == 'entities':
            return {'entities': [dict(name='charge', semantic_role='quantity',
                description='Charge has a full definition here.', evidence_id=0)]}
        assert stage == 'source_review'
        assert len(payload['claims']) == 1
        return {'reviews': {'entity_0': dict(verdict='UNCERTAIN', reason='No definition')}}
    result, report = extract_grounded_source(dict(content=text, start_offset=100,
        end_offset=100+len(text), source_id='dev', chapter=1), call,
        model='producer', reviewer_model='reviewer')
    assert report['accepted_entity_names'] == []
    assert report['literal_mention_count'] == 3
    assert len({e.name for e in result.entities}) == 3
    assert not result.relationships
    for entity in result.entities:
        props = entity.properties
        assert props['entity_review'] == 'EXACT_SOURCE_MENTION'
        assert props['assertion_kind'] == 'literal_phrase_occurrence'
        assert props['symbol_assignment_verified'] is False
        assert props['semantic_role'] == 'other'
        assert text[props['start_offset']-100:props['end_offset']-100] == entity.description
