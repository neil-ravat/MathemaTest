"""Checks for leakage, deterministic labels, evidence contracts, and evaluation gates."""
import copy
import json
import hashlib
from collections import Counter

import pytest

from scripts.controlled_benchmark import generate, freeze, oracle, digest
from scripts.run_controlled_study import context_for, decode, EvidenceError, summarize, authorize_heldout, code_hash, gate_cases, MODELS


def test_benchmark_oracle_and_frozen_split(tmp_path):
    cases=generate()
    assert Counter(c['category'] for c in cases)=={k:20 for k in ('supported','missing','future','background','preview','false')}
    dev={c['family'] for c in cases if c['split']=='development'}
    held={c['family'] for c in cases if c['split']=='heldout'}
    assert len(dev)==8 and len(held)==12 and not dev & held
    for c in cases:
        assert oracle(c)[0]==c['expected']
    c=copy.deepcopy(next(c for c in cases if c['category']=='supported'))
    c['oracle']['claim']+=1
    assert oracle(c)[0]=='FAIL_LOGIC'
    freeze(tmp_path);freeze(tmp_path)
    (tmp_path/'heldout.json').write_text('changed')
    with pytest.raises(ValueError,match='Frozen benchmark'):
        freeze(tmp_path)


def test_retrieval_boundaries_graph_and_no_gold_payload():
    cases=generate()
    for c in cases:
        for arm in ('none','lexical','graph','complete'):
            p=context_for(c,arm)
            assert all(d['position']<c['target_position'] for d in p['context'])
            assert not {'expected','oracle','required_ids','category','family'} & p.keys()
            if arm!='complete':
                assert len(p['context'])<=4
        if c['category']=='supported':
            assert set(c['required_ids']) <= {d['id'] for d in context_for(c,'graph')['context']}
    # Traversal must not expand a future intermediary to leak its earlier child.
    c={'documents':[{'id':'future','position':101,'content':'future','references':['past']},
                    {'id':'past','position':1,'content':'past','references':[]}],
       'references':['future'],'target_position':100,'target':'test','background':'','background_passages':[]}
    assert context_for(c,'graph')['context']==[]


def test_evidence_contract_and_failure_denominator():
    p={'target_position':5,'context_complete':False,'background_passages':[],
       'context':[{'id':'past','position':1},{'id':'future','position':6}]}
    v={'status':'PASS','reason':'support','missing_prerequisites':[],'confidence':0.5,'cited_passage_ids':['past']}
    assert decode(json.dumps(v),p)['status']=='PASS'
    for citation in ('invented','future'):
        with pytest.raises(EvidenceError):
            decode(json.dumps({**v,'cited_passage_ids':[citation]}),p)
    with pytest.raises(EvidenceError):
        decode(json.dumps({**v,'status':'FAIL_GAP'}),p)
    p['context_complete']=True
    assert decode(json.dumps({**v,'status':'FAIL_GAP','cited_passage_ids':[]}),p)['status']=='FAIL_GAP'
    rows=[{'model':'x','prompt':'p','arm':'none','family':'f','category':'c','expected':'PASS',
           'future_items':0,'seconds':1,'error_type':'json_format'}]
    summary=next(iter(summarize(rows).values()))
    assert summary['attempts']==1 and summary['exact_matches']==0 and summary['per_class']['PASS']['recall']==0


def test_gate_rejects_failure_and_changed_protocol(tmp_path):
    manifest={'test':'benchmark'};metadata={'models':[]}
    record={'phase':'gate','code_hash':code_hash(),'benchmark_manifest_hash':digest(manifest),'model_metadata':metadata}
    (tmp_path/'manifest.json').write_text(json.dumps(record))
    rows=[{'case_id':c['id'],'model':m,'prompt':'evidence','arm':'complete','expected':c['expected'],
           'verdict':{'status':c['expected']}} for m in MODELS for c in gate_cases()]
    (tmp_path/'predictions.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    (tmp_path/'COMPLETE.json').write_text(json.dumps({'predictions_sha256':hashlib.sha256((tmp_path/'predictions.jsonl').read_bytes()).hexdigest()}))
    authorize_heldout(tmp_path,manifest,'evidence',metadata)
    rows[0]['verdict']['status']='ABSTAIN'
    (tmp_path/'predictions.jsonl').write_text('\n'.join(map(json.dumps,rows)))
    (tmp_path/'COMPLETE.json').write_text(json.dumps({'predictions_sha256':hashlib.sha256((tmp_path/'predictions.jsonl').read_bytes()).hexdigest()}))
    with pytest.raises(ValueError,match='gate failed'):
        authorize_heldout(tmp_path,manifest,'evidence',metadata)
    record['code_hash']='changed';(tmp_path/'manifest.json').write_text(json.dumps(record))
    with pytest.raises(ValueError,match='identical'):
        authorize_heldout(tmp_path,manifest,'evidence',metadata)
