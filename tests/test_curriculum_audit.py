from types import SimpleNamespace
import json
import pytest
from src.verification.curriculum_audit import (Proposal, Assessment, eligible_records,
    retrieve_requirements, validate_evidence, validate_givens, audit_curriculum)


def row(id, text, position=0, **kw):
    return dict(id=id, content=text, position=position, source_id='book', kind='para', **kw)


P = Proposal(givens=[],requirements=[dict(name='order', necessity='Compare items', search_query='ordering numbers')])


def test_source_order_and_unreviewed_material_are_excluded():
    target = row('target', 'Compare.', 5)
    records = [row('prior', 'Ordering numbers.', 1), row('future', 'Answer.', 6),
               row('example', 'Answer.', 2, has_media=True), row('bad_math', '?', 3, unsupported_mathml=['table'])]
    assert [r['id'] for r in eligible_records(records, target)] == ['prior']
    with pytest.raises(ValueError): eligible_records([row('x','Text',True)], target)


@pytest.mark.parametrize('quote,id', [('Invented support.', 'p'), ('Ordering numbers.', 'future')])
def test_fabricated_or_unretrieved_citation_is_rejected(quote, id):
    a = Assessment(requirements=[dict(requirement_index=0,status='SUPPORTED',
        citations=[dict(source='passage',id=id,quote=quote)],rationale='Relevant')],
        additional_requirements=[], input_readable=True)
    with pytest.raises(ValueError): validate_evidence(a,P,[row('p','Ordering numbers.')],'Arithmetic')


def test_quote_provenance_and_completeness_are_checked():
    a = Assessment(requirements=[dict(requirement_index=0,status='SUPPORTED',
        citations=[dict(source='passage',id='p',quote='Ordering numbers.')],rationale='Relevant')],
        additional_requirements=[],input_readable=True)
    assert validate_evidence(a,P,[row('p','Ordering numbers.')],'Arithmetic')[0]['start'] == 0
    with pytest.raises(ValueError): validate_evidence(a.model_copy(update={'requirements':[]}),P,[],'')
    assert retrieve_requirements([row('p','Ordering numbers.')],P,max_chars=1) == ([],[])


def test_second_review_can_reject_exact_but_irrelevant_quotes():
    payloads = [P.model_dump(), dict(requirements=[dict(requirement_index=0,status='SUPPORTED',
        evidence_ids=['E0'],rationale='Relevant')],
        additional_requirements=[],input_readable=True),
        dict(requirements_complete=True,evidence_entails_requirements=False,assumptions_explicit=True,
             issues=['The quote does not establish the required operation.'],observations=[])]
    def create(**kwargs):
        payload = payloads.pop(0)
        if kwargs['response_format']['json_schema']['name']=='assessment':
            assert kwargs['max_tokens']==4096
            decision_schema=kwargs['response_format']['json_schema']['schema']['$defs']['EvidenceDecision']
            assert decision_schema['properties']['evidence_ids']['maxItems']==2
            assert decision_schema['properties']['rationale']['maxLength']==360
            task=json.loads(kwargs['messages'][1]['content'])
            assert all(set(r)=={'requirement_key','name'} for r in task['requirements'])
            payload['evidence_readings']={e['evidence_id']:e['quote'] for e in json.loads(kwargs['messages'][1]['content'])['evidence_catalog']}
            payload['requirements']={f'R{i}':{k:v for k,v in d.items() if k!='requirement_index'} for i,d in enumerate(payload['requirements'])}
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=json.dumps(payload)))], model_dump=lambda:payload)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out=audit_curriculum(client,'producer','reviewer',[row('p','Ordering numbers.')],row('t','Compare.',2),'Arithmetic')
    assert out['status']=='REVIEW_REQUIRED'
    assert not out['reviewer_grounding_valid'] and 'reviewer_grounding_error' in out
    assert len(out['validated_quotes'])==1 and len(out['calls'])==3
    assert out['educational_gold'] is None and not out['general_semantics_verified']


def test_target_givens_cannot_certify_prior_knowledge():
    target = 'The conversion is 2 tokens per unit.'
    proposal = P.model_copy(update={'givens': []})
    a = Assessment(requirements=[dict(requirement_index=0,status='SUPPORTED',
        citations=[dict(source='target',id='target',quote=target)],rationale='Given rule')],
        additional_requirements=[],input_readable=True)
    with pytest.raises(ValueError, match='Target facts'):
        validate_evidence(a,proposal,[],'Arithmetic',target)
    actual = Proposal(givens=[dict(name='conversion rate',quote=target)],requirements=P.requirements)
    assert validate_givens(actual,target)[0]['start']==0
    with pytest.raises(ValueError, match='exact target'):
        validate_givens(actual,'No conversion was supplied.')


def test_unrelated_book_uses_same_contract_without_subject_rules():
    proposal=Proposal(givens=[],requirements=[dict(name='alphabetical ordering',necessity='Sort entries',search_query='alphabetical order')])
    records=[row('dictionary','Alphabetical order compares letters from left to right.',1)]
    selected, trace=retrieve_requirements(records,proposal)
    assert selected[0]['id']=='dictionary' and trace[0]['requirement_index']==0


def test_exercise_section_metadata_excludes_instruction_paragraphs():
    assert eligible_records([row('instruction','Explain how to calculate a slope.',1,
                                instructional_role='exercise_material')],row('t','Problem',2)) == []


def test_adjacent_context_stays_in_module_scope_and_budget():
    proposal=Proposal(givens=[],requirements=[dict(name='rule',necessity='Use it',search_query='zebra')])
    records=[row('explanation','Context explanation',1,module_id='a'),
             row('seed','zebra equation',2,module_id='a'),
             row('other_module','Unrelated',3,module_id='b')]
    selected,trace=retrieve_requirements(records,proposal)
    assert {r['id'] for r in selected}=={'seed','explanation'}
    assert any(t.get('reason')=='adjacent_source_context' for t in trace)
    selected,_=retrieve_requirements(records,proposal,max_chars=len('zebra equation'))
    assert [r['id'] for r in selected]==['seed']


def test_catalogue_materializes_original_text_and_rejects_unknown_selection():
    from src.verification.curriculum_audit import evidence_catalog, materialize_assessment, EvidenceSelection
    catalog=evidence_catalog([row('p','An exact original sentence.')],'Arithmetic')
    selection=EvidenceSelection(evidence_readings={'B0':'Arithmetic','E0':'An exact original sentence.'},requirements=[dict(requirement_index=0,status='SUPPORTED',
        evidence_ids=['E0'],rationale='Relevant')],additional_requirements=[],input_readable=True)
    assert materialize_assessment(selection,catalog).requirements[0].citations[0].quote=='An exact original sentence.'
    selection.requirements[0].evidence_ids=['target']
    with pytest.raises(ValueError):materialize_assessment(selection,catalog)


def test_cnxml_roles_follow_ancestry_not_subject_words(tmp_path):
    from scripts.prepare_context_corpus import section_roles
    source=tmp_path/'section.xml'
    source.write_text('<document><section class="section-exercises"><para id="i">Words</para></section>'
                      '<section><para id="p">Exercises are a teaching activity.</para></section></document>')
    assert section_roles(source)=={'i':'exercise_material','p':'exposition'}


@pytest.mark.parametrize('prompt_tokens,reason', [(100,'stop'),(16000,'context_budget_exhausted')])
def test_local_runner_sets_context_and_preserves_budget_failures(monkeypatch,prompt_tokens,reason):
    from scripts import run_curriculum_audit as runner
    captured={}
    monkeypatch.setenv('MATHEMATEST_OLLAMA_URL','http://127.0.0.1:11435/')
    class Response:
        def __enter__(self):return self
        def __exit__(self,*args):pass
        def read(self):return json.dumps(dict(done_reason='stop',prompt_eval_count=prompt_tokens,message={'content':'{}'})).encode()
    def fake_open(request,timeout):
        captured.update(json.loads(request.data));captured['request_timeout']=timeout
        captured['url']=request.full_url;return Response()
    monkeypatch.setattr(runner,'urlopen',fake_open)
    response=runner.local_completion(model='local-model',messages=[],temperature=0,seed=42,max_tokens=2200,
        response_format={'json_schema':{'schema':{'type':'object'}}})
    assert captured['options']['num_ctx']==16384 and captured['options']['num_predict']==2200
    assert captured['request_timeout']==600
    assert captured['url']=='http://127.0.0.1:11435/api/chat'
    assert captured['format']=={'type':'object'}
    assert response.choices[0].finish_reason==reason
    assert response.model_dump()['prompt_eval_count']==prompt_tokens


def test_interruption_keeps_completed_stages_and_checkpoints():
    saved=[];calls=[]
    def create(**kwargs):
        calls.append(kwargs)
        if len(calls)>1:raise KeyboardInterrupt()
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
            message=SimpleNamespace(content=P.model_dump_json()))],model_dump=lambda:P.model_dump())
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result=audit_curriculum(client,'producer','reviewer',[row('p','Ordering numbers.')],
        row('t','Compare.',2),'Arithmetic',checkpoint=lambda value:saved.append(json.loads(json.dumps(value))))
    assert result['status']=='INTERRUPTED' and len(result['calls'])==2
    assert result['calls'][0]['response']==P.model_dump()
    assert saved[-1]['calls'][0]['response']==P.model_dump()
    assert result['proposal']==P.model_dump()


def test_advisory_observations_do_not_veto_but_real_blockers_still_do():
    from src.verification.curriculum_audit import Challenge, curriculum_status
    assessment=Assessment(requirements=[dict(requirement_index=0,status='SUPPORTED',
        citations=[dict(source='background',id='background',quote='Arithmetic')],rationale='Explicitly allowed')],
        additional_requirements=[],input_readable=True)
    review=Challenge(requirements_complete=True,evidence_entails_requirements=True,
        assumptions_explicit=True,issues=[],observations=['Another solution route could also be taught.'])
    assert curriculum_status(assessment,review,grounding_valid=True)=='MODEL_SUPPORTED'
    review.issues=['A required rule has no supporting evidence.']
    assert curriculum_status(assessment,review,grounding_valid=True)=='REVIEW_REQUIRED'
    review.issues=[];assessment.requirements[0].status='UNRESOLVED'
    assert curriculum_status(assessment,review,grounding_valid=True)=='REVIEW_REQUIRED'


@pytest.mark.parametrize('readings', [{}, {'B0':'Arithmetic','E0':'Rule','invented':'Rule'}, {'B0':'Arithmetic','E0':' '}])
def test_model_cannot_skip_or_invent_evidence_readings(readings):
    def create(**kwargs):
        stage=kwargs['response_format']['json_schema']['name']
        value=P.model_dump() if stage=='prerequisites' else dict(evidence_readings=readings,
            requirements={'R0':dict(status='SUPPORTED',evidence_ids=['E0'],rationale='Rule')},
            additional_requirements=[],input_readable=True)
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:value)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result=audit_curriculum(client,'producer','reviewer',[row('p','Ordering numbers.')],row('t','Compare.',2),'Arithmetic')
    assert result['status']=='ERROR' and len(result['calls'])==2
    assert 'reading' in result['error']


def test_proposal_quotes_are_constrained_to_original_math_spans():
    seen=[]
    def create(**kwargs):
        seen.append(kwargs)
        raise KeyboardInterrupt()
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    target='Differentiate.\n\ny=(x)^(cotx)'
    audit_curriculum(client,'producer','reviewer',[],row('t',target,2),'Algebra')
    allowed=seen[0]['response_format']['json_schema']['schema']['$defs']['Given']['properties']['quote']['enum']
    assert allowed==['Differentiate.','y=(x)^(cotx)']
    assert 'y = (x)^(cot(x))' not in allowed


def test_nested_exercises_and_unresolved_visual_evidence_are_ineligible():
    bad=[row('n','Question and answer',0,contains_exercise_content=True),
         row('v','See the graph',1,requires_external_media=True)]
    assert eligible_records(bad,row('t','Task',2))==[]


def test_linked_visual_target_is_blocked_before_any_model_call():
    result=audit_curriculum(None,'producer','reviewer',[],
        row('t','Interpret the linked graph.',2,requires_external_media=True),'Algebra')
    assert result['status']=='INPUT_REVIEW_REQUIRED' and result['calls']==[]


@pytest.mark.parametrize('url', ['http://gpu.example:11434', 'http://key@localhost:11435',
                               'http://127.0.0.1:11435/api', 'http://localhost:0'])
def test_gpu_connection_requires_clean_tunnel_url(monkeypatch,url):
    from scripts.run_curriculum_audit import ollama_base_url
    monkeypatch.setenv('MATHEMATEST_OLLAMA_URL',url)
    with pytest.raises(ValueError):ollama_base_url()


def test_repeated_evidence_references_are_bounded_before_deduplication():
    from src.verification.curriculum_audit import EvidenceDecision
    args=dict(requirement_index=0,status='SUPPORTED',rationale='Two complementary rules.')
    decision=EvidenceDecision(**args,evidence_ids=['E1','B0','E1','B0'])
    assert decision.evidence_ids==['E1','B0']
    # Reproduces the T4 run's runaway repeated citation list. Do not silently
    # trim an unbounded output into an apparently valid assessment.
    with pytest.raises(ValueError):
        EvidenceDecision(**args,evidence_ids=['E1']*1000)
    with pytest.raises(ValueError):
        EvidenceDecision(**{**args,'rationale':'x'*361},evidence_ids=['E1'])


def test_truncated_response_never_becomes_a_valid_proposal():
    def create(**kwargs):
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='length',
            message=SimpleNamespace(content=P.model_dump_json()))],model_dump=lambda:dict(done_reason='length'))
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    result=audit_curriculum(client,'producer','reviewer',[],row('t','Compare.',2),'Arithmetic')
    assert result['status']=='ERROR' and 'Incomplete model output' in result['error']
    assert 'proposal' not in result
    assert result['calls'][0]['response']['done_reason']=='length'


def test_grounded_review_rejects_unchecked_resolved_and_invented_objections():
    from src.verification.curriculum_audit import GroundedChallenge, review_request, validate_review
    payload,schema=review_request(dict(target='Rotate around x=2.',background='Algebra',
        givens=[dict(quote='Rotate around x=2.')],evidence_catalog=[dict(evidence_id='B0',quote='Algebra')]))
    issue=dict(claim='The axis is missing.',necessary_for_task='The task asks for a rotation.',
        context_checks={k:dict(outcome='does_not_resolve',reason='No support identified.') for k in ('T0','B0','G0')},
        evidence_ids=['B0'],unresolved_reason='Reviewer alleges absence.')
    values=dict(context_readings={'T0':'Rotation around x=2.','B0':'Algebra allowed.','G0':'Axis x=2 supplied.'},
        requirements_complete=False,evidence_entails_requirements=True,assumptions_explicit=False,
        issues=[issue],observations=[])
    assert schema['$defs']['ReviewIssue']['properties']['context_checks']['required']==['T0','B0','G0']
    for outcome in ('resolves','uncertain'):
        issue['context_checks']['G0']['outcome']=outcome
        with pytest.raises(ValueError,match='resolved or uncertain'):
            validate_review(GroundedChallenge(**values),payload)
    issue['context_checks']['G0']['outcome']='does_not_resolve'
    issue['evidence_ids']=['invented']
    with pytest.raises(ValueError,match='unknown or repeated'):
        validate_review(GroundedChallenge(**values),payload)
    issue['evidence_ids']=['B0'];del issue['context_checks']['G0']
    with pytest.raises(ValueError,match='all supplied context'):
        validate_review(GroundedChallenge(**values),payload)
    with pytest.raises(ValueError):
        GroundedChallenge(**{**values,'issues':['The axis is missing.']})


def test_positive_review_requires_context_coverage_and_consistent_judgments():
    from src.verification.curriculum_audit import GroundedChallenge, review_request, validate_review, curriculum_status, Challenge
    payload,_=review_request(dict(target='Sort these words.',background='Alphabetical ordering.',givens=[],evidence_catalog=[]))
    review=GroundedChallenge(context_readings={'T0':'Sort words.','B0':'Ordering is granted.'},
        requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
    validate_review(review,payload)
    review.requirements_complete=False
    with pytest.raises(ValueError,match='disagree'):validate_review(review,payload)
    review.requirements_complete=True;review.context_readings.pop('T0')
    with pytest.raises(ValueError,match='read every'):validate_review(review,payload)
    a=Assessment(requirements=[],additional_requirements=[],input_readable=True)
    legacy=Challenge(requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
    assert curriculum_status(a,legacy)=='REVIEW_REQUIRED'


def test_review_must_read_source_passages_as_well_as_target():
    from src.verification.curriculum_audit import GroundedChallenge, review_request, validate_review
    payload,schema=review_request(dict(target='Compute a density.',background='Arithmetic.',givens=[],
        evidence_catalog=[dict(evidence_id='B0',quote='Arithmetic.'),
                          dict(evidence_id='E0',quote='Density concerns mass and volume.')],
        task_facts=dict(status='SUFFICIENT',missing_facts=[],rationale='E0 allegedly states a formula.')))
    assert [e['id'] for e in payload['review_context']]==['T0','B0','E0']
    assert payload['review_context'][-1]['text']=='Density concerns mass and volume.'
    assert 'E0' in schema['$defs']['ReviewIssue']['properties']['context_checks']['required']
    review=GroundedChallenge(context_readings={'T0':'A task.','B0':'Arithmetic.'},
        requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
    with pytest.raises(ValueError,match='read every'):
        validate_review(review,payload)


def test_review_source_index_is_lossless_and_replayable_without_mutating_input():
    from src.verification.curriculum_audit import review_request
    original=dict(target='Compute.',background='Arithmetic.',givens=[],evidence_catalog=[
        dict(evidence_id='B0',quote='Arithmetic.'),
        dict(evidence_id='E0',source='passage',id='original',quote='Exact formula: a = b / c.')])
    before=json.dumps(original,sort_keys=True)
    task,schema=review_request(original)
    texts={e['id']:e['text'] for e in task['review_context']}
    assert [texts[e['text_context_id']] for e in task['evidence_catalog']]==[e['quote'] for e in original['evidence_catalog']]
    assert all('quote' not in e for e in task['evidence_catalog'])
    assert review_request(task)==(task,schema)
    assert json.dumps(original,sort_keys=True)==before


def test_diagnostic_scoring_distinguishes_wrong_answers_and_bad_formats():
    from scripts.diagnose_reviewer import score,request_body
    case=dict(category='arithmetic',expected=6,max_tokens=256,model='test',mode='unconstrained',messages=[],schema={'type':'object'})
    def raw(value,reason='stop'):
        return dict(done_reason=reason,prompt_eval_count=10,message={'content':json.dumps(value)})
    assert 'format' not in request_body(case)
    assert score(case,raw({'x':6,'prerequisites':['Algebra']}))['correct']
    wrong=score(case,raw({'x':4,'prerequisites':['Algebra']}))
    assert wrong['format_valid'] and not wrong['answer_correct']
    assert not score(case,raw({'x':True,'prerequisites':['Algebra']}))['format_valid']
    assert not score(case,raw({'x':6,'prerequisites':['Algebra']},'length'))['complete']
    fact=dict(category='fact_presence',expected=True,context='The axis is x=2.',needle='x=2',max_tokens=256)
    assert score(fact,raw({'present':True,'quote':'The axis is x=2.'}))['correct']
    assert not score(fact,raw({'present':True,'quote':'The axis is x=3.'}))['correct']
    assert not score(fact,raw({'present':False,'quote':''}))['correct']


def test_full_audit_uses_grounded_contract_before_model_support():
    def create(**kwargs):
        stage=kwargs['response_format']['json_schema']['name'];task=json.loads(kwargs['messages'][1]['content'])
        if stage=='prerequisites':value=P.model_dump()
        elif stage=='assessment':
            value=dict(evidence_readings={e['evidence_id']:'Ordering rule.' for e in task['evidence_catalog']},requirements={'R0':dict(status='SUPPORTED',evidence_ids=['B0'],rationale='Ordering allowed.')},additional_requirements=[],input_readable=True)
        else:
            assert list(kwargs['response_format']['json_schema']['schema']['properties'])[0]=='context_readings'
            value=dict(context_readings={e['id']:'Explicit ordering context.' for e in task['review_context']},requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:value)
    client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create)))
    out=audit_curriculum(client,'producer','reviewer',[],row('t','Compare.',2),'Ordering allowed.')
    assert out['status']=='MODEL_SUPPORTED' and out['reviewer_grounding_valid']
    assert out['educational_gold'] is None and not out['general_semantics_verified']
