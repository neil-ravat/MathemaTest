import hashlib
import json
from pathlib import Path
import pytest
from scripts.check_pedagogical_review import validate
from scripts.prepare_pedagogical_review import build


def material():
    prefix='Current is charge per time.'
    case=dict(id='dev',prefix_sha256=hashlib.sha256(prefix.encode()).hexdigest(),
              target_start_offset=len(prefix),context_complete_for_curriculum=False)
    review=dict(case_id='dev',reviewer='nonexpert user',learner_background='Arithmetic and unit conversion',
        input_readable=True,prerequisites_complete=True,judgment='SUPPORTED',rationale='Under this stated background',
        requirements=[dict(name='current relationship',status='EARLIER',quote=prefix,background_reason='')])
    return prefix,case,review


def test_supported_review_is_conditional_not_expert_gold():
    prefix,case,review=material()
    result=validate(review,case,prefix)
    assert result['usable_review_judgment']=='SUPPORTED' and not result['expert_gold']
    assert result['citations'][0]['end_offset']==case['target_start_offset']


def test_missing_retrieval_or_user_completeness_claim_cannot_establish_gap():
    prefix,case,review=material()
    review.update(judgment='GAP',context_complete_for_curriculum=True)
    review['requirements'][0].update(status='NOT_FOUND',quote='')
    result=validate(review,case,prefix)
    assert result['submitted_judgment']=='GAP' and result['usable_review_judgment']=='UNCERTAIN'
    assert 'Incomplete curriculum cannot establish absence' in result['unresolved']


def test_future_or_invented_support_and_changed_source_rejected():
    prefix,case,review=material()
    review['requirements'][0]['quote']='Later chapter supplies the answer.'
    with pytest.raises(ValueError,match='absent'): validate(review,case,prefix)
    with pytest.raises(ValueError,match='prefix mismatch'): validate(review,case,prefix+'later')


def test_unknowns_and_unexplained_background_remain_uncertain():
    prefix,case,review=material()
    review['requirements'][0].update(status='BACKGROUND',quote='')
    assert validate(review,case,prefix)['usable_review_judgment']=='UNCERTAIN'
    review['requirements'][0]['background_reason']='Assumed from earlier grades, not verified here'
    review['prerequisites_complete']=None
    assert validate(review,case,prefix)['usable_review_judgment']=='UNCERTAIN'


def test_packets_exclude_target_and_leave_all_labels_blank(tmp_path):
    root=Path(__file__).resolve().parents[1]
    if not (root/'data/ncert10_pilot_v1/live_development_cases_v1.json').exists():pytest.skip('Local development inputs required')
    source=root/'data/ncert10_pilot_v1'
    inputs=json.loads((source/'live_development_cases_v1.json').read_text())
    if any(not (source/'raw'/f"{c['source_id']}.pdf").exists() for c in inputs):
        pytest.skip('Original textbook PDFs are not distributed with the code release')
    cases=build(tmp_path)
    assert len(cases)==3
    for case in cases:
        prefix=(tmp_path/case['earlier_context_file']).read_text()
        assert len(prefix)==case['target_start_offset']
        assert not case['context_complete_for_curriculum']
        assert not {'reviewer_notes','target_reviewed','answer','prerequisite_label'} & case.keys()
    forms=[json.loads(p.read_text()) for p in tmp_path.glob('*-blank.json')]
    assert len(forms)==3 and all(f['judgment'] is None for f in forms)
    assert all(r['status'] is None for f in forms for r in f['requirements'])
