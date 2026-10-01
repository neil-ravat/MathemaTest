"""Build a new source-checked rendering with structural roles and text excerpts.

Source files, original corpus, IDs and ordering remain unchanged.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path
import sys
import xml.etree.ElementTree as ET
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scripts.prepare_openstax import render


def independent_prefix(text):
    """Retain complete sentences before the first unrendered reference/media.

    This establishes an exact textual excerpt, not semantic independence. Later
    entailment checks still decide what the excerpt actually supports.
    """
    marker = re.search(r'\[reference:|\[unrendered-media\]', text)
    if marker is None:
        return None
    prefix = text[:marker.start()]
    ends = list(re.finditer(r'[.!?](?:\s|$)', prefix))
    if not ends:
        return None
    end = ends[-1].start() + 1
    quote = text[:end].strip()
    # Do not detach a sentence already referring to an unavailable visual.
    if not quote or re.search(r'\b(figure|diagram|graph above|graph below|shown above|shown below)\b', quote, re.I):
        return None
    start = text.index(quote)
    return dict(quote=quote, start=start, end=start+len(quote),
                parent_sha256=hashlib.sha256(text.encode()).hexdigest())


def section_roles(path):
    roles = {}
    def visit(node, exercise=False):
        exercise = (exercise or 'section-exercises' in node.get('class', '').split()
                    or node.tag.rsplit('}', 1)[-1] in {'exercise', 'example', 'solution'})
        if node.get('id'):
            roles[node.get('id')] = 'exercise_material' if exercise else 'exposition'
        for child in node:
            visit(child, exercise)
    visit(ET.parse(path).getroot())
    return roles



def source_metadata(path):
    root = ET.parse(path).getroot()
    nodes = {n.get('id'): n for n in root.iter() if n.get('id')}
    roles = section_roles(path)
    metadata = {}
    visual = {'figure', 'media', 'image', 'table'}
    for anchor, node in nodes.items():
        descendants = list(node.iter())
        referenced = [n.get('target-id') for n in descendants if n.get('target-id')]
        external = any(ref not in nodes or any(n.tag.rsplit('}', 1)[-1] in visual for n in nodes[ref].iter()) for ref in referenced)
        metadata[anchor] = dict(instructional_role=roles[anchor],
            contains_exercise_content=any(n is not node and n.tag.rsplit('}', 1)[-1] in {'exercise','example','solution'} for n in descendants),
            requires_external_media=external)
    return metadata

def build(source, destination):
    manifest = json.loads((source/'manifest.json').read_text())
    corpus = source/'corpus.jsonl'
    if hashlib.sha256(corpus.read_bytes()).hexdigest() != manifest['corpus_sha256']:
        raise ValueError('Original corpus hash mismatch')
    for item in manifest['source_files']:
        path = source/'source'/item['path']
        if hashlib.sha256(path.read_bytes()).hexdigest() != item['sha256']:
            raise ValueError('Pinned source hash mismatch: '+item['path'])
    records = [json.loads(line) for line in corpus.read_text().splitlines()]
    modules = {r['module_id'] for r in records}
    roles = {m: source_metadata(source/'source/modules'/m/'index.cnxml') for m in modules}
    nodes = {m: {n.get('id'): n for n in ET.parse(source/'source/modules'/m/'index.cnxml').getroot().iter()
                 if n.get('id')} for m in modules}
    for row in records:
        row.update(roles[row['module_id']].get(row['anchor'], {'instructional_role':'unknown'}))
        node = nodes[row['module_id']].get(row['anchor'])
        if node is not None:
            body = node.find('{http://cnx.rice.edu/cnxml}problem') if row['kind']=='exercise' else node
            if body is not None:
                unsupported = set()
                row['content'] = re.sub(r'\s+', ' ', render(body, unsupported)).strip()
                row['unsupported_mathml'] = sorted(unsupported)
                row['xml_sha256'] = hashlib.sha256(ET.tostring(body)).hexdigest()
        if (row.get('has_media') or row.get('requires_external_media')) and not row.get('contains_exercise_content'):
            excerpt = independent_prefix(row['content'])
            if excerpt:
                row['retrieval_excerpt'] = excerpt
    destination.mkdir(parents=True, exist_ok=False)
    output = destination/'corpus.jsonl'
    output.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
    (destination/'manifest.json').write_text(json.dumps(dict(
        parent_manifest=str((source/'manifest.json').resolve()), parent_corpus_sha256=manifest['corpus_sha256'],
        corpus_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), records=len(records),
        exercise_material=sum(r['instructional_role']=='exercise_material' for r in records),
        scope='Source-checked re-rendering and structural metadata; no educational labels or fresh-test designation',
        rendering='Explicit table row/cell boundaries and exact prefixes before media references',
        retained_text_excerpts=sum('retrieval_excerpt' in r for r in records)), indent=2))
    return records


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();rows=build(args.source,args.destination)
    print(len(rows),'records preserved;',sum(r['instructional_role']=='exercise_material' for r in rows),'exercise-section records tagged')
