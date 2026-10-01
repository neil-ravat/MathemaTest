"""Exercise real MathemaTest integration gates on NCERT without substituting mocks.

An unsuccessful ingestion/graph/retrieval gate blocks downstream audit calls.
An independently seeded retrieval probe diagnoses the existing implementation;
it is explicitly NOT a successful PDF-to-verdict run or a performance benchmark.
"""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from dataclasses import asdict
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ['HF_HOME'] = str(ROOT / '.cache/huggingface')
os.environ['HF_HUB_OFFLINE'] = '1'
os.environ['TRANSFORMERS_OFFLINE'] = '1'
os.environ['ANONYMIZED_TELEMETRY'] = 'False'


def source_violation(metadata, case):
    if metadata.get('source_id') != case['source_id']:
        return 'different_source'
    if metadata.get('end_offset', float('inf')) > case['target_start_offset']:
        return 'target_or_later_material'
    return None


def main():
    import torch
    torch.set_num_threads(2)
    from src.config.settings import Settings
    from src.ingestion.ingestion_engine import IngestionEngine
    from src.graph_store.neo4j_client import Neo4jClient
    from src.graph_store.graph_constructor import GraphConstructorAgent
    from src.vector_store.chroma_client import ChromaVectorStore
    from src.retrieval.hybrid_orchestrator import HybridRetriever
    from src.verification.lean_compiler import Lean4Compiler

    run = ROOT / 'artifacts/ncert_pipeline_check' / datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run.mkdir(parents=True)
    print('Run:', run, flush=True)
    def save(name, data):
        (run / name).write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')

    source = ROOT / 'data/ncert10_pilot_v1'
    source_hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                     for p in sorted(source.rglob('*')) if p.is_file()}
    cases = json.loads((source / 'candidates.json').read_text())
    lean = ROOT / '.tools/lean-4.26.0-darwin_aarch64/bin/lean'
    settings = Settings(_env_file=None, openai_api_key='ollama',
        openai_base_url='http://127.0.0.1:11434/v1', default_model='qwen2.5-coder:7b',
        gpt4o_mini_model='qwen2.5-coder:7b', openai_max_retries=0,
        neo4j_uri='bolt://127.0.0.1:7687', neo4j_user='neo4j', neo4j_password='password',
        chroma_persist_directory=str(run / 'isolated_chroma'), lean_binary=str(lean))
    report = {'purpose': __doc__, 'new_llm_calls': 0, 'mock_components_used': False,
              'source_hashes': source_hashes, 'stages': {}, 'blockers': []}
    stages, blockers = report['stages'], report['blockers']

    # Actual PDF -> ingestion calls. No supplied layout blocks or OCR substitutes.
    stages['ingestion'] = []
    for code, page in [('jemh104', 3), ('jesc111', 2)]:
        result = IngestionEngine(use_gpu=False, dpi=96).process_pdf(
            source / 'raw' / (code + '.pdf'), page_range=(page, page))
        stages['ingestion'].append({'source_id': code, 'pdf_page': page,
                                    'result': result.model_dump(mode='json')})
    if any(r['result']['errors'] or not r['result']['blocks'] for r in stages['ingestion']):
        blockers.append('Real PDF ingestion failed or produced no blocks; no ingested corpus can flow downstream.')
    save('ingestion.json', stages['ingestion'])
    print('Ingestion attempted on two real NCERT pages.', flush=True)

    graph = Neo4jClient(settings)
    try:
        graph.driver.verify_connectivity()
        stages['graph_connection'] = {'connected': True, 'writes_performed': False}
    except Exception as exc:
        stages['graph_connection'] = {'connected': False, 'error': f'{type(exc).__name__}: {exc}'}
        blockers.append('Local Neo4j connection unavailable; graph persistence/traversal cannot run.')
    constructor = GraphConstructorAgent(settings=settings, neo4j_client=graph)
    stages['graph_extractor_initialization'] = {'client_enabled': constructor.openai is not None,
        'configured_endpoint': settings.openai_base_url, 'key_is_dummy_local_token': True,
        'extraction_calls': 0}
    if constructor.openai is None:
        blockers.append('GraphConstructorAgent disables the configured local endpoint because its key validator requires an sk- prefix.')

    stages['optional_dependencies'] = {name: importlib.util.find_spec(name) is not None
                                      for name in ['doclayout_yolo', 'unimernet']}
    # Independent downstream engineering probe, not ingestion output or model input.
    spans = json.loads((ROOT / 'data/ncert10_diagnostic_v1/source_spans.json').read_text())
    documents = [{'id': p['id'], 'content': p['text'], 'source_id': p['source_id'],
                  'chapter': 4 if p['source_id'] == 'jemh104' else 11,
                  'start_offset': p['start_offset'], 'end_offset': p['end_offset']}
                 for p in spans]
    store = ChromaVectorStore(settings=settings, collection_name='ncert-integration-probe')
    store.embedder.device = 'cpu'
    retriever = HybridRetriever(settings=settings, vector_store=store, graph_client=graph)
    stages['retrieval_probe'] = {'input_origin': '15 previously AI-curated spans, independently seeded; NOT IngestionEngine output',
        'condition': 'actual HybridRetriever.retrieve_for_audit; reranking disabled only in leakage probe',
        'cases': []}
    try:
        store.add_documents(documents)
        stages['retrieval_probe']['indexed'] = store.collection.count()
        stages['retrieval_probe']['embedding_model'] = settings.embedding_model
        for case in cases:
            results = retriever.retrieve_for_audit(case['target_reviewed'],
                current_chapter=4 if case['source_id'] == 'jemh104' else 11,
                n_results=3, rerank=False)
            stages['retrieval_probe']['cases'].append({'case_id': case['id'],
                'results': [{**asdict(r), 'source_order_violation': source_violation(r.metadata, case)} for r in results]})
        leaking = sum(any(r['source_order_violation'] for r in c['results'])
                      for c in stages['retrieval_probe']['cases'])
        stages['retrieval_probe']['contexts_with_source_order_violations'] = leaking
        if leaking:
            blockers.append(f'Actual chapter-filter retrieval returned target/later or cross-source spans for {leaking}/12 diagnostic contexts.')
        try:
            result = retriever.retrieve_for_audit(cases[0]['target_reviewed'], current_chapter=4,
                                                  n_results=3, rerank=True)
            stages['reranking_probe'] = {'completed': True, 'results': [asdict(r) for r in result]}
        except Exception as exc:
            stages['reranking_probe'] = {'completed': False, 'error': f'{type(exc).__name__}: {exc}'}
            blockers.append('Default reranker could not execute with locally available model files.')
    except Exception as exc:
        stages['retrieval_probe']['error'] = f'{type(exc).__name__}: {exc}'
        blockers.append('Real vector retrieval probe failed; see recorded exception.')
    save('retrieval.json', stages['retrieval_probe'])
    print('Real retrieval probe completed.', flush=True)

    compiler = Lean4Compiler(lean_project_path=run / 'lean_workspace', settings=settings)
    stages['verification_probe'] = {'lean_available': compiler.lean_available,
        'isolated_probe_mathlib_available': compiler.mathlib_available,
        'repository_mathlib_packages_present': (ROOT / 'mathematest/.lake/packages/mathlib').exists(),
        'scope': 'toolchain smoke checks, not textbook proofs',
        'core': asdict(compiler.compile('theorem probe : (1 : Nat) + 1 = 2 := by rfl', use_prelude=False, use_mathlib=False)),
        'mathlib_import': asdict(compiler.compile('import Mathlib.Tactic\ntheorem probe : (1 : Nat) + 1 = 2 := by norm_num', use_prelude=False))}
    if not stages['verification_probe']['mathlib_import']['success']:
        blockers.append('Configured Mathlib-import proof compilation failed; core Lean availability is not sufficient.')
    report['audit_execution'] = {'status': 'BLOCKED_BEFORE_LLM',
        'reason': 'No valid connected PDF-ingestion/graph/retrieval chain; never substitute curated excerpts or empty context and report it as an end-to-end success.',
        'completed_end_to_end_cases': 0, 'textbook_proofs': 0}
    report['source_files_unchanged'] = all(hashlib.sha256((ROOT / p).read_bytes()).hexdigest() == h
                                          for p, h in source_hashes.items())
    report['source_code_hashes'] = {}
    for p in sorted((ROOT / 'src').rglob('*.py')) + [Path(__file__)]:
        relative = p.relative_to(ROOT)
        snapshot = run / 'source_snapshot' / relative
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(p, snapshot)
        report['source_code_hashes'][str(relative)] = hashlib.sha256(p.read_bytes()).hexdigest()
    save('report.json', report)
    graph.close()
    print(json.dumps({'blockers': blockers, 'completed_end_to_end_cases': 0,
                      'new_llm_calls': 0, 'report': str(run / 'report.json')}, indent=2), flush=True)
    return 2 if blockers else 1  # Gate diagnostics never certify a complete audit.


if __name__ == '__main__':
    raise SystemExit(main())
