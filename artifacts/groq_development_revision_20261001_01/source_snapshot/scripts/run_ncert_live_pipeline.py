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
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def validate_direct(judgment):
    """Direct evidence is absent; enforce dependent answer fields as in the app."""
    if judgment['cited_passage_ids']:
        raise ValueError('Direct response invented a source citation')
    fields = [judgment[k] for k in ('calculation_expression', 'claimed_value', 'answer_unit')]
    if judgment['status'] == 'PASS':
        if judgment['missing_prerequisites'] or not all(isinstance(v, str) and v.strip() for v in fields):
            raise ValueError('Direct PASS has incomplete answer fields or missing prerequisites')
        from src.verification.rational_calculator import check_calculation
        if not check_calculation(fields[0], fields[1])['consistent']:
            raise ValueError('Direct calculation is inconsistent')
    elif any(v is not None for v in fields):
        raise ValueError('Direct non-PASS has answer fields')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input-run', required=True, type=Path)
    parser.add_argument('--compare', action='store_true', help='Direct model plus production vector-only and graph-enabled modes')
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
        model='qwen2.5-coder:7b', development_only=True, planned_answer_calls=len(cases)*(3 if args.compare else 1), comparison=args.compare,
        source_manifest=manifest, graph_traversal='Production scoped path: prerequisite edges only; factual nodes can be vector seeds',
        limitations=['Previously exposed cases, AI-only review', 'Native formulas not rewritten',
                     'No accepted prerequisite edges; vector corpus includes entity excerpts; not a raw-text baseline',
                     'Direct is an unverified learned-knowledge comparator; vector and graph use source-only policy']))
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
    modes = ('direct', 'vector', 'graph') if args.compare else ('graph',)
    schedule = [(case, mode) for case in cases for mode in modes]
    save('schedule.json', dict(calls=[{'case_id': c['id'], 'mode': m} for c,m in schedule],
        source_cases=cases, max_tokens=1000, seed=42, temperature=0, retries=0))
    try:
        for case, mode in schedule:
            active['case_id'] = case['id']
            active['mode'] = mode
            retriever.graph_client = graph if mode == 'graph' else SimpleNamespace(search_concepts=lambda **k: [])
            start = time.perf_counter()
            try:
                background='Rational arithmetic; 1 minute = 60 seconds; SI units multiply and divide with quantities.'
                if mode == 'direct':
                    from src.verification.auditor_prover import QuestionJudgment
                    messages = [dict(role='system', content='Answer using learned subject knowledge and declared background. State assumptions. Use PASS to attempt an answer, ABSTAIN if uncertain, FAIL_LOGIC for a demonstrated contradiction. Return the JSON schema. No passages are supplied: cited_passage_ids must be []. For PASS provide a numeric calculation_expression, claimed_value and answer_unit. For non-PASS these fields must be null. Never claim a curriculum gap.'),
                        dict(role='user',content=json.dumps(dict(question=case['target_raw'],background=background)))]
                    response=auditor.openai.chat.completions.create(model=auditor.model,messages=messages,
                        temperature=0,seed=42,max_tokens=1000,response_format={'type':'json_schema',
                        'json_schema':{'name':'question_judgment','strict':True,'schema':QuestionJudgment.model_json_schema()}})
                    result=dict(status='ERROR',response=response.model_dump(),messages=messages)
                    if response.choices[0].finish_reason != 'stop':
                        result['error']='Incomplete direct response'
                    else:
                        judgment=QuestionJudgment.model_validate_json(response.choices[0].message.content).model_dump()
                        validate_direct(judgment)
                        result.update(status='MODEL_ONLY_'+judgment['status'],judgment=judgment)
                else:
                    result = auditor.audit_question(case['target_raw'],source_id=manifest['source_ids'][case['source_id']],
                        before_position=case['target_start_offset'],n_context=4,rerank=True,background=background)
            except Exception as exc:
                result = dict(status='ERROR',error=f'{type(exc).__name__}: {exc}')
            result.update(case_id=case['id'],comparison_mode=mode,wall_seconds=time.perf_counter()-start)
            results.append(result)
            save('results.json',results)
            print(case['id'],mode,result['status'],result.get('answer',''),flush=True)
        save('COMPLETE.json',dict(attempts=len(results),statuses=[r['status'] for r in results],
             benchmark_accuracy_claim=False))
    finally:
        auditor.openai.close()
        graph.close()


if __name__ == '__main__':
    main()
