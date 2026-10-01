"""Build prediction-blind development materials; never manufacture expert labels."""
import hashlib
import html
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'data/ncert10_pilot_v1'
OUT = ROOT / 'artifacts/ncert_expert_review_v1'


def write_frozen(path, text):
    encoded = text.encode()
    if path.exists() and path.read_bytes() != encoded:
        raise ValueError(f'Refusing to overwrite changed review material: {path}')
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)


def main():
    candidates = json.loads((SOURCE / 'candidates.json').read_text())
    manifest = json.loads((SOURCE / 'manifest.json').read_text())
    cases, sections = [], []
    for index, c in enumerate(candidates, 1):
        source_id = c['source_id']
        raw = (SOURCE / 'raw' / f'{source_id}.txt').read_text()
        assert hashlib.sha256(raw.encode()).hexdigest() == c['source_text_sha256']
        assert hashlib.sha256((SOURCE / 'raw' / f'{source_id}.pdf').read_bytes()).hexdigest() == c['source_pdf_sha256']
        assert raw[c['target_start_offset']:c['target_end_offset']] == c['target_raw']
        blind_id = f'DEV-{index:02d}'
        prefix_file = f'prefixes/{blind_id}.txt'
        write_frozen(OUT / prefix_file, raw[:c['target_start_offset']])
        case = {
            'case_id': blind_id, 'source_id': source_id,
            'pdf_page': c['pdf_page'], 'printed_page': c['printed_page'],
            'source_pdf_sha256': c['source_pdf_sha256'],
            'source_text_sha256': c['source_text_sha256'],
            'target_start_offset': c['target_start_offset'],
            'target_end_offset': c['target_end_offset'],
            'target_raw': c['target_raw'], 'earlier_context_file': prefix_file,
            'context_complete_for_curriculum': False,
            'source_pdf': f'../../data/ncert10_pilot_v1/raw/{source_id}.pdf',
        }
        cases.append(case)
        sections.append(f'''<section><h2>{blind_id} — {html.escape(source_id)}, printed page {c['printed_page']}</h2>
<pre>{html.escape(c['target_raw'])}</pre><p><a href="{case['source_pdf']}#page={c['pdf_page']}">Original PDF, page {c['pdf_page']}</a> · <a href="{prefix_file}">Earlier chapter text only</a></p>
<p>Target begins at character {c['target_start_offset']}. Inspect the PDF for formulas and diagrams. Record your own transcription and answer before consulting the printed solution. Record any prior familiarity or solution consultation. Missing material in this prefix is not proof of a textbook gap.</p></section>''')
    blank_labels = [{
        'case_id': c['case_id'], 'transcription_verified': None, 'corrected_question': None,
        'prior_familiarity': None, 'printed_solution_consulted': None,
        'answer': None, 'answer_unit': None, 'derivation': None,
        'answer_tolerance': None, 'required_background': [],
        'prerequisites': [], 'supporting_passages': [],
        'curricular_judgment': None, 'rationale': None, 'confidence': None,
        'unresolved_source_issues': [],
    } for c in cases]
    for reviewer in ('A', 'B'):
        form = {'reviewer_code': reviewer, 'qualification_and_subject': None,
                'completed_at': None, 'independent_before_discussion': None,
                'status': 'UNLABELED_DEVELOPMENT', 'labels': blank_labels}
        write_frozen(OUT / f'reviewer_{reviewer}_blank.json', json.dumps(form, indent=2) + '\n')
    write_frozen(OUT / 'cases.json', json.dumps(cases, indent=2, ensure_ascii=False) + '\n')
    style = 'body{max-width:950px;margin:40px auto;padding:0 20px;font:17px/1.6 system-ui}pre{white-space:pre-wrap;background:#f3f5f7;padding:15px}section{border-top:1px solid #ccc;margin-top:30px}a{color:#075e83}'
    page = f'''<!doctype html><html lang="en"><meta charset="utf-8"><title>NCERT independent development review</title><style>{style}</style><body><h1>Independent NCERT development review</h1><p>Twelve previously inspected development cases. This packet hides model predictions and AI reviewer notes; it is not a fresh held-out test. Raw extraction may be damaged. Original sources remain local and retain NCERT copyright.</p><p>Read <a href="../../../docs/ncert_expert_review_rubric.md">the review rubric</a>. Save a separate completed copy of <a href="reviewer_A_blank.json">reviewer A</a> or <a href="reviewer_B_blank.json">reviewer B</a>. This page does not collect, save or upload annotations. Do not discuss case judgments until both reviews are locked.</p>''' + ''.join(sections) + '</body></html>\n'
    # OUT lives two levels below the repository root.
    page = page.replace('../../../docs/', '../../docs/')
    write_frozen(OUT / 'review.html', page)
    packet_manifest = {
        'role': 'PREDICTION_BLIND_DEVELOPMENT_ONLY', 'count': len(cases),
        'expert_labels_completed': 0, 'ground_truth_status': 'AWAITING_INDEPENDENT_HUMANS',
        'source_manifest_sha256': hashlib.sha256((SOURCE / 'manifest.json').read_bytes()).hexdigest(),
        'source_candidates_sha256': hashlib.sha256((SOURCE / 'candidates.json').read_bytes()).hexdigest(),
        'omitted_fields': ['target_reviewed', 'reviewer_notes', 'prerequisite_label', 'model_predictions', 'reference_answers'],
        'files': {str(p.relative_to(OUT)): hashlib.sha256(p.read_bytes()).hexdigest()
                  for p in sorted([OUT / 'cases.json', OUT / 'review.html', OUT / 'reviewer_A_blank.json', OUT / 'reviewer_B_blank.json', *[OUT / c['earlier_context_file'] for c in cases]])},
    }
    write_frozen(OUT / 'manifest.json', json.dumps(packet_manifest, indent=2) + '\n')
    assert len(cases) == 12 and all(x['answer'] is None for x in blank_labels)
    assert not {'target_reviewed', 'reviewer_notes', 'prerequisite_label'} & set().union(*(c.keys() for c in cases))
    print(f'Prepared {len(cases)} unlabeled development cases at {OUT}')


if __name__ == '__main__':
    main()
