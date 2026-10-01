"""Constructed curricula with arithmetic ground truth; never textbook gold labels."""
import copy
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/controlled_curricula_v1'
CATEGORIES = ('supported', 'missing', 'future', 'background', 'preview', 'false')


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()


def trees(n):
    if n == 0:
        return [None]
    return [(a, b) for k in range(n) for a in trees(k) for b in trees(n-1-k)]


def generate():
    # Whole ordered dependency topologies, not renamed copies, determine splits.
    shapes = (trees(2) + trees(3) + trees(4))[:20]
    cases = []
    for family, shape in enumerate(shapes):
        split = 'development' if family < 8 else 'heldout'
        docs, nodes = [], {}

        def build(tree):
            if tree is None:
                return 'x'
            left, right = (build(t) for t in tree)
            name = f'fun{family}_{len(nodes)}'
            offset = len(nodes) + 1
            nodes[name] = [left, right, offset]
            term = lambda t: 'x' if t == 'x' else f'{t}(x)'
            equation = f'{name}(x) = {term(left)} + {term(right)} + {offset}'
            wording = f'Define {equation}.' if split == 'development' else f'For integer x, the rule is {equation}.'
            docs.append({'id': name, 'content': wording, 'position': 10*(len(docs)+1),
                         'references': list(dict.fromkeys(t for t in (left, right) if t != 'x'))})
            return name

        root = build(shape)
        missing_id = docs[0]['id']
        for category in CATEGORIES:
            case = {'id': digest([family, category])[:16], 'family': f'topology-{family:02}',
                    'topology': shape, 'split': split, 'category': category,
                    'target_position': 100, 'references': [root],
                    'background': 'Integer addition and equality. Function names are local to this curriculum.',
                    'background_passages': [], 'documents': copy.deepcopy(docs),
                    'oracle': {'nodes': copy.deepcopy(nodes), 'root': root, 'x': family % 5 + 1,
                               'preview': category == 'preview'}}
            if category in ('missing', 'future', 'background'):
                passage = next(d for d in case['documents'] if d['id'] == missing_id)
                if category == 'future':
                    passage['position'] = 110
                else:
                    case['documents'].remove(passage)
                    if category == 'background':
                        case['background_passages'].append(passage)
            def value(name):
                if name == 'x':
                    return case['oracle']['x']
                a, b, c = nodes[name]
                return value(a) + value(b) + c
            claim = value(root) + int(category == 'false')
            case['oracle']['claim'] = claim
            expression = f'{root}({case["oracle"]["x"]}) = {claim}'
            if category == 'preview':
                case['target'] = f'Preview: {root} will be used later. No calculation or proof is asserted here.'
            else:
                case['target'] = (f'Check the equality {expression}.' if split == 'development'
                                  else f'The proposed result is {expression}.')
            # Irrelevant earlier content makes a four-passage retrieval budget meaningful.
            case['documents'] += [{'id': f'distractor{family}_{i}', 'position': 60+i,
                'content': f'Define other{family}_{i}(x) = x + {i+1}.', 'references': []} for i in range(5)]
            case['expected'], case['required_ids'] = oracle(case)
            cases.append(case)
    validate(cases)
    return cases


def oracle(case):
    """Evaluate declared operations using only definitions admissible at the target."""
    o = case['oracle']
    if o['preview']:
        return 'PASS', []
    available = {d['id'] for d in case['documents'] if d['position'] < case['target_position']}
    available.update(d['id'] for d in case['background_passages'])
    needed = set()
    def evaluate(name):
        if name == 'x':
            return o['x']
        needed.add(name)
        left, right, offset = o['nodes'][name]
        a, b = evaluate(left), evaluate(right)
        if name not in available or a is None or b is None:
            return None
        return a + b + offset
    result = evaluate(o['root'])
    verdict = 'FAIL_GAP' if result is None else 'PASS' if result == o['claim'] else 'FAIL_LOGIC'
    return verdict, sorted(needed)


def validate(cases):
    from collections import Counter
    assert len(cases) == len({c['id'] for c in cases}) == 120
    assert Counter(c['category'] for c in cases) == {k: 20 for k in CATEGORIES}
    assert Counter(c['split'] for c in cases) == {'development': 48, 'heldout': 72}
    groups = [{digest(c['topology']) for c in cases if c['split'] == split} for split in ('development', 'heldout')]
    assert not groups[0] & groups[1]
    for c in cases:
        assert (c['expected'], c['required_ids']) == oracle(c)
        assert c['expected'] == {'missing':'FAIL_GAP', 'future':'FAIL_GAP', 'false':'FAIL_LOGIC'}.get(c['category'], 'PASS')
        assert len({d['id'] for d in c['documents']}) == len(c['documents'])


def freeze(destination=DEST):
    cases = generate()
    payloads = {split+'.json': json.dumps([c for c in cases if c['split'] == split], indent=2)+'\n'
                for split in ('development', 'heldout')}
    manifest = {'version': 1, 'purpose': 'Synthetic technical benchmark; not natural textbook defects',
                'counts': {'development': 48, 'heldout': 72}, 'split_unit': 'entire ordered dependency topology family',
                'limitations': ['Shared integer-addition domain across splits', 'Heldout topology transfer, not independent pedagogical validation',
                                'Graph uses explicit symbolic references; reference extraction is not evaluated'],
                'files': {name: hashlib.sha256(value.encode()).hexdigest() for name, value in payloads.items()}}
    payloads['manifest.json'] = json.dumps(manifest, indent=2)+'\n'
    destination.mkdir(parents=True, exist_ok=True)
    for name, value in payloads.items():
        path = destination/name
        if path.exists():
            if path.read_text() != value:
                raise ValueError('Frozen benchmark differs; create a new version, never overwrite: '+str(path))
        else:
            with path.open('x') as f:
                f.write(value)
    return manifest


if __name__ == '__main__':
    print(json.dumps(freeze(), indent=2))
