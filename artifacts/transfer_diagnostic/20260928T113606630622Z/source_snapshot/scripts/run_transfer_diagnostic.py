"""Frozen-input exploratory variants; controlled passages, live production auditor."""
from datetime import datetime, timezone
import argparse
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_ncert_diagnostic import api
from src.config.settings import Settings
from src.retrieval.hybrid_orchestrator import RetrievalResult
from src.verification.auditor_prover import AuditorProver, QUESTION_SYSTEM_PROMPT, QuestionJudgment
from src.verification.lean_compiler import Lean4Compiler

BACKGROUND = 'Rational arithmetic; 1 minute = 60 seconds; SI units multiply and divide with quantities.'
HEATER = 'A heater draws 2 A at 30 V. Find its current at 90 V.'
CASES = [
    dict(id='charge', question='A current of 0.25 A flows for 2 minutes. Find the charge.',
         source='I = Q/t\nCurrent I is charge Q divided by time t in seconds.', expected='answer', value='30', units=['c','coulomb','coulombs']),
    dict(id='work', question='Find the work done moving a charge of 3 C across a potential difference of 9 V.',
         source='V = W/Q\nPotential difference V is work W in joules divided by charge Q in coulombs.', expected='answer', value='27', units=['j','joule','joules']),
    dict(id='missing_work_rule', question='Find the work done moving a charge of 3 C across a potential difference of 9 V.',
         source='Electric charge is measured in coulombs.', expected='withhold'),
    dict(id='heater_explicit', question=HEATER+' Assume constant resistance.',
         source='I = V/R\nAt unchanged resistance, current is proportional to voltage.', expected='answer', value='6', units=['a','amp','amps','ampere','amperes']),
    dict(id='heater_unstated', question=HEATER,
         source='I = V/R\nAt unchanged resistance, current is proportional to voltage.', expected='conditional', value='6', units=['a','amp','amps','ampere','amperes']),
    dict(id='heater_changing', question=HEATER+' The resistance changes with temperature; its new value is unspecified.',
         source='I = V/R\nAt unchanged resistance, current is proportional to voltage.', expected='withhold'),
]


def score(case, result):
    if result.get('status') == 'ERROR':
        return False
    if case['expected'] == 'withhold':
        return result.get('status') in {'ABSTAIN','SOURCE_REVIEW_REQUIRED','QUANTITY_REVIEW_REQUIRED','ASSUMPTION_REVIEW_REQUIRED'} and 'answer' not in result
    accepted = {'ARITHMETIC_CHECKED'} if case['expected']=='answer' else {'CONDITIONAL_ANSWER'}
    judgment=result.get('judgment',{})
    try:
        return (result.get('status') in accepted and
                Fraction(judgment['claimed_value'])==Fraction(case['value']) and
                judgment['answer_unit'].strip().lower() in case['units'])
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return False


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-file',type=Path,help='Explicit exploratory development cases; never held-out benchmark input')
    args=parser.parse_args()
    cases=json.loads(args.cases_file.read_text()) if args.cases_file else CASES
    assert cases and len({c['id'] for c in cases})==len(cases)
    for case in cases:
        assert case['id'].replace('_','').isalnum() and case['expected'] in {'answer','conditional','withhold'}
        assert len(case['source'])<1000
    run=ROOT/'artifacts/transfer_diagnostic'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    def save(name,value):
        with (run/name).open('x') as f: json.dump(value,f,indent=2)
    files={}
    for source in [*sorted((ROOT/'src').rglob('*.py')),Path(__file__).resolve()]:
        dest=run/'source_snapshot'/source.relative_to(ROOT)
        dest.parent.mkdir(parents=True,exist_ok=True); shutil.copyfile(source,dest)
        files[str(source.relative_to(ROOT))]=hashlib.sha256(source.read_bytes()).hexdigest()
    save('cases.json',cases)
    save('protocol.json',dict(scope='Synthetic exploratory development; AI-authored references; not independent or confirmatory',
        planned_calls=len(cases),model='qwen2.5-coder:7b',model_metadata=api('tags'),
        prompt=QUESTION_SYSTEM_PROMPT,schema=QuestionJudgment.model_json_schema(),
        temperature=0,seed=42,max_tokens=1000,retries=0,background=BACKGROUND,
        retrieval='Controlled single passage; retrieval and extraction not evaluated',
        cases_sha256=hashlib.sha256((run/'cases.json').read_bytes()).hexdigest(),source_hashes=files,
        scoring='Expected answer/conditional/withhold with exact rational value and declared unit aliases; ERROR never counts as correct; every scheduled attempt retained'))
    settings=Settings(_env_file=None,openai_api_key='ollama',openai_base_url='http://127.0.0.1:11434/v1',
        default_model='qwen2.5-coder:7b',openai_max_retries=0,openai_timeout=240,
        lean_binary=str(ROOT/'.tools/lean-4.26.0-darwin_aarch64/bin/lean'))
    compiler=Lean4Compiler(settings=settings,lean_project_path=run/'lean',use_mathlib=False)
    auditor=AuditorProver.__new__(AuditorProver)
    auditor.model='qwen2.5-coder:7b';auditor.settings=settings;auditor.lean_compiler=compiler
    auditor.openai=settings.create_openai_client()
    print(run,flush=True); results=[]
    try:
        for case in cases:
            passage=RetrievalResult('p1',case['source'],'controlled',1,
                dict(source_id='synthetic',start_offset=0,end_offset=len(case['source'])))
            auditor.retriever=SimpleNamespace(retrieve_for_audit=lambda *a,**k:[passage])
            start=time.monotonic()
            try:
                result=auditor.audit_question(case['question'],source_id='synthetic',before_position=1000,background=BACKGROUND)
            except Exception as exc:
                result=dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
            result.update(case_id=case['id'],elapsed_seconds=time.monotonic()-start)
            result['matches_constructed_reference']=score(case,result)
            save(case['id']+'.json',result);results.append(result)
            print(case['id'],result['status'],result.get('answer'),result['matches_constructed_reference'],flush=True)
        save('summary.json',dict(attempts=len(results),reference_matches=sum(r['matches_constructed_reference'] for r in results),
            errors=sum(r['status']=='ERROR' for r in results),results=[dict(case_id=r['case_id'],status=r['status'],matches=r['matches_constructed_reference']) for r in results]))
    finally:
        auditor.openai.close();compiler.openai.close()


if __name__=='__main__':main()
