"""Frozen local witness comparison and two full-pipeline controls."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import run_curriculum_audit as transport
from scripts.compare_local_workflows import SINGLE, SingleDecision, candidate
from scripts.check_rule_support import BACKGROUND, score
from src.verification.support_witness import PROMPT, SupportWitness, witness_schema, witness_decision, parse_witness
from src.verification.primitive_skills import explicit_operation_witness
from src.verification.curriculum_audit import audit_curriculum


def cases():
    rows=[
      ('kinetic-stated','A body has mass 4 kg and speed 3 m/s. Find its kinetic energy.','Formula for kinetic energy','Kinetic energy equals one half of mass multiplied by the square of speed.',BACKGROUND,'SUPPORTED'),
      ('kinetic-absent','A body has mass 4 kg and speed 3 m/s. Find its kinetic energy.','Formula for kinetic energy','Kinetic energy is energy associated with motion.',BACKGROUND,'UNRESOLVED'),
      ('triangle-stated','A triangle has base 8 and perpendicular height 5. Find its area.','Formula for area of a triangle','A triangle has area equal to half its base times its perpendicular height.',BACKGROUND,'SUPPORTED'),
      ('triangle-absent','A triangle has base 8 and perpendicular height 5. Find its area.','Formula for area of a triangle','A triangle has three sides. The perpendicular height is measured at a right angle to the base.',BACKGROUND,'UNRESOLVED'),
      ('division-granted','Divide 24 by 6.','Division of supplied numbers','Two numbers are supplied.',BACKGROUND,'SUPPORTED'),
      ('rule-granted','A spring has stiffness 5 and extension 2. Find the restoring-force magnitude.','Spring restoring-force magnitude formula','Stiffness and extension describe a spring.',BACKGROUND+' The learner knows the spring restoring-force magnitude F=k*x for stiffness k and extension x.','SUPPORTED'),
      ('algebra-derived','A device has power 6 and runs for 4 seconds. Find transferred energy.','Obtain transferred energy from power and duration','Power P=E/t, where E is transferred energy and t is duration; t is positive.',BACKGROUND,'SUPPORTED'),
      ('unspecified-rule','Sensor readings are u=3 and v=9. Find the adjustment index.','Adjustment index formula','An adjustment index is computed from u and v using a rule supplied in another manual.',BACKGROUND,'UNRESOLVED')]
    return [dict(id=i,payload=dict(target=t,requirement=q,evidence_catalog=[dict(evidence_id='B0',source='background',id='background',quote=b),dict(evidence_id='E0',source='passage',id='rule',quote=e)]),expected=s) for i,t,q,e,b,s in rows]


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',type=Path,required=True);a=parser.parse_args();r=a.output;r.mkdir(parents=True,exist_ok=False)
    plan=cases();hashes={}
    for path in [Path(__file__).resolve(),ROOT/'scripts/check_rule_support.py',ROOT/'scripts/compare_local_workflows.py',ROOT/'scripts/run_curriculum_audit.py',ROOT/'src/verification/support_witness.py',ROOT/'src/verification/primitive_skills.py',ROOT/'src/verification/curriculum_audit.py']:
        name=str(path.relative_to(ROOT));dest=r/'source_snapshot'/name;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(path,dest);hashes[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    old_schema=SingleDecision.model_json_schema();old_schema['properties']['evidence_ids']['items']['enum']=['B0','E0']
    manifest=dict(created=datetime.now(timezone.utc).isoformat(),plan=plan,prompts=dict(previous=SINGLE,revised=PROMPT),schemas=dict(previous=old_schema,revised=witness_schema(plan[0]['payload']['evidence_catalog'])),source_hashes=hashes,model='qwen2.5-coder:7b',reviewer='mistral:latest',temperature=0,seed=42,budgets=dict(previous=500,revised=750),context_tokens=16384,retries=0,time_budget_seconds=1200,per_call_timeout_seconds=180,order='Alternating arm order per requirement case; full-pipeline baseline then witness',pipeline_case_ids=['kinetic-stated','kinetic-absent'],scope='Eight synthetic requirement controls and two full-pipeline controls. Not independent expert labels; overlapping pipeline cases are not additional independent samples.',adoption_rule='Require improved strict outcomes without new false support, preserved supported decisions and original regression repaired. Keep experimental pending broader independent validation.')
    mp=r/'manifest.json';mp.write_text(json.dumps(manifest,indent=2));mh=hashlib.sha256(mp.read_bytes()).hexdigest()
    for ep in ['tags','version']:
        with urlopen(transport.ollama_base_url()+'/api/'+ep,timeout=10) as response:(r/f'ollama-{ep}.json').write_bytes(response.read())
    transport.DEADLINE=time.monotonic()+1200;transport.REQUEST_TIMEOUT_SECONDS=180;results=[];pipelines=[]
    try:
        for i,c in enumerate(plan,1):
            for arm in (['previous','revised'] if i%2 else ['revised','previous']):
                payload=c['payload'] if arm=='previous' else {k:v for k,v in c['payload'].items() if k!='target'}
                out=dict(case_id=c['id'],arm=arm,messages=[dict(role='system',content=manifest['prompts'][arm]),dict(role='user',content=json.dumps(payload))]);start=time.monotonic()
                direct=explicit_operation_witness(payload['requirement'],payload['evidence_catalog']) if arm=='revised' else None
                if direct is not None:
                    out.update(witness=direct.model_dump(),decision=witness_decision(direct,payload['evidence_catalog'],0).model_dump(),origin='explicit_learner_grant',seconds=round(time.monotonic()-start,3))
                    results.append(out);(r/f'{i:02}-{arm}.json').write_text(json.dumps(out,indent=2));print(c['id'],arm,out['decision']['status'],flush=True)
                    continue
                try:
                    resp=transport.local_completion(model=manifest['model'],messages=out['messages'],temperature=0,seed=42,max_tokens=manifest['budgets'][arm],response_format={'type':'json_schema','json_schema':{'name':'requirement','strict':True,'schema':manifest['schemas'][arm]}});out['response']=resp.model_dump()
                    if resp.choices[0].finish_reason!='stop':raise ValueError('Incomplete output')
                    if arm=='revised':
                        w=parse_witness(resp.choices[0].message.content,c['payload']['evidence_catalog']);out['witness']=w.model_dump();d=witness_decision(w,c['payload']['evidence_catalog'],0)
                    else:
                        d=SingleDecision.model_validate_json(resp.choices[0].message.content);ids=set(d.evidence_ids)
                        if not ids<={'B0','E0'} or (d.status=='UNRESOLVED' and ids) or (d.status!='UNRESOLVED' and not ids):raise ValueError('Invalid evidence references')
                    out['decision']=d.model_dump()
                except Exception as exc:out['error']=f'{type(exc).__name__}: {exc}'
                out['seconds']=round(time.monotonic()-start,3);results.append(out);(r/f'{i:02}-{arm}.json').write_text(json.dumps(out,indent=2));print(c['id'],arm,out.get('decision',{}).get('status',out.get('error')),flush=True)
                if 'timed out' in out.get('error','').lower() or 'timeout' in out.get('error','').lower():raise TimeoutError('Stop after timeout')
        client=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=transport.local_completion)))
        for c in plan[:2]:
            p=c['payload'];source=c['id'];records=[dict(id='rule',content=p['evidence_catalog'][1]['quote'],position=0,source_id=source,module_id=source,kind='para',instructional_role='exposition')];target=dict(id='target',content=p['target'],position=1,source_id=source,module_id=source,kind='exercise',instructional_role='exercise_material');records.append(target)
            for arm in ['baseline','witness']:
                dest=r/f'pipeline-{source}-{arm}.json'
                def checkpoint(o):
                    tmp=dest.with_suffix('.tmp');tmp.write_text(json.dumps(o,indent=2));tmp.replace(dest)
                start=time.monotonic()
                if arm=='baseline':base=audit_curriculum(client,manifest['model'],manifest['reviewer'],records,target,p['evidence_catalog'][0]['quote'],checkpoint=checkpoint);out=base
                else:out=candidate(base,checkpoint,evidence_first=True)
                out.update(case_id=source,arm=arm,seconds=round(time.monotonic()-start,3));checkpoint(out);pipelines.append(out);print('pipeline',source,arm,out['status'],flush=True)
                if 'timed out' in out.get('error','').lower() or 'timeout' in out.get('error','').lower():raise TimeoutError('Stop after timeout')
    finally:
        ok=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==h for n,h in hashes.items());same=hashlib.sha256(mp.read_bytes()).hexdigest()==mh
        (r/'summary.json').write_text(json.dumps(dict(requirement_completed=len(results),arms=score(plan,results),pipeline=[{k:o.get(k) for k in ['case_id','arm','status','seconds','error']} for o in pipelines],code_unchanged=ok,manifest_unchanged=same,accuracy=None,independent_labels=False),indent=2))
        if not ok or not same:raise ValueError('Frozen sources changed')

if __name__=='__main__':main()
