"""Focused scope tests; doubles exercise boundaries without modifying live databases."""
from contextlib import contextmanager
from types import SimpleNamespace

import pytest

from src.graph_store.neo4j_client import Neo4jClient
from src.retrieval.hybrid_orchestrator import HybridRetriever
from src.vector_store.chroma_client import ChromaVectorStore


def node(id, end=20, source='run-book', **extra):
    return dict(id=id, source_id=source, start_offset=0, end_offset=end,
                chapter=4, content=f'Original {id}', **extra)


def test_vector_database_filter_and_defensive_boundary():
    store = object.__new__(ChromaVectorStore)
    store.embedder = SimpleNamespace(embed=lambda _: SimpleNamespace(tolist=lambda: [[1.0]]))
    nodes = [node('before', 99), node('boundary', 100), node('after', 101),
             node('other', 1, 'another-run'), {'id': 'missing', 'chapter': 4}]
    captured = {}

    def query(**kwargs):
        captured.update(kwargs)
        return {'ids': [[n['id'] for n in nodes]], 'documents': [['text'] * 5],
                'metadatas': [nodes], 'distances': [[0.1] * 5]}

    store._collection = SimpleNamespace(query=query)
    rows = store.search('roots', source_id='run-book', before_position=100, max_chapter=1)
    assert [r['id'] for r in rows] == ['before', 'boundary']
    assert captured['where'] == {'$and': [
        {'source_id': {'$eq': 'run-book'}}, {'start_offset': {'$gte': 0}},
        {'start_offset': {'$lt': 100}}, {'end_offset': {'$gt': 0}},
        {'end_offset': {'$lte': 100}}]}
    store.search('roots', max_chapter=3)
    assert captured['where'] == {'chapter': {'$lte': 3}}


def test_graph_queries_scope_entire_incoming_path_and_seed_terms():
    client = object.__new__(Neo4jClient)
    calls = []

    @contextmanager
    def session():
        def run(query, **params):
            calls.append((query, params))
            if 'MATCH path' in query:
                assert '(c {id: $id})<-[:PREREQUISITE_OF*1..2]-(prereq)' in query
                assert 'ALL(v IN nodes(path) WHERE' in query
                assert 'v.source_id = $source_id' in query
                assert 'v.end_offset <= $before_position' in query
                assert 'v.start_offset IS :: INTEGER' in query
                assert 'v.end_offset IS :: INTEGER' in query
                assert 'v.start_offset < v.end_offset' in query
                assert 'ALL(r IN relationships(path) WHERE' in query
                assert 'r.source_id = $source_id' in query
                assert 'r.start_offset IS :: INTEGER' in query
                assert 'r.end_offset IS :: INTEGER' in query
                assert 'r.start_offset >= 0' in query
                assert 'r.start_offset < r.end_offset' in query
                assert 'r.end_offset <= $before_position' in query
                return [{'prereq': node('prerequisite'), 'distance': 1,
                         'path_ids': ['dependent', 'prerequisite']}]
            assert 'n.source_id = $source_id' in query
            assert 'n.end_offset <= $before_position' in query
            assert 'n.id IN $seed_ids' in query and 'ANY(term IN $terms' in query
            return [{'n': node('dependent'), 'types': ['Concept']}]
        yield SimpleNamespace(run=run)

    client.session = session
    seeds = client.search_concepts('Find the quadratic roots', source_id='run-book',
                                   before_position=100, seed_ids=['dependent'])
    assert seeds[0]['node']['content'] == 'Original dependent'
    assert calls[-1][1]['terms'] == ['quadratic', 'roots']
    paths = client.get_prerequisites('dependent', source_id='run-book', before_position=100)
    assert paths[0]['path_ids'] == ['dependent', 'prerequisite']
    assert paths[0]['node']['start_offset'] == 0


def retriever(vector_rows=None, graph_nodes=None, paths=None):
    h = object.__new__(HybridRetriever)
    h.vector_store = SimpleNamespace(search=lambda **kw: vector_rows or [])
    h.graph_client = SimpleNamespace(
        search_concepts=lambda **kw: graph_nodes or [],
        get_prerequisites=lambda *args, **kw: paths or [])
    h.reranker = SimpleNamespace(rerank=lambda q, rows, top_k: rows[:top_k])
    return h


def test_scoped_audit_excludes_later_missing_cross_source_and_preserves_paths():
    nodes = [node('dependent', 100), node('later', 101), node('other', 50, 'other-run'),
             {'id': 'missing', 'chapter': 4, 'content': 'unknown'}]
    vector = [{'id': n['id'], 'content': n['content'], 'metadata': n} for n in nodes]
    graph = [{'node': n, 'types': ['Concept']} for n in nodes]
    h = retriever(vector, graph, [{'node': node('prerequisite', 50), 'distance': 1,
                                  'path_ids': ['dependent', 'prerequisite']}])
    rows = h.retrieve_for_audit('long question about roots', current_chapter=4,
                               source_id='run-book', before_position=100, rerank=False)
    assert [r.id for r in rows] == ['dependent', 'prerequisite']
    assert rows[0].metadata['graph_provenance'][0]['kind'] == 'seed'
    assert rows[1].content == 'Original prerequisite'
    assert rows[1].metadata['source_id'] == 'run-book'
    assert rows[1].metadata['end_offset'] == 50
    assert rows[0].metadata['graph_trace']['expansions'][0]['path_ids'] == ['dependent', 'prerequisite']


@pytest.mark.parametrize('kwargs', [{'source_id': 'x'}, {'before_position': 5},
                                  {'source_id': '', 'before_position': 1},
                                  {'source_id': 'x', 'before_position': -1},
                                  {'source_id': 'x', 'before_position': True}])
def test_invalid_scope_rejected_at_all_entry_points(kwargs):
    with pytest.raises(ValueError):
        retriever().retrieve_for_audit('q', **kwargs)
    with pytest.raises(ValueError):
        object.__new__(ChromaVectorStore).search('q', **kwargs)
    with pytest.raises(ValueError):
        object.__new__(Neo4jClient).search_concepts('q', **kwargs)
    with pytest.raises(ValueError):
        object.__new__(Neo4jClient).get_prerequisites('id', **kwargs)


@pytest.mark.parametrize('branch', ['vector', 'graph', 'path', 'rerank'])
def test_scoped_errors_are_not_partial_success(branch):
    h = retriever([{'id': 'dependent', 'content': 'source', 'metadata': node('dependent')}],
                  [{'node': node('dependent'), 'types': ['Concept']}])
    def fail(*args, **kwargs):
        raise RuntimeError('backend failed')
    if branch == 'vector': h.vector_store.search = fail
    if branch == 'graph': h.graph_client.search_concepts = fail
    if branch == 'path': h.graph_client.get_prerequisites = fail
    if branch == 'rerank': h.reranker.rerank = fail
    with pytest.raises(RuntimeError, match='backend failed'):
        h.retrieve_for_audit('q', source_id='run-book', before_position=100)


def test_prerequisite_fixture_rejects_unsafe_intermediate_and_wrong_direction():
    """The session double evaluates the asserted incoming/all-node query on a tiny graph."""
    nodes = {n['id']: n for n in [node('seed', 100), node('prior', 80),
        node('future', 101), node('cross', 20, 'another-run'),
        node('hidden-prior', 5), node('dependent', 90)]}
    nodes['missing'] = {'id': 'missing', 'source_id': 'run-book'}
    edges = [('prior', 'seed'), ('future', 'seed'), ('cross', 'seed'),
             ('missing', 'seed'), ('hidden-prior', 'future'), ('seed', 'dependent')]
    client = object.__new__(Neo4jClient)

    @contextmanager
    def session():
        def run(query, **params):
            assert '(c {id: $id})<-[:PREREQUISITE_OF*1..2]-(prereq)' in query
            assert 'ALL(v IN nodes(path) WHERE' in query
            def safe(id):
                n = nodes[id]
                return n.get('source_id') == params['source_id'] and type(n.get('start_offset')) is int and type(n.get('end_offset')) is int and 0 <= n['start_offset'] < n['end_offset'] <= params['before_position']
            frontier = [[params['id']]]
            result = []
            for _ in range(2):
                following = []
                for path in frontier:
                    for prerequisite, dependent in edges:
                        if dependent == path[-1]:
                            extended = path + [prerequisite]
                            if all(safe(id) for id in extended):
                                result.append({'prereq': nodes[prerequisite], 'distance': len(extended)-1, 'path_ids': extended})
                                following.append(extended)
                frontier = following
            return result
        yield SimpleNamespace(run=run)

    client.session = session
    found = client.get_prerequisites('seed', source_id='run-book', before_position=100)
    assert [r['node']['id'] for r in found] == ['prior']
    assert found[0]['path_ids'] == ['seed', 'prior']


@pytest.mark.parametrize('bad_span', [{"end_offset": 10}, {"start_offset": 5, "end_offset": 5},
    {"start_offset": 20, "end_offset": 10}, {"start_offset": 0, "end_offset": 0},
    {"start_offset": 0.0, "end_offset": 10}, {"start_offset": False, "end_offset": 10}])
def test_invalid_spans_are_excluded(bad_span):
    metadata = {"id": "bad", "source_id": "run-book", "content": "original", **bad_span}
    h = retriever([{"id": "bad", "content": "original", "metadata": metadata}],
                  [{"node": metadata, "types": ["Concept"]}])
    assert h.retrieve_for_audit('q', source_id='run-book', before_position=100) == []
    store = object.__new__(ChromaVectorStore)
    store.embedder = SimpleNamespace(embed=lambda _: SimpleNamespace(tolist=lambda: [[1.0]]))
    store._collection = SimpleNamespace(query=lambda **kw: {
        'ids': [['bad']], 'documents': [['original']], 'metadatas': [[metadata]], 'distances': [[0.1]]})
    assert store.search('q', source_id='run-book', before_position=100) == []


def test_unscoped_prerequisite_query_keeps_legacy_behavior():
    client = object.__new__(Neo4jClient)
    calls = []

    @contextmanager
    def session():
        def run(query, **params):
            calls.append(query)
            return []
        yield SimpleNamespace(run=run)

    client.session = session
    assert client.get_prerequisites('seed', max_chapter=4) == []
    assert 'prereq.chapter <= $max_chapter' in calls[-1]
    assert 'relationships(path)' not in calls[-1]
    assert client.get_prerequisites('seed') == []
    assert 'relationships(path)' not in calls[-1]


def test_rule_channel_reserves_slot_without_relaxing_scope_or_budget():
    regular = [{'id':str(i), 'content':'A similar exercise', 'metadata':node(str(i), 20)} for i in range(4)]
    rule = {'id':'rule', 'content':'The quantity is directly proportional to its input at constant temperature.',
            'metadata':node('rule', 90)}
    future = {'id':'future-rule', 'content':'The formula is defined as x = y.', 'metadata':node('future-rule', 101)}
    cross = {'id':'other-rule', 'content':'The formula is defined as x = y.', 'metadata':node('other-rule', 10, 'other')}
    h = retriever()
    calls = []
    def search(**kwargs):
        calls.append(kwargs)
        return [future, cross, rule] if kwargs.get('where_document') else regular
    h.vector_store.search = search
    results = h.retrieve_for_audit('Question', source_id='run-book', before_position=100, n_results=4)
    assert len(results) == 4 and results[0].id == 'rule'
    assert results[0].metadata['graph_trace']['rule_candidate_ids'] == ['rule']
    assert all(c['source_id']=='run-book' and c['before_position']==100 for c in calls)
    assert calls[1]['where_document']['$or']
    assert [r.id for r in h.retrieve_for_audit('Question',source_id='run-book',before_position=100,n_results=1)] == ['rule']


def test_rule_slot_deduplicates_same_source_span():
    first = {'id':'first','content':'The quantity is defined as x = y.', 'metadata':node('first', 20)}
    alias = {**first, 'id':'alias'}
    h = retriever()
    h.vector_store.search = lambda **kw: [alias] if kw.get('where_document') else [first]
    results = h.retrieve_for_audit('Question',source_id='run-book',before_position=100)
    assert len(results) == 1 and results[0].id == 'alias'
