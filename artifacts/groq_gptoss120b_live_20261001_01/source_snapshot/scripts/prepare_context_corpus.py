"""Preserve CNXML exercise-section roles in a new, hash-checked corpus version.

Original text, IDs, ordering and the original corpus remain unchanged.
"""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET


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
    for row in records:
        row.update(roles[row['module_id']].get(row['anchor'], {'instructional_role':'unknown'}))
    destination.mkdir(parents=True, exist_ok=False)
    output = destination/'corpus.jsonl'
    output.write_text(''.join(json.dumps(r, ensure_ascii=False)+'\n' for r in records))
    (destination/'manifest.json').write_text(json.dumps(dict(
        parent_manifest=str((source/'manifest.json').resolve()), parent_corpus_sha256=manifest['corpus_sha256'],
        corpus_sha256=hashlib.sha256(output.read_bytes()).hexdigest(), records=len(records),
        exercise_material=sum(r['instructional_role']=='exercise_material' for r in records),
        scope='Structural metadata only; no new educational labels or fresh-test designation'), indent=2))
    return records


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source',type=Path);parser.add_argument('destination',type=Path)
    args=parser.parse_args();rows=build(args.source,args.destination)
    print(len(rows),'records preserved;',sum(r['instructional_role']=='exercise_material' for r in rows),'exercise-section records tagged')
