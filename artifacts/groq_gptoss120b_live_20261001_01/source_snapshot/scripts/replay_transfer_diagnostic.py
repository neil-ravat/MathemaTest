"""Replay a preserved development diagnostic with original raw model responses.

No inference or live retrieval. Original studies are never modified.
"""
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
from scripts.run_transfer_diagnostic import score
from src.config.settings import Settings
from src.retrieval.hybrid_orchestrator import RetrievalResult
from src.verification.auditor_prover import AuditorProver
from src.verification.lean_compiler import Lean4Compiler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('input', type=Path)
    args = parser.parse_args()
    cases = json.loads((args.input/'cases.json').read_text())
    run = ROOT/'artifacts/transfer_replay'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    files = [args.input/'cases.json', args.input/'protocol.json']
    files += [args.input/(c['id']+'.json') for c in cases]
    hashes = {str(p): hashlib.sha256(p.read_bytes()).hexdigest() for p in files}
    source_hashes = {}
    for p in [*sorted((ROOT/'src').rglob('*.py')), Path(__file__).resolve(), ROOT/'scripts/run_transfer_diagnostic.py']:
        dest = run/'source_snapshot'/p.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, dest)
        source_hashes[str(p.relative_to(ROOT))] = hashlib.sha256(p.read_bytes()).hexdigest()
    (run/'manifest.json').write_text(json.dumps(dict(input_hashes=hashes, source_hashes=source_hashes,
        fresh_model_calls=0, live_retrieval=False, scope='Exposed development replay; not fresh accuracy'), indent=2))
    settings = Settings(_env_file=None, openai_api_key='unused',
                        lean_binary=str(ROOT/'.tools/lean-4.26.0-darwin_aarch64/bin/lean'))
    compiler = Lean4Compiler(settings=settings, lean_project_path=run/'lean', use_mathlib=False)
    results = []
    try:
        for case in cases:
            saved = json.loads((args.input/(case['id']+'.json')).read_text())
            payload = json.loads(saved['messages'][1]['content'])
            choice = saved['response']['choices'][0]
            response = SimpleNamespace(choices=[SimpleNamespace(finish_reason=choice['finish_reason'],
                message=SimpleNamespace(content=choice['message']['content']))], model_dump=lambda: saved['response'])
            auditor = AuditorProver.__new__(AuditorProver)
            auditor.model = 'saved-response-replay'; auditor.lean_compiler = compiler
            auditor.retriever = SimpleNamespace(retrieve_for_audit=lambda *a, **k: [RetrievalResult(**r) for r in saved['retrieval']])
            auditor.openai = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **k: response)))
            result = auditor.audit_question(payload['question'], source_id=payload['source_id'],
                before_position=payload['target_start_offset'], background=payload['background'])
            result.update(case_id=case['id'], previous_status=saved['status'], matches_constructed_reference=score(case, result))
            (run/(case['id']+'.json')).write_text(json.dumps(result, indent=2))
            results.append(result)
            print(case['id'], result['status'], result['matches_constructed_reference'], flush=True)
    finally:
        compiler.openai.close()
    assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest() == h for p, h in hashes.items())
    assert all(hashlib.sha256((ROOT/p).read_bytes()).hexdigest() == h for p, h in source_hashes.items())
    (run/'summary.json').write_text(json.dumps(dict(attempts=len(results),
        reference_matches=sum(r['matches_constructed_reference'] for r in results),
        input_hashes_unchanged=True, code_hashes_unchanged=True, fresh_model_calls=0), indent=2))
    print(run)


if __name__ == '__main__':
    main()
