"""Replay saved application outputs and retrieval; no fresh model inference."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config.settings import Settings
from src.retrieval.hybrid_orchestrator import RetrievalResult
from src.verification.auditor_prover import AuditorProver
from src.verification.lean_compiler import Lean4Compiler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    rows = json.loads(args.input.read_text())
    run = ROOT/'artifacts/numeric_conversion_replay'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    print(run, flush=True)
    hashes = {}
    for source in [*sorted((ROOT/'src').rglob('*.py')), Path(__file__).resolve()]:
        destination = run/'source_snapshot'/source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        hashes[str(source.relative_to(ROOT))] = hashlib.sha256(source.read_bytes()).hexdigest()
    (run/'manifest.json').write_text(json.dumps(dict(input=str(args.input),
        input_sha256=hashlib.sha256(args.input.read_bytes()).hexdigest(), source_hashes=hashes,
        fresh_model_calls=0, live_retrieval=False, real_core_lean=True,
        scope='Exposed development replay; no independent accuracy claim'), indent=2))
    settings = Settings(_env_file=None, openai_api_key='unused',
        lean_binary=str(ROOT/'.tools/lean-4.26.0-darwin_aarch64/bin/lean'))
    compiler = Lean4Compiler(settings=settings,lean_project_path=run/'lean',use_mathlib=False)
    results = []
    try:
        for saved in rows:
            if saved['comparison_mode'] == 'direct':
                continue
            payload = json.loads(saved['messages'][1]['content'])
            retrieval = [RetrievalResult(**r) for r in saved['retrieval']]
            assert all(r.metadata['source_id']==payload['source_id'] and
                       r.metadata['end_offset']<=payload['target_start_offset'] for r in retrieval)
            response = SimpleNamespace(choices=[SimpleNamespace(finish_reason='stop',
                message=SimpleNamespace(content=json.dumps(saved['judgment'])))],
                model_dump=lambda: saved['response'])
            auditor = AuditorProver.__new__(AuditorProver)
            auditor.model='saved-response-replay'; auditor.lean_compiler=compiler
            auditor.retriever=SimpleNamespace(retrieve_for_audit=lambda *a,**k: retrieval)
            auditor.openai=SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: response)))
            result = auditor.audit_question(payload['question'],source_id=payload['source_id'],
                before_position=payload['target_start_offset'],background=payload['background'])
            result.update(case_id=saved['case_id'],comparison_mode=saved['comparison_mode'],
                          previous_status=saved['status'])
            results.append(result)
            (run/'results.json').write_text(json.dumps(results,indent=2))
            print(result['case_id'],result['comparison_mode'],result['status'],result.get('answer'),flush=True)
    finally:
        compiler.openai.close()
    (run/'COMPLETE.json').write_text(json.dumps(dict(attempts=len(results)),indent=2))


if __name__ == '__main__':
    main()
