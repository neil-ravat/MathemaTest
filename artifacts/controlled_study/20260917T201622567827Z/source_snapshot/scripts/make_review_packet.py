"""Prepare an offline, prediction-blind development annotation packet."""
import hashlib
import copy
import html
import json
import random
import sys
import xml.etree.ElementTree as ET
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_openstax import CN, MATH, DEST, REVISION

OUT = ROOT / 'artifacts/faculty_review'


def render_html(node, module):
    tag = node.tag.split('}')[-1]
    if node.tag == MATH + 'math':
        math = copy.deepcopy(node)
        math.tail = None
        for part in math.iter():
            part.tag = part.tag.split('}')[-1]
        math.set('xmlns', MATH[1:-1])
        return ET.tostring(math, encoding='unicode')
    if tag in {'media', 'image'}:
        identifier = f' id="{html.escape(node.get("id"))}"' if node.get('id') else ''
        return f'<p{identifier} class="omission">[Image omitted; consult the original textbook if needed.]</p>'
    inner = html.escape(node.text or '') + ''.join(render_html(c, module) + html.escape(c.tail or '') for c in node)
    if tag == 'link':
        target_module = node.get('document', module)
        anchor = node.get('target-id', '')
        if target_module.startswith('m') and target_module[1:].isdigit() and anchor:
            return f'<a href="{html.escape(target_module)}.html#{html.escape(anchor)}">{inner or "source reference"}</a>'
        return inner or '[external reference]'
    mapping = {'para':'p', 'title':'h3', 'section':'section', 'list':'ul', 'item':'li',
               'emphasis':'em', 'term':'strong', 'sup':'sup', 'sub':'sub'}
    dest = mapping.get(tag, 'div')
    identifier = f' id="{html.escape(node.get("id"))}"' if node.get('id') else ''
    return f'<{dest}{identifier}>{inner}</{dest}>'


def main():
    records = [json.loads(line) for line in (DEST/'corpus.jsonl').read_text().splitlines()]
    candidates = [r for r in records if r['is_target'] and r['chapter'] > 0
                  and r['kind'] in {'rule','definition','note'} and not r['unsupported_mathml']
                  and not r.get('has_media', False) and 60 <= len(r['content']) <= 2500]
    rng = random.Random(42)
    selected = []
    for chapter in range(1,7):
        group = [r for r in candidates if r['chapter'] == chapter]
        selected.extend(rng.sample(group, min(10, len(group))))
    selected.sort(key=lambda r:r['position'])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/'source').mkdir(exist_ok=True)
    (OUT/'LICENSE.txt').write_bytes((DEST/'source/LICENSE').read_bytes())
    (OUT/'README.txt').write_text('''MathemaTest independent development review

Extract the entire ZIP, then open review.html in a modern browser.
Keep the source folder beside review.html. No installation or model is needed.
Use contents.html to inspect earlier textbook sections. Work independently.
Use reviewer codes A and B; do not put names in the exported file.
Start with the first five cases as a calibration round, export separately, then
resolve rubric ambiguities before the remaining independent reviews.
The form does not autosave or import previous exports. Export before closing;
if continuing another session, label the remaining cases and keep both exports.
Return the JSON exports to the researcher. Do not discuss individual judgments
with the second reviewer until both independent reviews are saved.
All 55 examples are development data, not a held-out evaluation set.

OpenStax, Calculus Volume 1: https://openstax.org/details/books/calculus-volume-1
Adapted excerpts and source readers retain the CC BY-NC-SA 4.0 license in
LICENSE.txt. Images are omitted. Original MathML is retained. The manifest
identifies the pinned source revision. This is not an official OpenStax product.
''')
    style = 'body{font:17px/1.6 system-ui;max-width:1050px;margin:36px auto;padding:0 24px;color:#18303b}h1,h2,h3{line-height:1.2}a{color:#086980}math{font-size:1.1em}section,details{padding:12px;border-bottom:1px solid #cbd5df}select,textarea,input,button{font:inherit;padding:8px;margin:8px 0}textarea{width:96%;min-height:70px}.omission{color:#805300}header{background:#edf5f7;padding:20px}button{cursor:pointer;background:#0d5367;color:white;border:0;border-radius:5px}.target{background:#f5f8fa;padding:18px}'
    snippets = {}
    contents = []
    for path in sorted((DEST/'source/modules').glob('*/index.cnxml')):
        module = path.parent.name
        tree = ET.parse(path).getroot()
        body = tree.find(CN+'content')
        module_records = [r for r in records if r['module_id'] == module]
        contents.append((min(r['position'] for r in module_records), module,
                         tree.findtext(CN+'title', 'Textbook module'), module_records[0]['chapter']))
        for case in [r for r in selected if r['module_id'] == module]:
            element = next(n for n in body.iter() if n.get('id') == case['anchor'])
            snippets[case['id']] = render_html(element,module).replace('href="m', 'href="source/m')
        document = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{html.escape(tree.findtext(CN+"title", "Textbook module"))}</title><style>{style}</style><body><header><a href="../review.html">Back to review packet</a><p>OpenStax, Calculus Volume 1. <a href="https://openstax.org/details/books/calculus-volume-1">Download for free</a>. CC BY-NC-SA 4.0. Source revision {REVISION}. Text and MathML preserved; images omitted.</p></header>'
        document += render_html(body,module) + '</body></html>'
        (OUT/'source'/f'{module}.html').write_text(document)
    links = ''.join(f'<li>Chapter {chapter}: <a href="source/{module}.html">{html.escape(title)}</a></li>'
                    for _, module, title, chapter in sorted(contents))
    (OUT/'contents.html').write_text(f'<!doctype html><html lang="en"><meta charset="utf-8"><title>Textbook contents</title><style>{style}</style><body><h1>Source sections in textbook order</h1><p><a href="review.html">Back to review</a>. Chapter 0 denotes front matter or appendices. Images are omitted; consult the original book where needed.</p><ol>{links}</ol></body></html>')
    for source in (OUT/'source').glob('*.html'):
        source.write_text(source.read_text().replace('Back to review packet</a>', 'Back to review packet</a> · <a href="../contents.html">All source sections</a>'))
    blocks = []
    for i, case in enumerate(selected,1):
        options = [('','Choose after reviewing'), ('ADEQUATE','Adequate at this point'),
                   ('MISSING_PREREQUISITE','Substantive missing prerequisite'), ('ASSUMED_BACKGROUND','Reasonable prior-course assumption'),
                   ('INTENTIONAL_PREVIEW','Intentional preview / informal introduction'), ('MATHEMATICAL_ERROR','Mathematical error'),
                   ('UNCERTAIN','Cannot judge / source or extraction problem')]
        select = ''.join(f'<option value="{value}">{text}</option>' for value,text in options)
        blocks.append(f'<details class="case" data-id="{html.escape(case["id"])}"><summary>{i}. Chapter {case["chapter"]}: {html.escape(case["module_title"])} — {html.escape(case["title"] or case["kind"])}</summary><div class="target">{snippets[case["id"]]}</div><p><a target="_blank" href="source/{case["module_id"]}.html#{html.escape(case["anchor"])}">Read the full source section</a> · Source position {case["position"]}</p><label>Judgment <select>{select}</select></label><br><label>Reason and evidence (prerequisite, earlier section, or assumed background)<textarea></textarea></label></details>')
    page = f'<!doctype html><html lang="en"><meta charset="utf-8"><title>MathemaTest faculty review</title><style>{style}</style><body><h1>Independent curriculum review</h1><header><p>{len(selected)} development examples from OpenStax Calculus Volume 1. This is a stratified development sample, not a prevalence estimate or held-out test. No model predictions are shown.</p><p>Assess each statement at its original place in the book. Consult the source section and earlier material. Distinguish reasonable assumed knowledge and intentional previews from substantive omissions. Do not require research-level foundations for every introductory result. Choose “Cannot judge” for missing images or unclear extraction. Work independently; discuss disagreements only after both reviews are exported.</p><p>Source revision: {REVISION}. <a href="https://openstax.org/details/books/calculus-volume-1">Download for free at OpenStax</a>. Textbook excerpts and adapted source pages: CC BY-NC-SA 4.0.</p><label>Reviewer code (no personal details needed): <input id="reviewer" placeholder="Reviewer A"></label><p>Nothing is uploaded. Export your work before closing; this page does not autosave. Partial exports are allowed.</p><button id="export">Export review JSON</button><span id="progress"></span></header>' + ''.join(blocks)
    page += '''<script>
const cases=[...document.querySelectorAll('.case')];
document.addEventListener('change',()=>{document.getElementById('progress').textContent=' '+cases.filter(c=>c.querySelector('select').value).length+'/'+cases.length+' labeled';});
document.getElementById('export').onclick=()=>{
 const reviewer=document.getElementById('reviewer').value.trim();
 if(!reviewer){alert('Enter a reviewer code first.');return;}
 const result={reviewer,exported_at:new Date().toISOString(),purpose:'Independent development annotations',labels:cases.map(c=>({id:c.dataset.id,label:c.querySelector('select').value||null,reason:c.querySelector('textarea').value}))};
 const url=URL.createObjectURL(new Blob([JSON.stringify(result,null,2)],{type:'application/json'}));
 const a=document.createElement('a');a.href=url;a.download='mathematest-review.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
</script></body></html>'''
    page = page.replace('<h1>Independent curriculum review</h1>', '<h1>Independent curriculum review</h1><p><a href="contents.html">Browse all source sections in textbook order</a></p>')
    provenance = {'source_revision': REVISION, 'source_corpus_sha256': hashlib.sha256((DEST/'corpus.jsonl').read_bytes()).hexdigest()}
    page = page.replace('const result={reviewer,', 'const result={...'+json.dumps(provenance)+',reviewer,')
    (OUT/'review.html').write_text(page)
    (OUT/'cases.json').write_text(json.dumps(selected,indent=2,ensure_ascii=False)+'\n')
    manifest={'source_revision':REVISION,'seed':42,'selection':'up to 10 definitions/theorem notes per chapter; excludes unsupported math and embedded media',
              'count':len(selected),'by_chapter':dict(Counter(r['chapter'] for r in selected)),
              'source_corpus_sha256':hashlib.sha256((DEST/'corpus.jsonl').read_bytes()).hexdigest(),
              'case_ids':[r['id'] for r in selected],'role':'DEVELOPMENT ONLY; reserve disjoint passages for final evaluation'}
    (OUT/'manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
    print(json.dumps(manifest,indent=2))


if __name__=='__main__':
    main()
