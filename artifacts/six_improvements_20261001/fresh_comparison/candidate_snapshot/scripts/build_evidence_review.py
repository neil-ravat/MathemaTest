"""Export retrospective, unblinded review cards from a saved diagnostic run."""
import argparse
import hashlib
import json
import re
from pathlib import Path


def validate_groups(rows):
    """Check declared groups; cannot infer omitted family/source relationships."""
    seen, owners = set(), {}
    for row in rows:
        if row['id'] in seen or row['split'] not in {'development','validation','test'}:
            raise ValueError('Duplicate case or invalid split')
        seen.add(row['id'])
        if not row['groups'] or any(not isinstance(g,str) or not g.strip() for g in row['groups']):
            raise ValueError('Explicit nonempty grouping keys required')
        if type(row['exposed']) is not bool:
            raise ValueError('Explicit exposure boolean required')
        if row['split']=='test' and row['exposed']:
            raise ValueError('Exposed case cannot enter test')
        for group in row['groups']:
            if group in owners and owners[group]!=row['split']:
                raise ValueError('Group crosses splits: '+group)
            owners[group]=row['split']
    return dict(cases=len(rows),groups=len(owners),test_cases=sum(r['split']=='test' for r in rows),
                scope='Declared group/exposure consistency only; not independent-label or full evaluation authorization')


def block(value):
    text=value if isinstance(value,str) else json.dumps(value,indent=2,ensure_ascii=False)
    fence='`'*(max([len(x) for x in re.findall(r'`+',text)]+[2])+1)
    return fence+'\n'+text+'\n'+fence+'\n'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run',type=Path)
    parser.add_argument('groups',type=Path)
    parser.add_argument('output',type=Path)
    args=parser.parse_args()
    cases=json.loads((args.run/'cases.json').read_text())
    groups=json.loads(args.groups.read_text())
    check=validate_groups(groups)
    if {c['id'] for c in cases}!={r['id'] for r in groups}:
        raise ValueError('Grouping manifest must cover exactly these cases')
    protocol=json.loads((args.run/'protocol.json').read_text())
    if hashlib.sha256((args.run/'cases.json').read_bytes()).hexdigest()!=protocol['cases_sha256']:
        raise ValueError('Frozen cases hash mismatch')
    cards=['# MathemaTest evidence review\n',
           'Retrospective, unblinded development review. Model explanations are claims, not proof. '
           'Constructed references are AI-authored. Reviewer decisions are unfilled.\n']
    reviews=[];hashes={}
    for c in cases:
        if not re.fullmatch(r'[A-Za-z0-9_]+',c['id']):
            raise ValueError('Unsafe case filename')
        path=args.run/(c['id']+'.json');r=json.loads(path.read_text());j=r.get('judgment',{})
        if r.get('case_id')!=c['id']:
            raise ValueError('Case/result identity mismatch')
        digest=hashlib.sha256(path.read_bytes()).hexdigest();hashes[path.name]=digest
        payload=json.loads(r['messages'][1]['content']) if r.get('messages') else None
        if payload and (payload['question']!=c['question'] or [p['text'] for p in payload['context']]!=[c['source']]):
            raise ValueError('Scheduled and supplied evidence differ')
        checks={k:r[k] for k in ('calculation_check','numeric_input_support','quantity_mapping',
            'heater_quantity_mapping','assumption_consistency','resistance_condition_check','answer_conditions') if k in r}
        if 'calculation_check' in checks:
            checks['calculation_check']={k:v for k,v in checks['calculation_check'].items() if k!='lean_code'}
        cards += ['## '+c['id']+'\n',
            '**Question**\n'+block(c['question']), '**Recorded model context and background**\n'+block(
                {'context':payload['context'],'background':payload['background']} if payload else 'No recorded model payload'),
            '**Application decision**\n'+block(dict(status=r['status'],answer=r.get('answer'),error=r.get('error'),
                abstention_kind=r.get('abstention_kind'),output_validation=r.get('output_validation'))),
            '**Model claim (unverified explanation)**\n'+block(j),
            '**Executed checks and evidence**\n'+block(checks),
            '**Constructed reference (not expert gold)**\n'+block({k:c[k] for k in ('expected','value','units') if k in c}),
            '**Recorded result SHA-256:** '+digest+'\n']
        reviews.append(dict(case_id=c['id'],result_sha256=digest,reviewer_id=None,reviewer_qualification=None,
            numerical_correctness=None,source_support=None,assumptions_adequate=None,
            decision_appropriate=None,evidence_ids=[],notes=None,reviewed_at=None,
            blinded=False,expert_gold=False))
    args.output.mkdir(parents=True,exist_ok=False)
    (args.output/'cards.md').write_text('\n'.join(cards))
    (args.output/'review_decisions.json').write_text(json.dumps(reviews,indent=2))
    (args.output/'manifest.json').write_text(json.dumps(dict(input_run=str(args.run.resolve()),
        group_check=check,result_hashes=hashes,cases_sha256=protocol['cases_sha256'],
        group_manifest_sha256=hashlib.sha256(args.groups.read_bytes()).hexdigest(),
        review_status='UNREVIEWED',scope='Evidence display; no attribution-faithfulness or independent validity claim'),indent=2))
    (args.output/'groups.json').write_text(json.dumps(groups,indent=2))
    print(args.output/'cards.md')


if __name__=='__main__':main()
