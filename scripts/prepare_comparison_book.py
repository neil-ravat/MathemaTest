"""Download pinned OpenStax Physics source chapters for a fresh exploratory check.

Downloads public CNXML only; does not call a model, download media or start compute.
The original calculus corpus and all prior experiment artifacts remain unchanged.
"""
import hashlib
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor
from urllib.request import Request,urlopen
import xml.etree.ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.prepare_openstax import extract_module,COL,MD

REVISION='dfdfd7a5356ecdd42e504de3df50d9153e33ea49'
REPOSITORY='https://github.com/openstax/osbooks-physics'
RAW=f'https://raw.githubusercontent.com/openstax/osbooks-physics/{REVISION}/'
DEST=ROOT/'artifacts/six_improvements_20261001/physics_source'


def download(name):
    path=DEST/'source'/name
    if not path.exists():
        with urlopen(Request(RAW+name,headers={'User-Agent':'MathemaTest-research'}),timeout=45) as response:data=response.read()
        path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)
    return dict(path=name,url=RAW+name,sha256=hashlib.sha256(path.read_bytes()).hexdigest())


def main():
    collection='collections/physics.collection.xml'
    sources=[download(name) for name in ['LICENSE','README.md',collection]]
    tree=ET.parse(DEST/'source'/collection).getroot()
    modules=[];chapter=0
    # Include the full preceding book boundary for sampled targets in chapters
    # 1--3; do not make a later chapter look unsupported by omitting earlier ones.
    for part in tree.find(COL+'content'):
        if part.tag==COL+'subcollection':
            chapter+=1
            if chapter<=3:modules.extend((n.get('document'),chapter) for n in part.iter(COL+'module'))
        elif part.tag==COL+'module':modules.append((part.get('document'),0))
    paths=[f'modules/{mid}/index.cnxml' for mid,_ in modules]
    with ThreadPoolExecutor(max_workers=4) as pool:sources.extend(pool.map(download,paths))
    records=[]
    for order,(mid,ch) in enumerate(modules):
        rows=extract_module(DEST/'source'/paths[order],mid,ch,order,len(records))
        for row in rows:
            row.update(source_id='openstax-physics-'+REVISION[:12],source_url=RAW+paths[order],
                attribution='OpenStax, Physics. https://openstax.org/details/books/physics',license='CC-BY-4.0')
        records.extend(rows)
    output=DEST/'corpus.jsonl';output.write_text(''.join(json.dumps(r,ensure_ascii=False)+'\n' for r in records))
    manifest=dict(repository=REPOSITORY,revision=REVISION,collection=collection,
        license=tree.find('.//'+MD+'license').get('url'),source_files=sources,
        records=len(records),chapters=[1,2,3],corpus_sha256=hashlib.sha256(output.read_bytes()).hexdigest(),
        scope='New source book; chapters 1--3 and preceding material. No labels or inference.')
    (DEST/'manifest.json').write_text(json.dumps(manifest,indent=2))
    print('Downloaded',len(modules),'modules;',len(records),'records; no inference.')


if __name__=='__main__':main()
