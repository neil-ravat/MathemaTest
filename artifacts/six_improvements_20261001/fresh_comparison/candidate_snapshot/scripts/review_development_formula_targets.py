"""Known-target crop recovery on exposed pages; not exhaustive detector recall."""
import argparse
import hashlib
import json
from pathlib import Path


def evaluate(fixture_path, packets_root):
    fixture=json.loads(fixture_path.read_text())
    rows=[]
    for target in fixture['targets']:
        path=packets_root/f"page_{target['pdf_page']}"/'candidates.json'
        packet=json.loads(path.read_text())
        if packet['pdf_sha256'] != fixture['pdf_sha256']:
            raise ValueError('Candidate source PDF hash mismatch')
        normalized=''.join(target['candidate_text'].split())
        matches=[i for i,c in enumerate(packet['candidates'])
                 if c['source_role']=='unclassified_source'
                 and normalized in ''.join(c['layout_text'].split())]
        rows.append({**target,'candidate_indices':matches,'recovered':bool(matches)})
    return dict(mode='known-target substring coverage of saved crop text; not exhaustive recall or semantic validation',
        expert_gold=False,heldout=False,targets=rows,recovered=sum(r['recovered'] for r in rows),
        total=len(rows),fixture_sha256=hashlib.sha256(fixture_path.read_bytes()).hexdigest())


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,required=True)
    parser.add_argument('--packets',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=evaluate(args.fixture,args.packets)
    with args.output.open('x') as f: json.dump(result,f,indent=2)
    print(f"Known targets recovered: {result['recovered']}/{result['total']}")
