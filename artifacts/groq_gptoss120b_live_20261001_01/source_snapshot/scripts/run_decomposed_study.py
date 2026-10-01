"""Development-only evidence extraction plus deterministic integer calculation/decision.

This is calculator-assisted evaluation, not formal verification: the model still
chooses dependencies and substitutes definitions. No heldout mode is provided.
"""
import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import sys
import time
from typing import Literal
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from scripts.run_controlled_study import (
    MODELS, EvidenceError, context_for, gate_cases, summarize,
)
from scripts.controlled_benchmark import DEST, digest
from src.config.settings import Settings

PROMPT = '''Extract evidence for the target using ONLY supplied earlier context and background.
Combine context with background_passages and background_knowledge. Never use a context
passage with position greater than or equal to target_position.
Do not choose a verdict. First identify all definitions needed, including definitions
used inside other definitions. A supplied definition needs no separate proof or example.
If any needed definition is absent, name it in missing_prerequisites; do not invent it.
When every needed definition is available, substitute recursively and return a fully
numeric integer expression using only parentheses, +, -, and *. Preserve the operations
from the definitions. A calculator will evaluate this expression and compare it to the
claimed integer; do not replace your expression with the claimed answer.
An explicit preview saying no calculation or proof is asserted/required needs no calculation.
Return exactly one JSON object with these fields:
target_kind: "equality", "preview", or "other";
claimed_value: the integer on the right of the target equality, or null if not an equality;
calculation: the fully substituted numeric expression, or null for a preview, absent
prerequisite, or unsupported task;
missing_prerequisites: array of names of absent definitions (empty if none);
cited_passage_ids: array of exact IDs of supplied passages used, including background;
reason: a brief nonempty explanation of substitutions or why calculation is unavailable.
Use target_kind "other" for unsupported tasks. Never cite a future or absent passage.
Return no status or verdict field.'''
PROTOCOL = 'decomposed'


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    target_kind: Literal['equality', 'preview', 'other']
    claimed_value: int | None
    calculation: str | None
    missing_prerequisites: list[str]
    cited_passage_ids: list[str]
    reason: str = Field(min_length=1)


def calculate(expression):
    """Bounded arithmetic only; never eval model text or accept executable syntax."""
    if len(expression) > 2000:
        raise EvidenceError('Calculation too long')
    tree = ast.parse(expression.strip(), mode='eval')
    if len(list(ast.walk(tree))) > 256:
        raise EvidenceError('Calculation too complex')

    def visit(node):
        if isinstance(node, ast.Constant) and type(node.value) is int:
            value = node.value
        elif isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
            value = visit(node.operand) * (-1 if isinstance(node.op, ast.USub) else 1)
        elif isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Sub, ast.Mult)):
            a, b = visit(node.left), visit(node.right)
            value = a+b if isinstance(node.op, ast.Add) else a-b if isinstance(node.op, ast.Sub) else a*b
        else:
            raise EvidenceError('Only integer literals, parentheses, +, -, * are supported')
        if abs(value) > 10**12:
            raise EvidenceError('Calculation outside bounded integer range')
        return value

    return visit(tree.body)


def decide(evidence, payload):
    """Use only model evidence and public payload; never case labels or oracle nodes."""
    e = Evidence.model_validate(evidence)
    allowed = {d['id'] for d in payload['context'] if d['position'] < payload['target_position']}
    allowed.update(d['id'] for d in payload['background_passages'])
    if not set(e.cited_passage_ids) <= allowed:
        raise EvidenceError('Nonexistent, non-retrieved, or future citation')
    if any(not name.strip() for name in e.missing_prerequisites):
        raise EvidenceError('Empty missing prerequisite')
    # The narrow public-text guard prevents a model changing an equality into a preview
    # or changing the stated right-hand-side integer to make its calculation agree.
    preview = bool(re.match(r'^Preview\b', payload['target'], re.I) and
                   re.search(r'no calculation or proof', payload['target'], re.I))
    claim = re.search(r'=\s*([+-]?\d+)\s*\.?\s*$', payload['target'])
    kind = 'preview' if preview else 'equality' if claim else 'other'
    if e.target_kind != kind:
        raise EvidenceError('Target kind contradicts public target text')
    expected_claim = int(claim.group(1)) if kind == 'equality' else None
    if e.claimed_value != expected_claim:
        raise EvidenceError('Claimed integer contradicts public target text')
    computed = None
    if kind in ('preview', 'other'):
        if e.calculation is not None or e.missing_prerequisites:
            raise EvidenceError('Non-calculation target has conflicting calculation or missing prerequisites')
        status = 'PASS' if kind == 'preview' else 'ABSTAIN'
    elif e.missing_prerequisites:
        if e.calculation is not None:
            raise EvidenceError('Cannot calculate with reported missing prerequisites')
        status = 'FAIL_GAP' if payload['context_complete'] else 'ABSTAIN'
    elif e.calculation is None:
        status = 'ABSTAIN'
    else:
        computed = calculate(e.calculation)
        status = 'PASS' if computed == e.claimed_value else 'FAIL_LOGIC'
    return {'status': status, 'reason': e.reason,
            'missing_prerequisites': e.missing_prerequisites,
            'cited_passage_ids': e.cited_passage_ids}, computed


def error_fields(exc):
    return {'error_type': 'json_format' if isinstance(exc, json.JSONDecodeError) else
            'output_schema' if isinstance(exc, ValidationError) else
            'evidence_or_scope' if isinstance(exc, (EvidenceError, SyntaxError)) else
            'runtime_or_truncation', 'error': str(exc)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase', choices=['gate', 'development'], required=True)
    args = parser.parse_args()
    manifest = json.loads((DEST/'manifest.json').read_text())
    # Deliberately do not open or hash heldout.json, even for integrity checking.
    development_bytes = (DEST/'development.json').read_bytes()
    if hashlib.sha256(development_bytes).hexdigest() != manifest['files']['development.json']:
        raise ValueError('Frozen development benchmark changed')
    cases = gate_cases() if args.phase == 'gate' else json.loads(development_bytes)
    if args.phase == 'development' and (len(cases) != 48 or len({c['id'] for c in cases}) != 48):
        raise ValueError('Exactly 48 distinct development cases required')
    settings = Settings(_env_file=None, openai_api_key='ollama',
                        openai_base_url='http://127.0.0.1:11434/v1',
                        openai_timeout=120, openai_max_retries=0)
    client = settings.create_openai_client()
    metadata = client.models.list().model_dump()
    if not set(MODELS) <= {m['id'] for m in metadata['data']}:
        raise ValueError('Both frozen study models must be available locally')
    with urlopen('http://127.0.0.1:11434/api/tags', timeout=10) as response:
        ollama_tags = json.load(response)
    if not all(any(m.get('name') == name and m.get('digest') for m in ollama_tags['models']) for name in MODELS):
        raise ValueError('Cannot establish local model digests')
    run = ROOT/'artifacts/controlled_study'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    sources = {}
    for directory in ('src', 'scripts'):
        for path in sorted((ROOT/directory).rglob('*.py')):
            relative = path.relative_to(ROOT)
            target = run/'source_snapshot'/relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
            sources[str(relative)] = hashlib.sha256(target.read_bytes()).hexdigest()
    lock = ROOT/'requirements-local.lock.txt'
    shutil.copyfile(lock, run/lock.name)
    with (run/'manifest.json').open('x') as f:
        json.dump({'phase': args.phase, 'arms': ['complete'], 'prompts': [PROTOCOL],
                   'models': MODELS, 'code_hash': digest(sources), 'source_sha256': sources,
                   'requirements_sha256': hashlib.sha256(lock.read_bytes()).hexdigest(),
                   'benchmark_manifest_hash': digest(manifest), 'model_metadata': metadata,
                   'ollama_tags': ollama_tags, 'temperature': 0, 'seed': 42, 'max_tokens': 500,
                   'case_count': len(cases), 'prompt_texts': {PROTOCOL: PROMPT},
                   'context_budget': {'complete_diagnostic': 'all earlier passages'},
                   'decision_rule': 'validated preview PASS; reported missing prerequisite FAIL_GAP if complete else ABSTAIN; integer expression compared to source claim; unsupported ABSTAIN; inconsistent evidence ERROR',
                   'limitations': ['Calculator-assisted protocol, not a prompt-only comparison',
                                   'Model dependency extraction and substitutions are not formally verified',
                                   'Public target parser supports explicit previews and integer right-hand-side equalities only',
                                   'This runner cannot authorize or execute heldout evaluation']}, f, indent=2)
    print('Run:', run, flush=True)
    rows = []
    with (run/'predictions.jsonl').open('x') as output:
        for model in MODELS:
            for case in cases:
                payload = context_for(case, 'complete')
                messages = [{'role': 'system', 'content': PROMPT},
                            {'role': 'user', 'content': json.dumps(payload)}]
                row = {'case_id': case['id'], 'family': case['family'], 'category': case['category'],
                       'expected': case['expected'], 'model': model, 'prompt': PROTOCOL,
                       'arm': 'complete', 'messages': messages, 'context_complete': True,
                       'future_items': 0, 'model_calls': 1, 'stages': []}
                started = time.monotonic()
                stage = {'stage': 'evidence', 'messages': messages}
                try:
                    response = client.chat.completions.create(model=model, messages=messages,
                        temperature=0, seed=42, max_tokens=500, response_format={'type': 'json_object'})
                    row['response'] = stage['response'] = response.model_dump()
                    if response.choices[0].finish_reason != 'stop':
                        raise ValueError('Truncated response')
                    row['evidence'] = Evidence.model_validate(json.loads(response.choices[0].message.content)).model_dump()
                except Exception as exc:
                    row.update(error_fields(exc)); stage.update(error_fields(exc))
                stage['seconds'] = time.monotonic()-started
                row['stages'].append(stage)
                if 'evidence' in row:
                    decision_started = time.monotonic()
                    stage = {'stage': 'decision', 'evidence': row['evidence']}
                    try:
                        verdict, computed = decide(row['evidence'], payload)
                        row['verdict'] = stage['verdict'] = verdict
                        row['computed_value'] = stage['computed_value'] = computed
                    except Exception as exc:
                        row.update(error_fields(exc)); stage.update(error_fields(exc))
                    stage['seconds'] = time.monotonic()-decision_started
                    row['stages'].append(stage)
                row['seconds'] = time.monotonic()-started
                row['correct'] = row.get('verdict', {}).get('status') == case['expected']
                rows.append(row)
                output.write(json.dumps(row)+'\n'); output.flush()
                print(model, case['id'], row.get('verdict', {}).get('status', row.get('error_type')), flush=True)
    with (run/'summary.json').open('x') as f:
        json.dump(summarize(rows), f, indent=2)
    with (run/'COMPLETE.json').open('x') as f:
        json.dump({'calls': sum(r['model_calls'] for r in rows), 'rows': len(rows),
                   'predictions_sha256': hashlib.sha256((run/'predictions.jsonl').read_bytes()).hexdigest()}, f)
    client.close()
    print('Saved:', run, flush=True)


if __name__ == '__main__':
    main()
