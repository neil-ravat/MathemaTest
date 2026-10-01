"""Freeze and construct a source-scoped corpus without displaying fresh questions.

No retries, no answer key access, no prompt tuning. Each chapter's graph status is
explicit; rejected/empty graphs are not successful graph baselines.
"""
import argparse
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

CONSTRUCTION = dict(model='qwen2.5-coder:7b', reviewer_model='mistral:latest',
    options=dict(temperature=0, seed=42, num_ctx=32768, num_predict=5000),
    request_timeout_seconds=900,
    retries=0, graph_prefix_rule='source start through earliest selected target start',
    max_graph_prefix_characters=48000, expert_gold=False,
    graph_semantics='provisional model-checked facts; no accepted educational prerequisites')


def validate_cases(cases):
    if not cases or len({c['id'] for c in cases}) != len(cases):
        raise ValueError('Cases must be nonempty with unique IDs')
    for case in cases:
        if not re.fullmatch(r'(?:jemh1|jesc1)\d{2}', case['source_id']):
            raise ValueError('Unsupported source filename')
        if not (type(case['target_start_offset']) is int and type(case['target_end_offset']) is int
                and 0 <= case['target_start_offset'] < case['target_end_offset']):
            raise ValueError('Invalid target offsets')


def graph_prefix_cutoffs(cases):
    """A shared chapter graph must precede every selected target, not only the last."""
    validate_cases(cases)
    return {code: min(c['target_start_offset'] for c in cases if c['source_id'] == code)
            for code in {c['source_id'] for c in cases}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-file', type=Path, required=True)
    args = parser.parse_args()
    cases_path = args.cases_file.resolve()
    cases = json.loads(cases_path.read_text())
    validate_cases(cases)
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    run = ROOT / 'artifacts/ncert_study_corpus' / stamp
    run.mkdir(parents=True)
    def save(name, data):
        target = run / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n')
    codes = sorted({c['source_id'] for c in cases})
    source_ids = {code: f'{stamp}-study-{code}' for code in codes}
    manifest = dict(construction=CONSTRUCTION, source_ids=source_ids,
        cases_file=str(cases_path), cases_sha256=hashlib.sha256(cases_path.read_bytes()).hexdigest(),
        selected_case_count=len(cases), maximum_planned_graph_calls=3*len(codes),
        graph_source_status={code: {'status': 'pending'} for code in codes},
        source_content_reviewed_by_agent=False, answer_references_accessed=False,
        limitations=['Native text/formula extraction unreviewed',
            'Shared graph excludes all selected targets and their subsequent solutions; per-query evidence remains cutoff-filtered',
            'Model-reviewed facts are not independent expert ground truth'])
    save('construction_lock.json', manifest)
    save('manifest.json', manifest)
    shutil.copyfile(cases_path, run / 'cases_snapshot.json')
    for path in sorted((ROOT / 'src').rglob('*.py')) + [Path(__file__)]:
        target = run / 'source_snapshot' / path.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    print(f'Corpus run: {run}; sources: {len(codes)}; cases: {len(cases)}', flush=True)
    os.environ.update(HF_HOME=str(ROOT / '.cache/huggingface'), HF_HUB_OFFLINE='1',
                      TRANSFORMERS_OFFLINE='1', ANONYMIZED_TELEMETRY='False')
    import httpx
    import torch
    from jsonschema import validate
    from src.config.settings import Settings
    from src.ingestion.ingestion_engine import IngestionEngine
    from src.graph_store.graph_constructor import GraphConstructorAgent
    from src.graph_store.grounded_extractor import extract_grounded_source
    from src.graph_store.neo4j_client import Neo4jClient
    from src.vector_store.chroma_client import ChromaVectorStore
    torch.set_num_threads(2)
    settings = Settings(_env_file=None, openai_api_key='ollama',
        openai_base_url='http://127.0.0.1:11434/v1', neo4j_uri='bolt://127.0.0.1:7687',
        neo4j_user='neo4j', neo4j_password='password',
        chroma_persist_directory=str(run / 'chroma'))
    graph = Neo4jClient(settings)
    http = httpx.Client(timeout=CONSTRUCTION['request_timeout_seconds'])
    try:
        graph.driver.verify_connectivity()
        graph.initialize_schema()
        response = http.get('http://127.0.0.1:11434/api/tags')
        response.raise_for_status()
        tags = response.json()
        save('models.json', tags)
        if not {CONSTRUCTION['model'], CONSTRUCTION['reviewer_model']} <= {m['name'] for m in tags['models']}:
            raise ValueError('Required local models unavailable')
        store = ChromaVectorStore(settings=settings, collection_name='ncert-connected-smoke')
        store.embedder.device = 'cpu'
        ingestion, documents = {}, []
        for code in codes:
            selected = [c for c in cases if c['source_id'] == code]
            boundaries = [c[k] for c in selected for k in ('target_start_offset', 'target_end_offset')]
            ingested = IngestionEngine.process_digital_pdf(cases_path.parent / 'raw' / f'{code}.pdf',
                source_ids[code], int(code[-2:]), split_boundaries=boundaries)
            for case in selected:
                if ingested['pdf_sha256'] != case['source_pdf_sha256']:
                    raise ValueError(f'Pinned PDF hash changed: {code}')
                if hashlib.sha256(ingested['text'].encode()).hexdigest() != case['source_text_sha256']:
                    raise ValueError(f'Pinned text hash changed: {code}')
                if ingested['text'][case['target_start_offset']:case['target_end_offset']] != case['target_raw']:
                    raise ValueError(f'Target span mismatch: {code}')
            ingestion[code] = ingested
            documents.extend(ingested['documents'])
        save('ingestion.json', ingestion)
        for doc in documents:
            graph.create_node('Concept', doc['id'], {**doc,
                'name': doc['content'].strip().splitlines()[0][:80],
                'evidence_kind': 'original_source_span', 'entity_review': 'NATIVE_TEXT_BLOCK'})
        store.add_documents(documents)
        print(f'Indexed {len(documents)} native source spans.', flush=True)
    except Exception as exc:
        save('FAILED.json', dict(stage='preflight_or_ingestion', error=f'{type(exc).__name__}: {exc}', model_calls=0))
        graph.close()
        http.close()
        raise
    calls = []
    constructor = GraphConstructorAgent(settings=settings, neo4j_client=graph)
    for code in codes:
        source_id = source_ids[code]
        cutoff = graph_prefix_cutoffs(cases)[code]
        content = dict(source_id=source_id, chapter=int(code[-2:]), start_offset=0,
                       end_offset=cutoff, content=ingestion[code]['text'][:cutoff])
        def call(stage, system, payload, schema, model):
            request = dict(model=model, messages=[dict(role='system', content=system),
                dict(role='user', content=json.dumps(payload, ensure_ascii=False))],
                stream=False, format=schema, options=CONSTRUCTION['options'], keep_alive='5m')
            save(f'{code}/{stage}_request.json', request)
            row = dict(source_id=code, stage=stage, model=model)
            started = time.perf_counter()
            try:
                response = http.post('http://127.0.0.1:11434/api/chat', json=request)
                save(f'{code}/{stage}_http_response.json', dict(status=response.status_code, body=response.text))
                response.raise_for_status()
                body = response.json()
                save(f'{code}/{stage}_response.json', body)
                row.update(prompt_tokens=body.get('prompt_eval_count'), output_tokens=body.get('eval_count'))
                if not body.get('done') or body.get('done_reason') != 'stop':
                    raise ValueError('Incomplete model response')
                parsed = json.loads(body['message']['content'])
                validate(parsed, schema)
                return parsed
            except Exception as exc:
                row['error'] = f'{type(exc).__name__}: {exc}'
                raise
            finally:
                row['seconds'] = time.perf_counter() - started
                calls.append(row)
                save('calls.json', calls)
                print(f'{code}: {stage}: ' + ('error' if 'error' in row else 'completed'), flush=True)
        try:
            if cutoff > CONSTRUCTION['max_graph_prefix_characters']:
                raise ValueError('Source prefix exceeds frozen character cap; not silently truncated')
            extracted, review = extract_grounded_source(content, call,
                model=CONSTRUCTION['model'], reviewer_model=CONSTRUCTION['reviewer_model'])
            save(f'{code}/review.json', review)
            save(f'{code}/extraction.json', asdict(extracted))
            counts = constructor.persist_extraction(extracted, source_id=source_id)
            with graph.session() as session:
                entities = [dict(r['n']) for r in session.run(
                    "MATCH (n) WHERE n.source_id=$s AND n.entity_review='MODEL_CHECKED_NOT_GOLD' RETURN n", s=source_id)]
            for entity in entities:
                if not (0 <= entity['start_offset'] < entity['end_offset'] <= cutoff and
                    entity['content'] == ingestion[code]['text'][entity['start_offset']:entity['end_offset']]):
                    raise ValueError('Extracted entity source mismatch')
            if entities:
                store.add_documents(entities)
            status = 'success' if counts['nodes'] and counts['relationships'] else 'empty'
            manifest['graph_source_status'][code] = dict(status=status, counts=counts,
                prefix_end_offset=cutoff, accepted_prerequisites=0)
        except Exception as exc:
            manifest['graph_source_status'][code] = dict(status='error', prefix_end_offset=cutoff,
                error=f'{type(exc).__name__}: {exc}')
        save('manifest.json', manifest)
        print(f'{code}: graph {manifest["graph_source_status"][code]["status"]}', flush=True)
    save('COMPLETE.json', dict(case_count=len(cases), graph_source_status=manifest['graph_source_status'],
         model_calls=len(calls), expert_gold=False, answer_references_accessed=False))
    constructor.openai.close()
    graph.close()
    http.close()


if __name__ == '__main__':
    main()
