"""Development replay of a saved answer, not fresh inference or live retrieval."""
import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src.config.settings import Settings
from src.retrieval.hybrid_orchestrator import RetrievalResult
from src.verification.auditor_prover import AuditorProver
from src.verification.lean_compiler import Lean4Compiler


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    saved=next(r for r in json.loads(args.input.read_text()) if r['case_id']=='jesc111:example-11.4')
    payload=json.loads(saved['messages'][1]['content'])
    args.output.mkdir(parents=True,exist_ok=False)
    settings=Settings(_env_file=None,openai_api_key='unused',
        lean_binary=str(ROOT/'.tools/lean-4.26.0-darwin_aarch64/bin/lean'))
    compiler=Lean4Compiler(settings=settings,lean_project_path=args.output/'lean',use_mathlib=False)
    rows=[RetrievalResult(**r) for r in saved['retrieval']]
    assert all(r.metadata['source_id']==payload['source_id'] and
               r.metadata['end_offset']<=payload['target_start_offset'] for r in rows)
    model_reply=SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
        message=SimpleNamespace(content=json.dumps(saved['judgment'])))],model_dump=lambda:saved['response'])
    auditor=AuditorProver.__new__(AuditorProver)
    auditor.settings=settings;auditor.model='saved-response-replay';auditor.lean_compiler=compiler
    auditor.retriever=SimpleNamespace(retrieve_for_audit=lambda *a,**k:rows)
    auditor.openai=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k:model_reply)))
    variants=[('original','', 'CONDITIONAL_ANSWER'),
              ('explicit_condition',' Assume the heater resistance remains constant.','ARITHMETIC_CHECKED'),
              ('changing_resistance',' The heater resistance changes with temperature.','ASSUMPTION_REVIEW_REQUIRED')]
    results=[]
    try:
        for name,suffix,expected in variants:
            result=auditor.audit_question(payload['question']+suffix,source_id=payload['source_id'],
                before_position=payload['target_start_offset'],background=payload['background'])
            assert result['status']==expected,(name,result)
            result.update(variant=name,development_replay=True,fresh_model_calls=0)
            results.append(result)
            print(name,result['status'],result.get('answer','no accepted answer'))
    finally:
        compiler.openai.close()
    (args.output/'results.json').write_text(json.dumps(results,indent=2)+'\n')
    files=['src/verification/parameter_support.py','src/verification/assumption_consistency.py','src/verification/auditor_prover.py',
           'src/verification/lean_compiler.py','src/verification/rational_calculator.py','scripts/replay_answer_conditions.py']
    hashes={}
    for name in files:
        source=ROOT/name;dest=args.output/'source_snapshot'/name
        dest.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,dest)
        hashes[name]=hashlib.sha256(source.read_bytes()).hexdigest()
    (args.output/'manifest.json').write_text(json.dumps(dict(input=str(args.input),
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(),source_hashes=hashes,
        mode='Saved model response and saved retrieval replay; variant questions are development perturbations',
        real_lean_compilation=True,fresh_model_calls=0,live_retrieval=False,expert_gold=False,
        benchmark_accuracy=False),indent=2)+'\n')


if __name__=='__main__':main()
