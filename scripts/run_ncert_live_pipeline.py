"""Live development smoke through the production scoped auditor; no accuracy claims."""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-run', required=True, type=Path)
    args = parser.parse_args()
    corpus = args.input_run.resolve()
    manifest = json.loads((corpus/'manifest.json').read_text())
    if not (corpus/'COMPLETE.json').exists():
        raise ValueError('Corpus construction must finish first')
    cases = json.loads((corpus/'cases_snapshot.json').read_text())
    run = ROOT/'artifacts/ncert_live_pipeline'/datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    print(run, flush=True)
    def save(name, value):
        (run/name).write_text(json.dumps(value, indent=2, ensure_ascii=False)+'\n')
    for path in list((ROOT/'src').rglob('*.py'))+[Path(__file__)]:
        dest = run/'source_snapshot'/path.relative_to(ROOT)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, dest)
    save('manifest.json', dict(input_run=str(corpus), cases=[c['id'] for c in cases],
        model='qwen2.5-coder:7b', development_only=True, planned_answer_calls=len(cases),
        source_manifest=manifest, graph_traversal='Production scoped path: prerequisite edges only; factual nodes can be vector seeds',
        limitations=['Previously exposed cases, AI-only review', 'Native formulas not rewritten',
                     'No accepted prerequisite edges; no graph-benefit comparison']))
    os.environ.update(HF_HOME=str(ROOT/'.cache/huggingface'), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', ANONYMIZED_TELEMETRY='False')
    import torch
    import httpx
    from openai import OpenAI
    from sentence_transformers import CrossEncoder
    from src.config.settings import Settings
    from src.graph_store.neo4j_client import Neo4jClient
    from src.vector_store.chroma_client import ChromaVectorStore
    from src.retrieval.hybrid_orchestrator import HybridRetriever, CrossEncoderReranker
    from src.verification.auditor_prover import AuditorProver
    from src.verification.lean_compiler import Lean4Compiler
    torch.set_num_threads(2)
    settings = Settings(_env_file=None, openai_api_key='ollama', openai_base_url='http://127.0.0.1:11434/v1',
        default_model='qwen2.5-coder:7b', gpt4o_mini_model='qwen2.5-coder:7b', openai_max_retries=0,
        openai_timeout=240, neo4j_uri='bolt://127.0.0.1:7687', neo4j_user='neo4j', neo4j_password='password',
        chroma_persist_directory=str(corpus/'chroma'),
        lean_binary=str(ROOT/'.tools/lean-4.26.0-darwin_aarch64/bin/lean'))
    graph = Neo4jClient(settings)
    graph.driver.verify_connectivity()
    with graph.session() as session:
        save('graph_snapshot.json', dict(nodes=[dict(r['n']) for r in session.run(
            'MATCH (n) WHERE n.source_id IN $ids RETURN n', ids=list(manifest['source_ids'].values()))],
            edges=[dict(r) for r in session.run('MATCH (a)-[r]->(b) WHERE a.source_id IN $ids '
                'RETURN a.name AS subject, type(r) AS relation, b.name AS object, properties(r) AS properties',
                ids=list(manifest['source_ids'].values()))]))
    store = ChromaVectorStore(settings=settings, collection_name='ncert-connected-smoke')
    store._collection = store.client.get_collection(name=store.collection_name)
    store.embedder.device = 'cpu'
    reranker = CrossEncoderReranker()
    info = json.loads((ROOT/'artifacts/mathematest_setup/reranker.json').read_text())
    reranker._model = CrossEncoder(info['snapshot_path'],device='cpu',local_files_only=True)
    retriever = HybridRetriever(settings=settings,vector_store=store,graph_client=graph,reranker=reranker)
    auditor = AuditorProver(settings=settings,retriever=retriever,
        lean_compiler=Lean4Compiler(settings=settings,lean_project_path=run/'lean',use_mathlib=False))
    active = {}
    def request_log(request):
        with (run/'requests.jsonl').open('a') as f:
            f.write(json.dumps(dict(active,body=json.loads(request.content)))+'\n')
    def response_log(response):
        response.read()
        with (run/'responses.jsonl').open('a') as f:
            f.write(json.dumps(dict(active,status=response.status_code,body=response.text))+'\n')
    auditor.openai.close()
    auditor.openai = OpenAI(api_key='ollama',base_url='http://127.0.0.1:11434/v1',max_retries=0,
        http_client=httpx.Client(timeout=240,trust_env=False,event_hooks={'request':[request_log],'response':[response_log]}))
    results = []
    try:
        for case in cases:
            active['case_id'] = case['id']
            start = time.perf_counter()
            try:
                result = auditor.audit_question(case['target_raw'],source_id=manifest['source_ids'][case['source_id']],
                    before_position=case['target_start_offset'],n_context=4,rerank=True,
                    background='Rational arithmetic; 1 minute = 60 seconds; SI units multiply and divide with quantities.')
            except Exception as exc:
                result = dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
            result.update(case_id=case['id'],wall_seconds=time.perf_counter()-start)
            results.append(result)
            save('results.json',results)
            print(case['id'],result['status'],result.get('answer',''),flush=True)
        save('COMPLETE.json',dict(attempts=len(results),statuses=[r['status'] for r in results],
             benchmark_accuracy_claim=False))
    finally:
        auditor.openai.close()
        graph.close()


if __name__ == '__main__':
    main()
