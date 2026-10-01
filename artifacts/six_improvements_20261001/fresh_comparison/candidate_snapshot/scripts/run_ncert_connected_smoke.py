"""One real connected MathemaTest run in explicit native-PDF/question mode.

Not the legacy OCR/calculus/Mathlib configuration, not an accuracy benchmark.
Original extraction is retained; no curated passage or answer key is model input.
"""
import hashlib
import json
import os
from pathlib import Path
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['HF_HOME'] = str(ROOT / '.cache/huggingface')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'


def main():
    import torch
    torch.set_num_threads(2)
    import httpx
    from openai import OpenAI
    from sentence_transformers import CrossEncoder
    from src.config.settings import Settings
    from src.ingestion.ingestion_engine import IngestionEngine
    from src.graph_store.graph_constructor import GraphConstructorAgent
    from src.graph_store.neo4j_client import Neo4jClient
    from src.vector_store.chroma_client import ChromaVectorStore
    from src.retrieval.hybrid_orchestrator import HybridRetriever, CrossEncoderReranker
    from src.verification.auditor_prover import AuditorProver
    from src.verification.lean_compiler import Lean4Compiler
    from scripts.prepare_ncert_pilot import locate_target

    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = ROOT / 'artifacts/ncert_connected_smoke' / stamp
    run.mkdir(parents=True)
    print('Run:', run, flush=True)
    def save(name, obj):
        (run / name).write_text(json.dumps(obj, indent=2, ensure_ascii=False) + '\n')
    source = ROOT / 'data/ncert10_pilot_v1'
    manifest = json.loads((source / 'manifest.json').read_text())
    candidates = json.loads((source / 'candidates.json').read_text())
    source_ids = {code: f'{stamp}-{code}' for code in ['jemh104', 'jesc111']}
    settings = Settings(_env_file=None, openai_api_key='ollama',
        openai_base_url='http://127.0.0.1:11434/v1', default_model='qwen2.5-coder:7b',
        gpt4o_mini_model='qwen2.5-coder:7b', openai_max_retries=0, openai_timeout=240,
        neo4j_uri='bolt://127.0.0.1:7687', neo4j_user='neo4j', neo4j_password='password',
        chroma_persist_directory=str(run / 'chroma'),
        lean_binary=str(ROOT / '.tools/lean-4.26.0-darwin_aarch64/bin/lean'))
    with urlopen('http://127.0.0.1:11434/api/tags', timeout=10) as r:
        tags = json.load(r)
    reranker_metadata = json.loads((ROOT / 'artifacts/mathematest_setup/reranker.json').read_text())
    save('manifest.json', {'configuration': 'native digital-PDF / scoped hybrid retrieval / numerical-question audit / exact arithmetic + core Lean',
         'models': tags, 'source_manifest': manifest, 'planned_inference_calls': 2,
         'target': 'jesc111:example-11.1', 'source_ids': source_ids,
         'reranker': reranker_metadata, 'background': 'Rational arithmetic; 1 minute = 60 seconds; SI units multiply and divide with quantities.',
         'limitations': ['Engineering smoke on a previously inspected case, not heldout evaluation',
             'Native text does not certify mathematical typography or diagrams',
             'Model graph edges unreviewed; original source spans used as evidence',
             'Arithmetic compilation is not a formal proof of source mapping, units or educational adequacy',
             'Legacy OCR and Mathlib configuration remains separate and incomplete']})
    for path in sorted((ROOT / 'src').rglob('*.py')) + [Path(__file__)]:
        target = run / 'source_snapshot' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    raw_ingestion, docs = {}, []
    for code, chapter in [('jemh104', 4), ('jesc111', 11)]:
        boundaries = [c[k] for c in candidates if c['source_id'] == code
                      for k in ('target_start_offset', 'target_end_offset')]
        result = IngestionEngine.process_digital_pdf(source / 'raw' / f'{code}.pdf',
            source_ids[code], chapter, split_boundaries=boundaries)
        if result['pdf_sha256'] != manifest['sources'][code]['pdf_sha256']:
            raise ValueError('Pinned PDF changed')
        if hashlib.sha256(result['text'].encode()).hexdigest() != manifest['sources'][code]['text_sha256']:
            raise ValueError('Fresh native extraction differs from pinned source text')
        raw_ingestion[code] = result
        docs.extend(result['documents'])
    save('ingestion.json', raw_ingestion)
    print('Ingested real PDF text:', len(docs), 'spans across 35 pages.', flush=True)

    graph = Neo4jClient(settings)
    graph.driver.verify_connectivity()
    graph.initialize_schema()
    # Persist only this run's uniquely identified original spans; no global deletes.
    for doc in docs:
        graph.create_node('Concept', doc['id'], {**doc, 'name': doc['content'].strip().splitlines()[0][:80],
            'evidence_kind': 'original_source_span', 'entity_review': 'NATIVE_TEXT_BLOCK'})
    store = ChromaVectorStore(settings=settings, collection_name='ncert-connected-smoke')
    store.embedder.device = 'cpu'
    store.add_documents(docs)
    print('Original spans persisted in Neo4j and real Chroma index.', flush=True)

    # Log real provider traffic before parser/validation, without authentication headers.
    def capture_request(request):
        if request.method == 'POST':
            with (run / 'model_requests.jsonl').open('a') as f:
                f.write(json.dumps({'path': request.url.path, 'body': json.loads(request.content)}) + '\n')
    def capture_response(response):
        response.read()
        try:
            body = response.json()
        except ValueError:
            body = response.text
        with (run / 'model_responses.jsonl').open('a') as f:
            f.write(json.dumps({'status': response.status_code, 'body': body}) + '\n')
    client = OpenAI(api_key='ollama', base_url=settings.openai_base_url, max_retries=0,
        http_client=httpx.Client(timeout=240, event_hooks={'request': [capture_request], 'response': [capture_response]}))
    target_text = raw_ingestion['jesc111']['text']
    start, end = locate_target(target_text, '11.1')
    target = target_text[start:end]
    prefix = {'source_id': source_ids['jesc111'], 'content': target_text[:start],
              'start_offset': 0, 'end_offset': start, 'chapter': 11}
    constructor = GraphConstructorAgent(settings=settings, neo4j_client=graph)
    constructor.openai.close()
    constructor.openai = client
    extracted = constructor.extract_from_content(prefix, source_id=source_ids['jesc111'], page_number=1)
    if extracted is None:
        save('FAILED.json', {'stage': 'graph_extraction', 'reason': 'Extraction failed; see raw provider logs', 'audit_calls': 0})
        raise RuntimeError('Graph extraction failed; connected run stopped')
    counts = constructor.persist_extraction(extracted, source_id=source_ids['jesc111'])
    save('graph_extraction.json', {'input': prefix, 'extraction': asdict(extracted), 'persisted': counts})
    with graph.session() as session:
        entities = [dict(r['n']) for r in session.run(
            "MATCH (n) WHERE n.source_id=$source AND n.entity_review='MODEL_UNREVIEWED' RETURN n",
            source=source_ids['jesc111'])]
    store.add_documents(entities)
    print('Extracted graph:', counts, flush=True)
    reranker = CrossEncoderReranker()
    reranker._model = CrossEncoder(reranker_metadata['snapshot_path'], device='cpu', local_files_only=True)
    retriever = HybridRetriever(settings=settings, vector_store=store, graph_client=graph, reranker=reranker)
    checks = []
    for c in candidates:
        results = retriever.retrieve_for_audit(c['target_raw'], source_id=source_ids[c['source_id']],
            before_position=c['target_start_offset'], n_results=4, rerank=True)
        valid = all(r.metadata['source_id'] == source_ids[c['source_id']] and
                    0 <= r.metadata['start_offset'] < r.metadata['end_offset'] <= c['target_start_offset'] for r in results)
        if not valid:
            raise ValueError('Source-order violation in connected retrieval')
        checks.append({'case_id': c['id'], 'scope_valid': valid, 'retrieved': [asdict(r) for r in results]})
    save('retrieval_checks.json', checks)
    compiler = Lean4Compiler(settings=settings, lean_project_path=run / 'lean', use_mathlib=False)
    auditor = AuditorProver(settings=settings, retriever=retriever, lean_compiler=compiler)
    auditor.openai.close()
    auditor.openai = client
    result = auditor.audit_question(target, source_id=source_ids['jesc111'], before_position=start,
        background='Rational arithmetic; 1 minute = 60 seconds; SI units multiply and divide with quantities.', n_context=4)
    save('audit.json', result)
    requests = [json.loads(l) for l in (run / 'model_requests.jsonl').read_text().splitlines()]
    expansions = result['retrieval'][0]['metadata']['graph_trace']['expansions']
    save('COMPLETE.json', {'inference_calls': len(requests), 'retrieval_cases_checked': len(checks),
        'source_order_violations': 0, 'graph_entity_nodes': counts['nodes'],
        'graph_relationships': counts['relationships'], 'audit_prerequisite_expansions': len(expansions),
        'audit_status': result['status'], 'verification_scope': result.get('verification_scope'),
        'pipeline_executed': True, 'benchmark_accuracy_claim': False})
    print('Audit:', result['status'], result.get('answer'), flush=True)
    print('Saved:', run, flush=True)
    client.close()
    graph.close()


if __name__ == '__main__':
    main()
