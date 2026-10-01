import copy
import xml.etree.ElementTree as ET

import pytest

from scripts.prepare_openstax import render
from scripts.prepare_context_corpus import independent_prefix
from src.verification.curriculum_audit import eligible_records


def test_cnxml_super_and_subscripts_keep_their_notation_and_tail():
    node=ET.fromstring('<para xmlns="http://cnx.rice.edu/cnxml">Acceleration in m/s<sup>2</sup>; v<sub>initial</sub>=0.</para>')
    unsupported=set()
    assert render(node,unsupported)=='Acceleration in m/s^(2); v_(initial)=0.'
    assert not unsupported


def test_table_boundaries_and_spans_are_not_silently_flattened():
    node = ET.fromstring('''<math xmlns="http://www.w3.org/1998/Math/MathML"><mtable>
      <mtr><mtd><mi>a</mi><mo>=</mo><mn>2</mn></mtd><mtd><mtext>first rule</mtext></mtd></mtr>
      <mtr><mtd><mi>b</mi><mo>=</mo><mn>3</mn></mtd><mtd><mtext>second rule</mtext></mtd></mtr>
    </mtable></math>''')
    unsupported = set(); text = render(node, unsupported)
    assert 'row[ a=2 | first rule ] ; row[ b=3 | second rule ]' in text
    assert not unsupported
    node.find('.//{*}mtd').set('columnspan', '2')
    unsupported = set(); render(node, unsupported)
    assert 'spanned-mtable' in unsupported


def test_exact_prefix_recovers_text_without_admitting_media_or_exercises():
    text = 'A full turn is 360 degrees. Half a turn is 180 degrees. [reference:#fig] shows examples.'
    row = dict(id='p', source_id='book', position=0, content=text,
               instructional_role='exposition', requires_external_media=True,
               retrieval_excerpt=independent_prefix(text))
    original = copy.deepcopy(row)
    target = dict(source_id='book', position=2)
    selected = eligible_records([row], target)
    assert len(selected)==1 and selected[0]['content']=='A full turn is 360 degrees. Half a turn is 180 degrees.'
    assert row==original and selected[0]['retrieval_excerpt']['parent_sha256']
    for flags in [dict(position=2), dict(contains_exercise_content=True),
                  dict(instructional_role='exercise_material'), dict(unsupported_mathml=['unknown'])]:
        assert not eligible_records([dict(row, **flags)], target)
    row['content'] = row['content'].replace('180','190')
    with pytest.raises(ValueError, match='Unverified'):eligible_records([row],target)
    assert independent_prefix('Use [reference:#fig] to read the value.') is None
    assert independent_prefix('The figure gives the value. [reference:#fig]') is None

from types import SimpleNamespace
import json
import jsonschema
from src.verification.evidence_audit import (RoutedProposal, validate_routes, JointWitness,
    TypedRequirement, validate_joint_witness, TaskFacts, task_spans, validate_task_readings,
    audit_evidence, RouteReview, validate_route_review)


def requirement(name='Rule', kind='domain_rule'):
    return dict(name=name, kind=kind, necessity='Needed for the stated route.',search_query=name)


def test_routes_do_not_union_alternatives_or_drop_unassigned_requirements():
    data=dict(givens=[],requirements=[requirement('Rule A'),requirement('Rule B'),requirement('Optional check')],
        routes=[dict(name='Direct',steps=[dict(action='Apply A.',requirement_indices=[0])]),
                dict(name='Alternative',steps=[dict(action='Apply B.',requirement_indices=[1])])],
        optional_requirement_indices=[2],optional_reason='Checking is not requested.')
    assert validate_routes(RoutedProposal(**data))==[[0],[1]]
    for changes in [dict(optional_requirement_indices=[]),dict(optional_requirement_indices=[0,2]),
                    dict(optional_reason='')]:
        with pytest.raises(ValueError):validate_routes(RoutedProposal(**{**data,**changes}))


def test_multiple_exact_premises_allow_composition_but_not_invented_or_future_steps():
    catalog=[dict(evidence_id='E0',source='passage',quote='u=a+b'),
             dict(evidence_id='E1',source='passage',quote='v=2*u')]
    witness=JointWitness(evidence_ids=['E0','E1'],basis='DERIVED',
        established_knowledge='v=2*(a+b)',needed_knowledge='Obtain v from a and b.',
        derivation=[dict(premise_ids=['E0','E1'],operation='substitution',conclusion='Substitute a+b for u in v=2*u.')])
    assert validate_joint_witness(witness,catalog,0,TypedRequirement(**requirement())).evidence_ids==['E0','E1']
    for ids in [['S0'],['E2'],['E0']]:
        bad=witness.model_copy(deep=True);bad.derivation[0].premise_ids=ids
        with pytest.raises(ValueError):validate_joint_witness(bad,catalog,0,TypedRequirement(**requirement()))
    bg=[dict(evidence_id='B0',source='background',quote='Arithmetic and elementary algebra are known. No subject-specific formulas are granted without source evidence.')]
    bad=witness.model_copy(update=dict(evidence_ids=['B0'],basis='STATED',derivation=[]))
    with pytest.raises(ValueError,match='Arithmetic-only'):validate_joint_witness(bad,bg,0,TypedRequirement(**requirement()))


def test_source_equations_cannot_change_in_transcription_or_task_rationale():
    target='Find the domain of f(x)=sqrt(x−2).';spans=task_spans(target)
    facts=TaskFacts(task_readings=spans,status='SUFFICIENT',missing_facts=[],rationale='T0 supplies the function.')
    validate_task_readings(facts,spans,target)
    for bad in [facts.model_copy(update={'rationale':'The supplied function is sqrt(x^2).'}),
                facts.model_copy(update={'rationale':'T0 supplies x=12.'}),
                facts.model_copy(update={'task_readings':[type(facts.task_readings[0])(span_id='T0',exact_text=target.replace('x−2','x^2'))]})]:
        with pytest.raises(ValueError):validate_task_readings(bad,spans,target)
    prose='A runner travels ninety metres in fifteen seconds. Find speed in metres per second.'
    units=TaskFacts(task_readings=task_spans(prose),status='SUFFICIENT',missing_facts=[],rationale='Inputs determine a result in m/s.')
    validate_task_readings(units,task_spans(prose),prose)


def response(value, reason='stop'):
    raw=dict(choices=[dict(finish_reason=reason,message=dict(content=json.dumps(value)))],usage={'prompt_tokens':10,'completion_tokens':10})
    return SimpleNamespace(choices=[SimpleNamespace(finish_reason=reason,message=SimpleNamespace(content=json.dumps(value)))],model_dump=lambda:raw)


@pytest.mark.parametrize('damage', [None,'equation','truncation','unsupported','first_route_only','review_first_route'])
def test_current_pipeline_uses_one_supported_route_and_preserves_sources(damage):
    from scripts.run_gpt4o_smoke import run_case
    bg='Arithmetic and elementary algebra are known. No subject-specific formulas are granted without source evidence.'
    records=[dict(id='rule',source_id='book',position=0,module_id='m',kind='para',instructional_role='exposition',content='The transformation maps x to sqrt(x−2).')]
    target=dict(id='target',source_id='book',position=2,content='Evaluate the supplied transformation sqrt(x−2) at x=11.')
    case=dict(id='control',records=records,target=target,background=bg)
    original=json.dumps(case,sort_keys=True);stages=[];truncated=False
    def complete(**request):
        nonlocal truncated
        stage=request['response_format']['json_schema']['name'];payload=json.loads(request['messages'][1]['content']);stages.append(stage)
        if stage=='prerequisites':
            value=dict(givens=[dict(name='Input and transformation',quote=target['content'])],
                requirements=[requirement('Transformation'),requirement('Alternative theorem'),requirement('Optional checking')],
                routes=[dict(name='Direct',steps=[dict(action='Apply the supplied transformation.',requirement_indices=[0])]),
                        dict(name='Alternative',steps=[dict(action='Use a different theorem.',requirement_indices=[1])])],optional_requirement_indices=[2],optional_reason='Checking is not requested.')
        elif stage.startswith('requirement_'):
            value=dict(evidence_ids=['E0'],basis='INSUFFICIENT' if damage=='unsupported' or (damage=='first_route_only' and stage=='requirement_0') else 'STATED',established_knowledge='The source specifies the transformation.',needed_knowledge='Apply the transformation.',derivation=[])
        elif stage=='task_facts':
            if damage=='truncation' and not truncated:
                truncated=True;return response({},'length')
            value=dict(task_readings=payload['immutable_task_spans'],status='SUFFICIENT',missing_facts=[],rationale='The expression sqrt(x^2) is supplied.' if damage=='equation' else 'T0 specifies the expression and value.')
        else:
            value=dict(context_readings=[dict(context_id=c['id'],supplies='Supplied task or rule.') for c in payload['context']],
                route_solves_task=True,requirements_necessary_and_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
            if damage=='review_first_route' and payload['selected_route']['name']=='Direct':
                value.update(route_solves_task=False,issues=[dict(claim='This route does not solve the task.',necessary_for_task='A complete solution route is needed.',checked_context_ids=[c['id'] for c in payload['context']],resolving_context_ids=[],uncertain_context_ids=[],reason='The route omits a necessary step.')])
        jsonschema.validate(value,request['response_format']['json_schema']['schema'])
        return response(value)
    result=run_case(case,complete,lambda _:None,model='mock')
    assert result['status']==('ERROR' if damage=='equation' else 'REVIEW_REQUIRED' if damage=='unsupported' else 'MODEL_SUPPORTED'),result
    assert result['source_integrity_verified'] and json.dumps(case,sort_keys=True)==original
    assert ('challenge' in stages)==(damage in (None,'truncation','first_route_only','review_first_route'))
    if damage in (None,'truncation'):assert 'requirement_1' not in stages
    if damage in ('first_route_only','review_first_route'):assert result['selected_route_index']==1
    assert 'requirement_2' not in stages
    if damage=='truncation':
        calls=[c for c in result['calls'] if c['stage']=='task_facts']
        assert [c['max_tokens'] for c in calls]==[1024,2048] and calls[0]['validation_error']=='Incomplete output'


def test_oversized_requests_are_blocked_before_api_call(tmp_path):
    from scripts.run_gpt4o_smoke import GroqCompletion,GROQ_MODEL
    calls=[];transport=GroqCompletion(lambda **kw:calls.append(kw),tmp_path/'usage.json')
    with pytest.raises(ValueError,match='too large'):
        transport(model=GROQ_MODEL,max_tokens=1024,messages=[dict(role='user',content='x'*26000)],response_format={'json_schema':{'name':'test'}})
    assert not calls and transport.calls[0]['status']=='blocked_before_request'


def test_reviewer_cannot_skip_context_or_discard_resolving_evidence():
    context=[dict(id='T0',text='Task'),dict(id='E0',text='The necessary rule')]
    data=dict(context_readings=[dict(context_id=c['id'],supplies=c['text']) for c in context],route_solves_task=True,
        requirements_necessary_and_complete=True,evidence_entails_requirements=True,assumptions_explicit=True,issues=[],observations=[])
    assert validate_route_review(RouteReview(**data),context)
    with pytest.raises(ValueError):validate_route_review(RouteReview(**{**data,'context_readings':data['context_readings'][:1]}),context)
    issue=dict(claim='Rule absent',necessary_for_task='Apply rule',checked_context_ids=['T0','E0'],resolving_context_ids=['E0'],uncertain_context_ids=[],reason='Absent')
    with pytest.raises(ValueError,match='Resolved'):validate_route_review(RouteReview(**{**data,'evidence_entails_requirements':False,'issues':[issue]}),context)


def test_comparison_metrics_keep_errors_and_unattempted_in_the_denominator(tmp_path):
    from scripts.run_fresh_comparison import summarize,write
    plan=[dict(id='p',family='f',book='A'),dict(id='n',family='g',book='B'),dict(id='u',family='h',book='B')]
    write(tmp_path/'plan.json',plan)
    write(tmp_path/'reference_review.json',[dict(case_id='p',reference_status='MODEL_SUPPORTED'),dict(case_id='n',reference_status='REVIEW_REQUIRED'),dict(case_id='u',reference_status='UNCERTAIN')])
    write(tmp_path/'results/00-baseline.json',dict(status='ERROR',_finished=True))
    write(tmp_path/'results/01-baseline.json',dict(status='MODEL_SUPPORTED',_finished=True))
    write(tmp_path/'results/00-candidate.json',dict(status='MODEL_SUPPORTED',_finished=True))
    write(tmp_path/'results/01-candidate.json',dict(status='REVIEW_REQUIRED',_finished=True))
    result=summarize(tmp_path)
    assert result['accuracy'] is None and not result['independent_labels']
    old=result['arms']['baseline'];new=result['arms']['candidate']
    assert old['planned']==3 and old['completed']==2 and old['valid_judgments']==1
    assert old['provisional_status_matches']==0 and old['unsupported_acceptance']==1
    assert old['false_review_on_supported']==0 and old['status_counts']['ERROR']==1
    assert new['provisional_status_matches']==2 and new['reference_labeled_denominator']==2
    assert new['status_counts']['UNATTEMPTED']==1
