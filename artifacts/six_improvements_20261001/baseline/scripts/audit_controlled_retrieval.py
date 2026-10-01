"""Audit all five retrieval arms on development data, without LLM calls."""
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
import numpy as np
import torch
from src.vector_store.embeddings import EmbeddingService
from scripts.controlled_benchmark import DEST, digest
from scripts.run_controlled_study import ARMS, context_for, code_hash


def main():
    manifest=json.loads((DEST/'manifest.json').read_text())
    raw=(DEST/'development.json').read_bytes()
    assert hashlib.sha256(raw).hexdigest()==manifest['files']['development.json']
    cases=json.loads(raw)
    torch.set_num_threads(2)
    service=EmbeddingService(device='cpu')
    texts=sorted({s for c in cases for s in [c['target']]+[d['content'] for d in c['documents']]})
    started=time.monotonic()
    vectors=service.embed(texts)
    elapsed=time.monotonic()-started
    cache=dict(zip(texts,vectors))
    class CachedEmbeddings:
        def embed(self, strings):
            return np.array([cache[s] for s in strings])
    rows=[]
    for c in cases:
        earlier={d['id'] for d in c['documents'] if d['position']<c['target_position']}
        required=set(c['required_ids']) & earlier
        for arm in ARMS:
            started=time.monotonic()
            p=context_for(c,arm,CachedEmbeddings())
            selected={d['id'] for d in p['context']}
            rows.append({'case_id':c['id'],'family':c['family'],'category':c['category'],'arm':arm,
                         'selected_ids':sorted(selected),'context_complete':p['context_complete'],
                         'future_items':sum(d['position']>=c['target_position'] for d in p['context']),
                         'available_required':len(required),'recovered_required':len(required & selected),
                         'ranking_seconds':time.monotonic()-started})
    summary={arm:{'cases':sum(r['arm']==arm for r in rows),
                  'future_context_cases':sum(r['arm']==arm and r['future_items']>0 for r in rows),
                  'available_required':sum(r['available_required'] for r in rows if r['arm']==arm),
                  'recovered_required':sum(r['recovered_required'] for r in rows if r['arm']==arm)} for arm in ARMS}
    assert all(summary[a]['future_context_cases']==0 for a in ('position_filtered','lexical','graph'))
    out=ROOT/'artifacts/controlled_study'/('retrieval-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ'))
    out.mkdir(parents=True)
    report={'purpose':'Development retrieval mechanics only; no model accuracy or educational claims',
            'benchmark_manifest_hash':digest(manifest),'code_hash':code_hash(),
            'audit_script_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            'embedding_model':service.model_name,
            'embedding_revision':getattr(service.model[0].auto_model.config,'_commit_hash',None),
            'embedding_seconds':elapsed,'unique_embedded_texts':len(texts),
            'latency_note':'Embedding cost is shared across cases and arms; ranking_seconds excludes embedding.',
            'summary':summary,'rows':rows}
    with (out/'retrieval_audit.json').open('x') as f:json.dump(report,f,indent=2)
    print(json.dumps(summary,indent=2));print('Saved:',out)


if __name__=='__main__':
    main()
