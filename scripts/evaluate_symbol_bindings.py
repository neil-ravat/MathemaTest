"""Replay AI-labelled development fixtures; not independent benchmark accuracy."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from src.ingestion.source_quality import quantity_symbol_mentions


def evaluate(path):
    fixture = json.loads(path.read_text())
    # Source-backed fixtures must still match the pinned PDF and exact page slices.
    if 'source_pdf' in fixture:
        from src.ingestion.pdf_region import read_pdf_page, layout_text
        pdf = ROOT/fixture['source_pdf']
        if hashlib.sha256(pdf.read_bytes()).hexdigest() != fixture['pdf_sha256']:
            raise ValueError('Development PDF hash mismatch')
        pages = {page: layout_text(read_pdf_page(pdf,page)[1])[0]
                 for page in {c['pdf_page'] for c in fixture['cases']}}
        for case in fixture['cases']:
            text = pages[case['pdf_page']]
            if (hashlib.sha256(text.encode()).hexdigest() != case['page_text_sha256']
                    or text[case['page_text_start']:case['page_text_end']] != case['text']):
                raise ValueError(f"Source evidence mismatch: {case['id']}")
    rows = []
    totals = {name: dict(tp=0, fp=0, fn=0, exact_cases=0) for name in ('previous_pdf_parser','current_parser')}
    for case in fixture['cases']:
        text = case['text']
        expected = {tuple(p) for p in case['expected']}
        mentions = quantity_symbol_mentions([dict(content=text,evidence_id=0,start_offset=0,end_offset=len(text))])
        assert all(text[m['start_offset']:m['end_offset']]==m['source_phrase'] for m in mentions)
        actual = {(m['symbol'],m['name']) for m in mentions}
        old = {(m['symbol'],m['label']) for m in re.finditer(
            r'(?P<label>[a-z]+)\s+(?P<symbol>[A-Za-z])(?=\s*[,;.)])',text)}
        row = dict(id=case['id'], kind=case['kind'], expected=sorted(expected))
        for name, prediction in [('previous_pdf_parser',old),('current_parser',actual)]:
            counts=dict(tp=len(prediction & expected),fp=len(prediction-expected),fn=len(expected-prediction),
                        exact_cases=int(prediction==expected))
            for key,value in counts.items(): totals[name][key]+=value
            row[name]=dict(predicted=sorted(prediction),**counts)
        rows.append(row)
    for scores in totals.values():
        scores['precision']=scores['tp']/(scores['tp']+scores['fp']) if scores['tp']+scores['fp'] else None
        scores['recall']=scores['tp']/(scores['tp']+scores['fn']) if scores['tp']+scores['fn'] else None
    return dict(label_provenance=fixture['label_provenance'],case_count=len(rows),
        metric='unique (symbol, canonical quantity label) pairs per excerpt; occurrence offsets checked separately',
        scope='binding parser only; equations, crop detection and semantic truth not scored',
        expert_gold=False, heldout=False, totals=totals, cases=rows)


if __name__ == '__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--fixture',type=Path,default=ROOT/'tests/fixtures/symbol_bindings_development.json')
    parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args()
    result=evaluate(args.fixture)
    with args.output.open('x') as output:
        json.dump(result,output,indent=2)
    print(json.dumps(result['totals'],indent=2))
