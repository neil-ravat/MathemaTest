"""Local-only, append-only technical evaluation with an enforced heldout gate."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import random
import re
import shutil
import sys
import time
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pydantic import ValidationError
from src.config.settings import Settings
from src.verification.verdicts import AuditVerdict
from scripts.controlled_benchmark import DEST, digest
from scripts.run_local_pilot import PROMPT as ORIGINAL_PROMPT, fixture_data

ARMS = ('none', 'vector', 'position_filtered', 'lexical', 'graph')
MODELS = ('qwen2.5-coder:7b', 'mistral:latest')
EVIDENCE_PROMPT = '''Judge the target using the supplied definitions and background. Integer arithmetic
and substitution are allowed: a definition f(x)=x+1 is sufficient to evaluate f(2).
PASS: the stated equality follows, or the target is explicitly only a preview.
FAIL_LOGIC: the available definitions give a different numerical result.
FAIL_GAP: a needed definition is absent AND context_complete is true.
ABSTAIN: necessary evidence is absent from an incomplete context.
Do not require a separate example or proof of a definition. An empty context does not
prevent using the explicitly supplied background arithmetic. A preview needs no proof.
Only passages earlier than target_position and supplied background_passages may support
the judgment. Future passages are inadmissible even if they contain the answer.
Give a brief calculation or evidence explanation. No Lean code.'''
CONTRACT = '''\nReturn one JSON object: status (PASS, FAIL_GAP, FAIL_LOGIC, ABSTAIN),
reason (nonempty string), missing_prerequisites (array of strings), confidence (0..1),
cited_passage_ids (array of exact IDs of passages used). Cite background passages when used.
Use [] if the judgment only needs ordinary stated arithmetic or identifies absent evidence.
Never cite a future passage or an ID not supplied. context_complete is provided by the
runner: only when true does the context exhaust the earlier curriculum. Otherwise absent
retrieval alone cannot establish FAIL_GAP.'''


class EvidenceVerdict(AuditVerdict):
    cited_passage_ids: list[str]


class EvidenceError(ValueError):
    pass


def decode(content, payload):
    value = EvidenceVerdict.model_validate(json.loads(content))
    allowed = {d['id'] for d in payload['context'] if d['position'] < payload['target_position']}
    allowed.update(d['id'] for d in payload['background_passages'])
    if not set(value.cited_passage_ids) <= allowed:
        raise EvidenceError('Nonexistent, non-retrieved, or future citation')
    if value.status == 'FAIL_GAP' and not payload['context_complete']:
        raise EvidenceError('Missing prerequisite asserted from incomplete retrieval')
    return value.model_dump()


def gate_cases():
    docs, cases = fixture_data()
    return [{'id': c['id'], 'family': c['id'], 'category': c['id'], 'target': c['content'],
             'target_position': c['position'], 'background': c['background'],
             'background_passages': [], 'documents': [{**d, 'references': []} for d in docs],
             'references': [], 'expected': c['expected'], 'required_ids': []} for c in cases]


def context_for(case, arm, embedder=None):
    docs = case['documents']
    earlier = [d for d in docs if d['position'] < case['target_position']]
    if arm == 'complete':
        selected = earlier
    elif arm == 'none':
        selected = []
    elif arm == 'graph':
        allowed = {d['id']: d for d in earlier}
        queue, seen, selected = list(case['references']), set(), []
        while queue and len(selected) < 4:
            name = queue.pop(0)
            if name in seen:
                continue
            seen.add(name)
            if name not in allowed:
                continue
            doc = allowed[name]
            selected.append(doc)
            queue.extend(doc['references'])
    else:
        pool = docs if arm == 'vector' else earlier
        if arm == 'lexical':
            tokens = lambda s: set(re.findall(r'[A-Za-z0-9_]+', s.lower()))
            query = tokens(case['target'])
            scores = [len(query & tokens(d['content']))/max(1,len(query | tokens(d['content']))) for d in pool]
        else:
            vectors = embedder.embed([case['target']] + [d['content'] for d in pool])
            scores = (vectors[1:] @ vectors[0]).tolist()
        selected = [d for _, d in sorted(zip(scores, pool), key=lambda pair: (-pair[0], pair[1]['id']))[:4]]
    if arm in ('position_filtered', 'lexical', 'graph', 'complete'):
        assert all(d['position'] < case['target_position'] for d in selected)
    # Same hard character ceiling for ranked arms; do not truncate a mathematical statement.
    if arm != 'complete':
        selected = selected[:4]
        while sum(len(d['content']) for d in selected) > 1600:
            selected.pop()
    payload = {'target': case['target'], 'target_position': case['target_position'],
               'background_knowledge': case['background'],
               'background_passages': [{k:d[k] for k in ('id','content')} for d in case['background_passages']],
               'context': [{k:d[k] for k in ('id','content','position')} for d in selected],
               'context_complete': {d['id'] for d in earlier} <= {d['id'] for d in selected}}
    return payload


def summarize(rows):
    result = {}
    for key in sorted({(r['model'], r['prompt'], r['arm']) for r in rows}):
        group = [r for r in rows if (r['model'],r['prompt'],r['arm']) == key]
        families = defaultdict(list)
        for r in group:
            families[r['family']].append(int(r.get('verdict',{}).get('status') == r['expected']))
        means = [sum(v)/len(v) for v in families.values()]
        rng = random.Random(42)
        samples = sorted(sum(rng.choices(means,k=len(means)))/len(means) for _ in range(1000))
        byclass = {}
        for label in ('PASS','FAIL_GAP','FAIL_LOGIC','ABSTAIN'):
            tp = sum(r.get('verdict',{}).get('status') == r['expected'] == label for r in group)
            predicted = sum(r.get('verdict',{}).get('status') == label for r in group)
            support = sum(r['expected'] == label for r in group)
            byclass[label] = {'support':support,'predicted':predicted,'precision':tp/predicted if predicted else None,
                              'recall':tp/support if support else None}
        result[' | '.join(key)] = {'attempts':len(group),'exact_matches':sum(map(sum,families.values())),
            'errors':dict(Counter(r.get('error_type') for r in group if r.get('error_type'))),
            'verdicts':dict(Counter(r.get('verdict',{}).get('status','ERROR') for r in group)),
            'coverage':sum(r.get('verdict',{}).get('status') in ('PASS','FAIL_GAP','FAIL_LOGIC') for r in group)/len(group),
            'future_context_cases':sum(r['future_items']>0 for r in group),
            'mean_seconds':sum(r['seconds'] for r in group)/len(group),
            'exact_match_family_bootstrap_95_interval':[samples[24],samples[974]],
            'family_count':len(means), 'per_class':byclass,
            'per_category':{c:{'attempts':sum(r['category']==c for r in group),
                               'matches':sum(r['category']==c and r.get('verdict',{}).get('status')==r['expected'] for r in group)}
                            for c in sorted({r['category'] for r in group})}}
    return result


def code_hash():
    files = [Path(__file__), ROOT/'scripts/controlled_benchmark.py', ROOT/'src/config/settings.py',
             ROOT/'src/verification/verdicts.py', ROOT/'src/vector_store/embeddings.py', ROOT/'scripts/run_local_pilot.py']
    return digest({str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files})


def authorize_heldout(gate, manifest, protocol, model_metadata):
    record = json.loads((gate/'manifest.json').read_text())
    if record['phase'] != 'gate' or record['code_hash'] != code_hash():
        raise ValueError('Gate must use identical evaluation code')
    if record['benchmark_manifest_hash'] != digest(manifest) or record['model_metadata'] != model_metadata:
        raise ValueError('Benchmark or local model identity changed since gate')
    completed = json.loads((gate/'COMPLETE.json').read_text())
    if completed['predictions_sha256'] != hashlib.sha256((gate/'predictions.jsonl').read_bytes()).hexdigest():
        raise ValueError('Gate results changed after completion')
    rows = [json.loads(line) for line in (gate/'predictions.jsonl').read_text().splitlines()]
    for model in MODELS:
        selected = [r for r in rows if r['model']==model and r['prompt']==protocol and r['arm']=='complete']
        if len(selected)!=7 or {r['case_id'] for r in selected} != {c['id'] for c in gate_cases()}:
            raise ValueError('Missing gate cases')
        expected = {c['id']:c['expected'] for c in gate_cases()}
        if not all(r.get('verdict',{}).get('status')==expected[r['case_id']] for r in selected):
            raise ValueError('Seven-fixture gate failed; heldout evaluation remains closed')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--phase',choices=['gate','development','heldout'],required=True)
    parser.add_argument('--arms',nargs='+',choices=[*ARMS,'complete'],default=['complete'])
    parser.add_argument('--prompts',nargs='+',choices=['original','evidence'],default=['original','evidence'])
    parser.add_argument('--gate-run',type=Path)
    args = parser.parse_args()
    manifest = json.loads((DEST/'manifest.json').read_text())
    for name, expected in manifest['files'].items():
        if hashlib.sha256((DEST/name).read_bytes()).hexdigest()!=expected:
            raise ValueError('Frozen benchmark hash changed: '+name)
    settings = Settings(_env_file=None, openai_api_key='ollama',openai_base_url='http://127.0.0.1:11434/v1',
                        openai_timeout=120,openai_max_retries=0)
    assert urlsplit(settings.openai_base_url).hostname == '127.0.0.1'
    client = settings.create_openai_client()
    metadata = client.models.list().model_dump()
    assert set(MODELS) <= {m['id'] for m in metadata['data']}
    if args.phase == 'heldout':
        if not args.gate_run or len(args.prompts)!=1 or args.arms!=list(ARMS):
            parser.error('Heldout requires --gate-run, one frozen prompt, and all five arms in defined order')
        authorize_heldout(args.gate_run,manifest,args.prompts[0],metadata)
    run = ROOT/'artifacts/controlled_study'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    for directory in ('src', 'scripts'):
        for path in (ROOT/directory).rglob('*.py'):
            target = run/'source_snapshot'/path.relative_to(ROOT)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    shutil.copyfile(ROOT/'requirements-local.lock.txt',run/'requirements-local.lock.txt')
    # Exclusive lock permits exactly one heldout attempt, including partial/failed runs.
    if args.phase == 'heldout':
        with (DEST/'HELDOUT_STARTED.json').open('x') as f:
            json.dump({'run':str(run),'protocol':args.prompts[0],'code_hash':code_hash()},f)
    cases = gate_cases() if args.phase=='gate' else json.loads((DEST/(args.phase+'.json')).read_text())
    embedder = None
    if set(args.arms) & {'vector','position_filtered'}:
        import torch
        from src.vector_store.embeddings import EmbeddingService
        torch.set_num_threads(2)
        embedder = EmbeddingService(device='cpu')
    with (run/'manifest.json').open('x') as f:
        json.dump({'phase':args.phase,'arms':args.arms,'prompts':args.prompts,'models':MODELS,
                   'code_hash':code_hash(),'benchmark_manifest_hash':digest(manifest),'model_metadata':metadata,
                   'temperature':0,'seed':42,'max_tokens':500,'case_count':len(cases),
                   'context_budget':{'passages':4,'characters':1600,'complete_diagnostic':'all earlier passages'},
                   'prompt_texts':{'original':ORIGINAL_PROMPT+CONTRACT,'evidence':EVIDENCE_PROMPT+CONTRACT}},f,indent=2)
    # Compute retrieval once, with labels and oracle metadata excluded from embedding inputs.
    payloads = {(c['id'],a):context_for(c,a,embedder) for c in cases for a in args.arms}
    rows = []
    with (run/'predictions.jsonl').open('x') as output:
        for model in MODELS:
            for case in cases:
                for arm in args.arms:
                    payload = payloads[case['id'],arm]
                    for protocol in args.prompts:
                        started=time.monotonic()
                        messages=[{'role':'system','content':(ORIGINAL_PROMPT if protocol=='original' else EVIDENCE_PROMPT)+CONTRACT},
                                  {'role':'user','content':json.dumps(payload)}]
                        row={'case_id':case['id'],'family':case['family'],'category':case['category'],
                             'expected':case['expected'],'model':model,'prompt':protocol,'arm':arm,
                             'messages':messages,'context_complete':payload['context_complete'],
                             'future_items':sum(d['position']>=case['target_position'] for d in payload['context'])}
                        supplied={d['id'] for d in payload['context'] if d['position']<case['target_position']}
                        supplied.update(d['id'] for d in payload['background_passages'])
                        row['required_evidence_supplied']=set(case['required_ids'])<=supplied if case['required_ids'] else None
                        try:
                            response=client.chat.completions.create(model=model,messages=messages,temperature=0,seed=42,
                                                                    max_tokens=500,response_format={'type':'json_object'})
                            row['response']=response.model_dump()
                            if response.choices[0].finish_reason!='stop':
                                raise ValueError('Truncated response')
                            row['verdict']=decode(response.choices[0].message.content,payload)
                        except Exception as exc:
                            row['error_type']=('json_format' if isinstance(exc,json.JSONDecodeError) else
                                'output_schema' if isinstance(exc,ValidationError) else
                                'evidence_or_scope' if isinstance(exc,EvidenceError) else 'runtime_or_truncation')
                            row['error']=str(exc)
                        row['seconds']=time.monotonic()-started
                        row['correct']=row.get('verdict',{}).get('status')==case['expected']
                        if not row['correct']:
                            row['diagnosis']=('format_or_execution' if row.get('error_type') else
                                'judgment_with_complete_context' if payload['context_complete'] else
                                'judgment_despite_required_evidence' if row['required_evidence_supplied'] else
                                'retrieval_coverage_or_judgment_unresolved')
                        rows.append(row);output.write(json.dumps(row)+'\n');output.flush()
                        print(model,case['id'],arm,protocol,row.get('verdict',{}).get('status',row.get('error_type')),flush=True)
    with (run/'summary.json').open('x') as f:
        json.dump(summarize(rows),f,indent=2)
    with (run/'COMPLETE.json').open('x') as f:
        json.dump({'calls':len(rows),'predictions_sha256':hashlib.sha256((run/'predictions.jsonl').read_bytes()).hexdigest()},f)
    client.close()
    print('Saved:',run,flush=True)


if __name__=='__main__':
    main()
