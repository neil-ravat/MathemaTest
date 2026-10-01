"""Logged staged graph development run; no heldout cases or expert-gold claim."""
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time
from datetime import datetime, timezone
from dataclasses import asdict

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import validate
from scripts.run_ncert_diagnostic import api
from scripts.prepare_ncert_pilot import locate_target
from src.ingestion.ingestion_engine import IngestionEngine
from src.config.settings import Settings
from src.graph_store.graph_constructor import GraphConstructorAgent
from src.graph_store.grounded_extractor import extract_grounded_source
from src.graph_store.neo4j_client import Neo4jClient


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = ROOT / 'artifacts/grounded_graph_pilot' / stamp
    run.mkdir(parents=True)
    print('Run:', run, flush=True)
    def save(name, value):
        (run / name).write_text(json.dumps(value, indent=2, ensure_ascii=False) + '\n')
    options = {'temperature': 0, 'seed': 42, 'num_ctx': 16384, 'num_predict': 5000}
    tags = api('tags')
    model, reviewer = 'qwen2.5-coder:7b', 'mistral:latest'
    if not {model, reviewer} <= {m['name'] for m in tags['models']}:
        raise ValueError('Required local models unavailable')
    for file in [str(p.relative_to(ROOT)) for p in sorted((ROOT / 'src').rglob('*.py'))] + [
                 'scripts/run_grounded_graph_pilot.py', 'scripts/run_ncert_diagnostic.py']:
        dest = run / 'source_snapshot' / file
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / file, dest)
    source_id = f'{stamp}-grounded-jesc111'
    source = ROOT / 'data/ncert10_pilot_v1'
    ingest = IngestionEngine.process_digital_pdf(source / 'raw/jesc111.pdf', source_id, 11)
    pinned = json.loads((source / 'manifest.json').read_text())['sources']['jesc111']
    assert ingest['pdf_sha256'] == pinned['pdf_sha256']
    assert hashlib.sha256(ingest['text'].encode()).hexdigest() == pinned['text_sha256']
    start, _ = locate_target(ingest['text'], '11.1')
    content = {'source_id': source_id, 'chapter': 11, 'content': ingest['text'][:start],
               'start_offset': 0, 'end_offset': start,
               'formula_layout_verified': ingest['formula_layout_verified']}
    save('manifest.json', {'source_id': source_id, 'mode': 'development only; provisional AI-reviewed graph',
        'models': tags, 'options': options, 'source': pinned, 'target_start': start,
        'extractor_model': model, 'reviewer_model': reviewer, 'planned_calls': 3,
        'retries': 0, 'expert_gold': False, 'prior_case_exposure': True})
    save('source.json', content)
    calls = []
    def call(stage, system, payload, schema, selected_model):
        request = {'model': selected_model, 'messages': [{'role': 'system', 'content': system},
            {'role': 'user', 'content': json.dumps(payload, ensure_ascii=False)}],
            'stream': False, 'format': schema, 'options': options, 'keep_alive': '5m'}
        save(f'{stage}_request.json', request)
        row = {'stage': stage, 'model': selected_model}
        started = time.monotonic()
        try:
            response = api('chat', request)
            save(f'{stage}_response.json', response)
            row.update(prompt_tokens=response.get('prompt_eval_count'), output_tokens=response.get('eval_count'))
            if not response.get('done') or response.get('done_reason') != 'stop':
                raise ValueError('Incomplete model response')
            result = json.loads(response['message']['content'])
            validate(result, schema)
            return result
        except Exception as exc:
            row['error'] = f'{type(exc).__name__}: {exc}'
            raise
        finally:
            row['seconds'] = time.monotonic() - started
            calls.append(row)
            save('calls.json', calls)
            print(stage, 'complete' if 'error' not in row else row['error'], flush=True)
    try:
        result, report = extract_grounded_source(content, call, model=model, reviewer_model=reviewer)
        save('review.json', report)
        save('extraction.json', asdict(result))
        settings = Settings(_env_file=None, openai_api_key='ollama',
            openai_base_url='http://127.0.0.1:11434/v1', neo4j_uri='bolt://127.0.0.1:7687',
            neo4j_user='neo4j', neo4j_password='password')
        graph = Neo4jClient(settings)
        constructor = GraphConstructorAgent(settings=settings, neo4j_client=graph)
        counts = constructor.persist_extraction(result, source_id=source_id)
        with graph.session() as session:
            stored_nodes = [dict(r['n']) for r in session.run('MATCH (n {source_id:$s}) RETURN n', s=source_id)]
            stored_edges = [dict(r['r']) for r in session.run('MATCH (a {source_id:$s})-[r]->() RETURN r', s=source_id)]
        assert len(stored_nodes) == counts['nodes'] and len(stored_edges) == counts['relationships']
        for record in stored_nodes + stored_edges:
            assert record['content'] == ingest['text'][record['start_offset']:record['end_offset']]
            assert record['end_offset'] <= start
        save('COMPLETE.json', {'counts': counts, 'calls': calls, 'source_slices_verified': True,
            'expert_gold': False, 'benchmark_accuracy': False, 'accepted_prerequisites': 0})
        graph.close()
        constructor.openai.close()
        print('Persisted provisional graph:', counts, flush=True)
    except Exception as exc:
        save('FAILED.json', {'error': f'{type(exc).__name__}: {exc}', 'calls': calls})
        raise


if __name__ == '__main__':
    main()
