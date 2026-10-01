import json
from types import SimpleNamespace
import pytest
from scripts.compare_local_workflows import candidate,cases,summary

@pytest.mark.parametrize('facts_status,ids,expected',[
    ('SUFFICIENT',['B0'],'MODEL_SUPPORTED'),
    ('MISSING_TASK_FACT',['B0'],'REVIEW_REQUIRED'),
    ('SUFFICIENT',['invented'],'ERROR')])
def test_candidate_reuses_upstream_and_enforces_evidence_and_task_facts(facts_status,ids,expected):
    base=dict(proposal=dict(givens=[],requirements=[dict(name='Arithmetic',necessity='Compute',search_query='Arithmetic')]),
        passages=[],retrieval_trace=[],validated_givens=[],target={'content':'Compute.'},background='Arithmetic allowed.',
        evidence_catalog=[dict(evidence_id='B0',source='background',id='background',quote='Arithmetic allowed.')])
    def complete(**kwargs):
        stage=kwargs['response_format']['json_schema']['name'];payload=json.loads(kwargs['messages'][1]['content'])
        assert not {'expected','reference_answer','condition'} & set(payload)
        if stage.startswith('requirement_'):
            value=dict(status='SUPPORTED',evidence_ids=ids,rationale='Explicit skill allowance.')
        elif stage=='task_facts':
            value=dict(status=facts_status,missing_facts=['Value'] if facts_status=='MISSING_TASK_FACT' else [],rationale='Checked target.')
        else:
            assert payload['task_facts']['status']==facts_status
            value=dict(context_readings={x['id']:'Explicit context.' for x in payload['review_context']},requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:dict(eval_count=5))
    original=json.dumps(base,sort_keys=True);result=candidate(base,lambda _:None,complete)
    assert result['status']==expected and json.dumps(base,sort_keys=True)==original


def test_fresh_cases_and_scores_do_not_credit_errors_as_abstention():
    plan=cases();assert len(plan)==6 and 5+(6-1)*3==20 and 90/15==6
    assert all(('weighted mean' not in c['target']['content'] and 'pressure' not in c['target']['content']) for c in plan)
    rows=[dict(case_id=c['id'],arm='baseline',status='REVIEW_REQUIRED',calls=[],seconds=0) for c in plan]
    scores=summary(plan,rows)['arms']['baseline']
    assert scores['expected_status_matches']==4 and scores['supported_accepted']==0
    rows[1]['status']='ERROR';scores=summary(plan,rows)['arms']['baseline']
    assert scores['errors']==1 and scores['expected_status_matches']==3


def test_rule_diagnostic_keeps_labels_out_of_inputs_and_errors_out_of_matches():
    from scripts.check_rule_support import cases as rule_cases, score
    plan = rule_cases()
    assert len(plan) == 8
    assert all(set(c['payload']) == {'target', 'requirement', 'evidence_catalog'} for c in plan)
    omitted = next(c for c in plan if c['id'] == 'circle-absent')
    rows = [dict(case_id=omitted['id'], arm='previous', decision={'status':'SUPPORTED'}),
            dict(case_id=omitted['id'], arm='revised', error='Incomplete output')]
    report = score(plan, rows)
    assert report['previous']['false_support'] == 1
    assert report['revised']['matches'] == 0 and report['revised']['errors'] == 1


@pytest.mark.parametrize('basis,quote,expected',[
    ('INSUFFICIENT','Arithmetic allowed.','REVIEW_REQUIRED'),
    ('STATED','Arithmetic allowed.','MODEL_SUPPORTED'),
    ('STATED','Invented formula.','ERROR')])
def test_witness_pipeline_cannot_override_missing_or_invented_support(basis,quote,expected):
    base=dict(proposal=dict(givens=[],requirements=[dict(name='Arithmetic',necessity='Compute',search_query='Arithmetic')]),
        passages=[],retrieval_trace=[],validated_givens=[],target={'content':'Compute.'},background='Arithmetic allowed.',
        evidence_catalog=[dict(evidence_id='B0',source='background',id='background',quote='Arithmetic allowed.')])
    def complete(**kwargs):
        stage=kwargs['response_format']['json_schema']['name'];payload=json.loads(kwargs['messages'][1]['content'])
        if stage.startswith('requirement_'):
            assert 'target' not in payload
            value=dict(evidence_id='B0',established_knowledge='Arithmetic allowed.',needed_knowledge='The named skill.',basis=basis,derivation='')
            if quote=='Invented formula.':value['quote']=quote
        elif stage=='task_facts':
            value=dict(status='SUFFICIENT',missing_facts=[],rationale='All task facts supplied.')
        else:
            value=dict(context_readings={x['id']:'Explicit context.' for x in payload['review_context']},requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:dict(eval_count=5))
    result=candidate(base,lambda _:None,complete,evidence_first=True)
    assert result['status']==expected
    if basis=='INSUFFICIENT':
        assert not result['assessment']['requirements'][0]['citations']
        assert result['support_witnesses'][0]['quote']==quote


def test_explicit_primitive_support_skips_model_judgment_but_keeps_task_and_review_checks():
    bg='Arithmetic and elementary algebra are known. No subject-specific formulas are granted without source evidence.'
    base=dict(proposal=dict(givens=[],requirements=[dict(name='Division of supplied numbers',necessity='Divide the two numbers',search_query='Division')]),
        passages=[],retrieval_trace=[],validated_givens=[],target={'content':'Divide 42 by 7.'},background=bg,
        evidence_catalog=[dict(evidence_id='B0',source='background',id='background',quote=bg)])
    def complete(**kwargs):
        stage=kwargs['response_format']['json_schema']['name'];payload=json.loads(kwargs['messages'][1]['content'])
        assert not stage.startswith('requirement_')
        if stage=='task_facts':
            value=dict(status='SUFFICIENT',missing_facts=[],rationale='Both inputs supplied.')
        else:
            value=dict(context_readings={x['id']:'Explicit context.' for x in payload['review_context']},requirements_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:dict(eval_count=5))
    result=candidate(base,lambda _:None,complete,evidence_first=True)
    assert result['status']=='MODEL_SUPPORTED'
    assert [c['stage'] for c in result['calls']]==['task_facts','challenge']
    assert result['witness_origins']==[dict(requirement_index=0,origin='explicit_learner_grant')]


@pytest.mark.parametrize('facts_status,missing_facts,expected',[
    ('RULE_NOT_ESTABLISHED',[],'REVIEW_REQUIRED'),
    ('RULE_NOT_ESTABLISHED',['A formula'],'ERROR'),
    ('MISSING_TASK_FACT',['elapsed time'],'REVIEW_REQUIRED')])
def test_unresolved_task_conditions_stop_before_final_review(facts_status,missing_facts,expected):
    bg='Arithmetic and elementary algebra are known. No subject-specific formulas are granted without source evidence.'
    base=dict(proposal=dict(givens=[],requirements=[dict(name='Division of supplied numbers',necessity='Divide.',search_query='Division')]),
        passages=[],retrieval_trace=[],validated_givens=[],target={'content':'Compute.'},background=bg,
        evidence_catalog=[dict(evidence_id='B0',source='background',id='background',quote=bg)])
    stages=[]
    def complete(**request):
        stage=request['response_format']['json_schema']['name'];stages.append(stage)
        assert stage=='task_facts', 'A known blocker must not reach the final reviewer'
        value=dict(status=facts_status,missing_facts=missing_facts,rationale='Input/rule limitation.')
        return SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:{})
    result=candidate(base,lambda _:None,complete,evidence_first=True)
    assert result['status']==expected
    assert stages==['task_facts']
    if expected=='REVIEW_REQUIRED':
        assert result['blocking_stages']==['task_facts']
        assert result['reviewer_grounding_valid'] is False
