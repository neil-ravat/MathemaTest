"""Validate review evidence, not reviewer expertise or physical/pedagogical truth."""
import argparse
import hashlib
import json
from pathlib import Path


def validate(review,case,prefix):
    if review['case_id']!=case['id'] or hashlib.sha256(prefix.encode()).hexdigest()!=case['prefix_sha256'] or len(prefix)!=case['target_start_offset']:
        raise ValueError('Case or source prefix mismatch')
    if not review.get('reviewer','').strip():raise ValueError('Reviewer identity/role required')
    if review.get('judgment') not in {'SUPPORTED','GAP','UNCERTAIN'}:raise ValueError('Invalid decision')
    if not review.get('rationale','').strip():raise ValueError('Decision rationale required')
    reasons=[];citations=[]
    if review.get('input_readable') is not True:reasons.append('Input fidelity unresolved')
    if review.get('prerequisites_complete') is not True:reasons.append('Necessary knowledge list unresolved')
    if not review.get('learner_background','').strip():reasons.append('Learner background unspecified')
    requirements=review.get('requirements',[])
    if not requirements:reasons.append('No knowledge requirements reviewed')
    statuses=[]
    for item in requirements:
        status=item.get('status');statuses.append(status)
        if status not in {'EARLIER','BACKGROUND','NOT_FOUND','UNSURE'}:raise ValueError('Incomplete requirement review')
        if not item.get('name','').strip():raise ValueError('Requirement name required')
        if status=='EARLIER':
            quote=item.get('quote','').strip()
            if not quote or quote not in prefix:raise ValueError('Supporting quote absent from admissible earlier text')
            start=prefix.index(quote)
            citations.append(dict(requirement=item['name'],quote=quote,start_offset=start,end_offset=start+len(quote)))
        if status=='BACKGROUND' and not item.get('background_reason','').strip():
            reasons.append('Background assumption lacks rationale')
        if status=='UNSURE':reasons.append('Unresolved requirement')
    if review['judgment']=='SUPPORTED' and 'NOT_FOUND' in statuses:
        reasons.append('Support decision conflicts with missing knowledge')
    if review['judgment']=='GAP':
        # Current development packets explicitly exclude a complete prior curriculum.
        if not case.get('context_complete_for_curriculum'):reasons.append('Incomplete curriculum cannot establish absence')
        if 'NOT_FOUND' not in statuses:reasons.append('Gap decision has no identified missing requirement')
    return dict(case_id=case['id'],submitted_judgment=review['judgment'],
        usable_review_judgment='UNCERTAIN' if reasons else review['judgment'],unresolved=reasons,
        citations=citations,reviewer=review['reviewer'],expert_gold=False,
        scope='assisted review under stated background; checks evidence presence, not semantic correctness')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--packet',type=Path,required=True)
    parser.add_argument('--review',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    manifest=json.loads((args.packet/'manifest.json').read_text())
    for name,digest in manifest['files'].items():
        if hashlib.sha256((args.packet/name).read_bytes()).hexdigest()!=digest:raise ValueError('Packet changed since creation')
    review=json.loads(args.review.read_text())
    case=next(c for c in json.loads((args.packet/'cases.json').read_text()) if c['id']==review['case_id'])
    result=validate(review,case,(args.packet/case['earlier_context_file']).read_text())
    with args.output.open('x') as f:json.dump(result,f,indent=2)
    print(result['usable_review_judgment'])
