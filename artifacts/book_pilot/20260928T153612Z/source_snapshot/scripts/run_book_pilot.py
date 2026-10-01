"""Frozen, resumable chapter-stratified OpenStax feasibility pilot."""
import argparse
from collections import Counter, defaultdict
from datetime import datetime, timezone
import fcntl
import hashlib
import json
from pathlib import Path
import random
import shutil
import sys
import time
from types import SimpleNamespace
from urllib.request import urlopen
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.run_curriculum_audit import local_completion
from src.verification.curriculum_audit import audit_curriculum

BACKGROUND = ('Rational arithmetic, elementary algebra including rearrangement, and ordinary reading comprehension. '
              'Geometry formulas, function concepts and exponential rules require source or target evidence.')
CORPUS = ROOT/'data/openstax_calculus_context_v2/corpus.jsonl'
SOURCE = ROOT/'data/openstax_calculus_v1'


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def save(path, value):
    tmp = path.with_suffix('.tmp')
    tmp.write_text(json.dumps(value, indent=2))
    tmp.replace(path)


def target_context(records, source):
    """Retain the nearest preceding sibling paragraph as shared task context.

    Structural candidate only: no assertion that extracted tasks are semantically complete.
    """
    modules = {}
    by_id = {r['id']: r for r in records}
    targets = []
    for row in records:
        if row['kind'] != 'exercise':
            continue
        module = row['module_id']
        if module not in modules:
            root = ET.parse(source/'source/modules'/module/'index.cnxml').getroot()
            modules[module] = ({n.get('id'): n for n in root.iter() if n.get('id')},
                               {c: n for n in root.iter() for c in n})
        nodes, parents = modules[module]
        node = nodes[row['anchor']]
        siblings = list(parents[node])
        context = next((n for n in reversed(siblings[:siblings.index(node)])
                        if n.tag.rsplit('}', 1)[-1] in {'para', 'section'}), None)
        original = dict(row)
        reasons = []
        context_row = None
        if context is not None and context.tag.endswith('}para'):
            context_row = by_id.get(module+':'+str(context.get('id')))
            if context_row is None:
                reasons.append('Shared paragraph not represented in extracted corpus')
            else:
                original['content'] = context_row['content']+'\n\n'+row['content']
                original['shared_context_id'] = context_row['id']
        for item in [row] + ([context_row] if context_row else []):
            if item.get('has_media'): reasons.append('Media-dependent input')
            if item.get('unsupported_mathml'): reasons.append('Unsupported mathematical transcription')
        if any(n.tag.rsplit('}', 1)[-1] == 'table' for n in node.iter()):
            reasons.append('Table layout needs review')
        if context is not None and any(n.tag.rsplit('}', 1)[-1] == 'table' for n in context.iter()):
            reasons.append('Shared-context table layout needs review')
        if not row['content'].strip(): reasons.append('Empty extracted target')
        targets.append(dict(target=original, input_issues=sorted(set(reasons)), original_content=row['content']))
    return targets


def stratify(targets, count, seed=42):
    groups = defaultdict(list)
    for item in targets: groups[item['target']['chapter']].append(item)
    rng = random.Random(seed)
    for group in groups.values(): rng.shuffle(group)
    selected = []
    while len(selected) < min(count, len(targets)):
        for chapter in sorted(groups):
            if groups[chapter] and len(selected) < count: selected.append(groups[chapter].pop())
    return selected


def prepare(run, count):
    manifest = json.loads((SOURCE/'manifest.json').read_text())
    for item in manifest['source_files']:
        if digest(SOURCE/'source'/item['path']) != item['sha256']: raise ValueError('Source hash mismatch')
    derived = json.loads((CORPUS.parent/'manifest.json').read_text())
    if digest(CORPUS) != derived['corpus_sha256']: raise ValueError('Corpus hash mismatch')
    records = [json.loads(line) for line in CORPUS.read_text().splitlines()]
    targets = target_context(records, SOURCE)
    run.mkdir(parents=True, exist_ok=False)
    save(run/'preflight.json', dict(total_exercises=len(targets),
        chapters=dict(Counter(t['target']['chapter'] for t in targets)),
        structurally_flagged=sum(bool(t['input_issues']) for t in targets),
        shared_context_added=sum('shared_context_id' in t['target'] for t in targets),
        caveat='Structural checks only; unflagged does not establish task completeness.', targets=targets))
    hashes = {}
    for path in [*sorted((ROOT/'src').rglob('*.py')), ROOT/'scripts/run_curriculum_audit.py', Path(__file__).resolve()]:
        relative = path.relative_to(ROOT); dest = run/'source_snapshot'/relative
        dest.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, dest)
        hashes[str(relative)] = digest(path)
    selected = stratify(targets, count)
    save(run/'manifest.json', dict(scope='Exploratory chapter-stratified pilot, not independent accuracy or confirmed pedagogical gaps',
        corpus_sha256=digest(CORPUS), source_hashes=hashes, background=BACKGROUND, seed=42,
        model='qwen2.5-coder:7b', reviewer='mistral:latest', selection=selected,
        selection_policy='Round-robin chapters after seeded shuffle; flagged cases retained, never replaced',
        planned=len(selected), model_policy='Existing three-stage pipeline; no reviewer bypass; no prompt tuning during run'))
    return run


def execute(run):
    with (run/'run.lock').open('w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        manifest = json.loads((run/'manifest.json').read_text())
        def verify():
            if digest(CORPUS) != manifest['corpus_sha256'] or any(digest(ROOT/p) != h for p,h in manifest['source_hashes'].items()):
                raise ValueError('Frozen corpus/code changed; refusing to mix versions')
        verify()
        records = [json.loads(line) for line in CORPUS.read_text().splitlines()]
        with urlopen('http://127.0.0.1:11434/api/tags', timeout=20) as response:
            metadata = json.load(response)
        if (run/'model_metadata.json').exists():
            old = json.loads((run/'model_metadata.json').read_text())
            def versions(data): return {m['name']:m['digest'] for m in data['models'] if m['name'] in {manifest['model'],manifest['reviewer']}}
            if versions(old) != versions(metadata): raise ValueError('Model versions changed')
        else: save(run/'model_metadata.json', metadata)
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=local_completion)))
        def progress(state, active=None):
            completed = [json.loads(p.read_text()) for p in sorted(run.glob('case-*.json'))]
            done = [r for r in completed if r.get('_finished')]
            save(run/'progress.json', dict(state=state, updated_at=datetime.now(timezone.utc).isoformat(),
                planned=manifest['planned'], completed=len(done), remaining=manifest['planned']-len(done),
                active_target=active, statuses=dict(Counter(r['status'] for r in done)),
                elapsed_case_seconds=sum(r.get('elapsed_seconds',0) for r in done),
                accuracy=None, independent_labels=False))
        failures = 0
        progress('RUNNING')
        try:
            for i,item in enumerate(manifest['selection'],1):
                verify(); path = run/f'case-{i:03}.json'
                if path.exists():
                    previous = json.loads(path.read_text())
                    if previous.get('_finished'): continue
                    shutil.copyfile(path,run/f'interrupted-{i:03}-{time.time_ns()}.json')
                target = item['target']; progress('RUNNING',target['id']); start=time.monotonic()
                if item['input_issues']:
                    result=dict(status='INPUT_REVIEW_REQUIRED', target=target, reasons=item['input_issues'], calls=[])
                else:
                    result=audit_curriculum(client,manifest['model'],manifest['reviewer'],records,target,manifest['background'],
                        checkpoint=lambda value:save(path,dict(value,_finished=False)))
                result.update(_finished=result['status']!='INTERRUPTED',elapsed_seconds=time.monotonic()-start)
                save(path,result); progress('RUNNING')
                print(i,target['id'],result['status'],flush=True)
                if not result['_finished']: progress('INTERRUPTED'); return
                failures = failures+1 if result['status']=='ERROR' else 0
                if failures >= 3: progress('STOPPED_AFTER_THREE_ERRORS'); return
            progress('COMPLETE')
        except BaseException:
            progress('INTERRUPTED_OR_FAILED'); raise


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--run-dir',type=Path)
    parser.add_argument('--prepare-only',action='store_true')
    parser.add_argument('--count',type=int,default=100)
    args=parser.parse_args()
    if args.count < 1: parser.error('Positive count required')
    run=args.run_dir or prepare(ROOT/'artifacts/book_pilot'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),args.count)
    print(run,flush=True)
    if not args.prepare_only: execute(run)
