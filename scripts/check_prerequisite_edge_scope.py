"""Live Neo4j synthetic control: earlier nodes cannot authorize later/missing edge evidence."""
import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.config.settings import Settings
from src.graph_store.neo4j_client import Neo4jClient


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    source = f'edge-scope-control-v2-{stamp}'
    output = ROOT / 'artifacts/prerequisite_edge_scope_v2' / stamp
    output.mkdir(parents=True)
    settings = Settings(_env_file=None, neo4j_uri='bolt://127.0.0.1:7687',
                        neo4j_user='neo4j', neo4j_password='password')
    client = Neo4jClient(settings)
    edges = {
        'valid': dict(source_id=source, start_offset=40, end_offset=50),
        'boundary': dict(source_id=source, start_offset=90, end_offset=100),
        'future': dict(source_id=source, start_offset=100, end_offset=101),
        'missing': dict(source_id=source),
        'cross': dict(source_id='other-source', start_offset=40, end_offset=50),
        'float': dict(source_id=source, start_offset=0.0, end_offset=50),
        'bool': dict(source_id=source, start_offset=False, end_offset=50),
        'reversed': dict(source_id=source, start_offset=50, end_offset=40),
        'zero': dict(source_id=source, start_offset=40, end_offset=40),
    }
    def node(name):
        return dict(id=f'{source}:{name}', name=name, source_id=source,
                    start_offset=0, end_offset=20, chapter=1,
                    content='Synthetic prior node', entity_review='SYNTHETIC_CONTROL')
    nodes = [node(name) for name in ['seed', *edges, 'hidden_prior']]
    try:
        for record in nodes:
            client.create_node('Concept', record['id'], record)
        for name, props in edges.items():
            client.create_relationship(f'{source}:{name}', 'Concept', f'{source}:seed', 'Concept',
                                       'PREREQUISITE_OF', {**props, 'assertion_kind': 'SYNTHETIC_CONTROL'})
        # Both endpoints and the upper path edge are earlier; the lower edge is future.
        client.create_relationship(f'{source}:hidden_prior', 'Concept', f'{source}:future', 'Concept',
                                   'PREREQUISITE_OF', dict(source_id=source, start_offset=40,
                                       end_offset=50, assertion_kind='SYNTHETIC_CONTROL'))
        scoped = client.get_prerequisites(f'{source}:seed', source_id=source, before_position=100)
        legacy = client.get_prerequisites(f'{source}:seed')
        found = sorted(r['node']['name'] for r in scoped)
        assert found == ['boundary', 'valid'], found
        assert len(legacy) == len(edges) + 1
        report = {'status': 'PASS', 'kind': 'SYNTHETIC_CONTROL_NOT_TEXTBOOK_GOLD',
                  'source_id': source, 'cutoff': 100, 'nodes': nodes, 'edge_cases': edges,
                  'scoped_names': found, 'scoped_results': scoped,
                  'legacy_count': len(legacy), 'hidden_prior_blocked': True,
                  'hashes': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                             for p in [Path(__file__), ROOT / 'src/graph_store/neo4j_client.py']}}
        (output / 'result.json').write_text(json.dumps(report, indent=2) + '\n')
        print(json.dumps({'output': str(output), 'scoped_names': found, 'legacy_count': len(legacy)}))
    except Exception as exc:
        (output / 'FAILED.json').write_text(json.dumps({'error': str(exc), 'source_id': source}, indent=2))
        raise
    finally:
        client.close()


if __name__ == '__main__':
    main()
