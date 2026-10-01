"""Freeze official NCERT chapter text and source-linked, unlabeled pilot candidates.

Uses system Poppler. No inference, answer scoring, formula auto-correction, or
held-out data access. Raw PDFs remain the authoritative source for mathematics.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/ncert10_pilot_v1'
SOURCES = {
    'jemh104': ('Mathematics: Quadratic Equations', 11, 38,
                '9aca4b28ad57ae78a5e69ce67d19344c44b1390c5b8afd13db83b46ad54e8e9d'),
    'jesc111': ('Science: Electricity', 24, 171,
                '640a680a24070d4add6d580d03d5377768ee5a6b4f89f9bfb66b350d457ab52f'),
    'jemh1ps': ('Mathematics preliminaries', 14, None,
                '62867d1b27b42e110948ee1301446a15e89ed386e04bb5b29dc6e301fa679f94'),
    'jesc1ps': ('Science preliminaries', 12, None,
                'cf2a2afb28bd01b4518dbd7e9517b8a9b4a85c989bf3a047cd96d1a8408fdcb0'),
}

# AI visual transcription of the selected question only, checked against page images.
# These are not educational labels; curation notes must never enter model prompts.
SELECTION = [
    ('jemh104', '2', 3, 'Classify as quadratic after simplifying: (i) (x-2)^2+1=2*x-3; (ii) x*(x+1)+8=(x+2)*(x-2); (iii) x*(2*x+3)=x^2+1; (iv) (x+2)^3=x^3-4.',
     'Earlier Section 4.2 and prior algebraic identities; extracted superscripts need normalization.'),
    ('jemh104', '3', 5, 'Find the roots of 2*x^2-5*x+3=0 by factorisation.',
     'Section 4.3 explicitly assumes Class IX factorisation; do not call this a missing prerequisite.'),
    ('jemh104', '4', 6, 'Find the roots of 6*x^2-x-2=0.',
     'Earlier factorisation example and zero-product reasoning; fractions in solutions need visual checking.'),
    ('jemh104', '5', 6, 'Find the roots of 3*x^2-2*sqrt(6)*x+2=0.',
     'Raw extraction drops radical signs. Question normalized from image; earlier-context radical expressions remain unverified.'),
    ('jemh104', '6', 7, 'Find the dimensions of the prayer hall described in Section 4.1.',
     'Requires the earlier Section 4.1 word problem, not just adjacent paragraphs. Positive dimensions restrict admissible roots.'),
    ('jemh104', '7', 8, 'Find the discriminant of 2*x^2-4*x+3=0 and determine the nature of its roots.',
     'Use preceding Section 4.4. Its displayed quadratic formula is damaged by plain-text extraction.'),
    ('jesc111', '11.1', 2, 'A filament carries 0.5 A for 10 minutes. Find the charge passing through the circuit.',
     'Needs earlier current-charge-time relation and minute-to-second conversion; units must be retained.'),
    ('jesc111', '11.2', 3, 'Find the work done moving 2 C of charge across a potential difference of 12 V.',
     'Earlier potential-difference definition. Printed solution continues on the next page, which must not leak into input.'),
    ('jesc111', '11.3', 9, 'At 220 V, find the current drawn by (a) a bulb filament of resistance 1200 ohm and (b) a heater coil of resistance 100 ohm.',
     'Use earlier Ohm law. Printed solution cites Eq. (12.6) in part (a), versus (11.6) in part (b); editorial reference candidate, not a proven prerequisite gap.'),
    ('jesc111', '11.4', 10, 'A heater draws 4 A at 60 V. Find its current when the potential difference increases to 120 V.',
     'Requires constant resistance within the stated Ohm-law regime; teacher should assess whether the physical assumption is adequately signposted.'),
    ('jesc111', '11.5', 10, 'A 1 m metal wire has resistance 26 ohm at 20 degrees C and diameter 0.3 mm. Find its resistivity and identify the material using Table 11.2.',
     'Needs earlier resistance-resistivity relation, circle area, SI conversion, and the table. Preserve temperature, units, and table values.'),
    ('jesc111', '11.6', 10, 'A wire of length l and cross-sectional area A has resistance 4 ohm. Find resistance for the same material with length l/2 and area 2*A.',
     'Earlier resistance-resistivity relation and proportional reasoning; assume matching material conditions, subject to educational review.'),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def freeze(path, data):
    if path.exists():
        if path.read_bytes() != data:
            raise ValueError('Refusing to overwrite different frozen file: '+str(path))
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open('xb') as stream:
            stream.write(data)


def locate_target(text, label):
    starts = list(re.finditer(r'(?m)(?:^|(?<=\f))[ \t]*Example[ \t]+'+re.escape(label)+r'(?![\d.])\s*:?\s*', text))
    if len(starts) != 1:
        raise ValueError('Expected one example heading: '+label)
    start = starts[0].start()
    solution = re.search(r'(?m)^[ \t]*Solution\b\s*:?', text[starts[0].end():])
    if solution is None:
        raise ValueError('No solution boundary for '+label)
    end = starts[0].end()+solution.start()
    return start, end


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--download', action='store_true', help='Fetch missing official PDFs; hashes must match pinned edition')
    args = parser.parse_args()
    texts, page_records, sources = {}, [], {}
    for code, (title, expected_pages, first_printed, expected_hash) in SOURCES.items():
        pdf = DEST/'raw'/f'{code}.pdf'
        url = f'https://www.ncert.nic.in/textbook/pdf/{code}.pdf'
        if not pdf.exists() and args.download:
            with urlopen(url, timeout=45) as response:
                data = response.read()
            if not data.startswith(b'%PDF-') or sha(data) != expected_hash:
                raise ValueError('Official PDF differs from pinned edition: '+code)
            freeze(pdf, data)
        data = pdf.read_bytes()
        if sha(data) != expected_hash:
            raise ValueError('Source hash mismatch: '+code)
        text = subprocess.check_output(['pdftotext', '-layout', str(pdf), '-'], text=True)
        freeze(pdf.with_suffix('.txt'), text.encode())
        pages = text.split('\f')
        if not pages[-1].strip():
            pages.pop()
        if len(pages) != expected_pages or set(re.findall(r'Reprint\s+(\d{4}-\d{2})', text)) != {'2026-27'}:
            raise ValueError('Unexpected pagination or edition: '+code)
        texts[code] = text
        sources[code] = {'title': title, 'official_url': url, 'pdf_sha256': sha(data),
                         'text_sha256': sha(text.encode()), 'pdf_pages': len(pages), 'reprint': '2026-27'}
        if first_printed is not None:
            offset = 0
            for number, page in enumerate(pages, 1):
                page_records.append({'id': f'{code}:p{number}', 'source_id': code, 'pdf_page': number,
                    'printed_page': first_printed+number-1, 'start_offset': offset, 'end_offset': offset+len(page),
                    'text': page, 'formula_layout_verified': False,
                    'notice': 'Extracted text may lose radicals, superscripts, fractions, tables, or diagrams; inspect source PDF.'})
                offset += len(page)+1
    cases = []
    for code, label, page, target, note in SELECTION:
        text = texts[code]
        start, end = locate_target(text, label)
        if text[:start].count('\f')+1 != page:
            raise ValueError('Selected example moved: '+code+' '+label)
        cases.append({'id': f'{code}:example-{label}', 'source_id': code, 'example': label,
            'pdf_page': page, 'printed_page': SOURCES[code][2]+page-1,
            'source_pdf_sha256': sources[code]['pdf_sha256'], 'source_text_sha256': sources[code]['text_sha256'],
            'target_start_offset': start, 'target_end_offset': end, 'target_raw': text[start:end],
            'target_reviewed': target, 'target_visual_review': 'AI-assisted check against rendered source page; no human adjudication',
            'visual_reference': f'artifacts/ncert10_pilot_v1/visual_checks/{code}-p{page}.png',
            'earlier_chapter_context': {'source_text': f'raw/{code}.txt', 'start_offset': 0, 'end_offset': start},
            'context_complete_for_curriculum': False, 'context_formula_review_complete': False,
            'prerequisite_label': None, 'label_source': 'UNLABELED', 'reviewer_notes': note})
    outputs = {'pages.jsonl': ''.join(json.dumps(p, ensure_ascii=False)+'\n' for p in page_records),
               'candidates.json': json.dumps(cases, ensure_ascii=False, indent=2)+'\n'}
    for name, content in outputs.items():
        freeze(DEST/name, content.encode())
    version = subprocess.run(['pdftotext', '-v'], capture_output=True, text=True, check=True)
    manifest = {'purpose': 'NCERT Class 10 development candidate packet, not a labeled benchmark',
        'sources': sources, 'chapter_pages': len(page_records), 'candidate_count': len(cases),
        'files': {name: sha(content.encode()) for name, content in outputs.items()},
        'extractor': (version.stdout+version.stderr).splitlines()[0],
        'builder_sha256': sha(Path(__file__).read_bytes()), 'new_model_calls': 0,
        'rights': 'NCERT copyright; public download does not imply an open redistribution license. Source copies stay local.',
        'limitations': ['Convenience development sample; not representative defect prevalence',
            'No independent educational labels or accuracy estimate', 'Target transcriptions AI-reviewed; earlier context still needs formula and diagram QA',
            'Earlier chapter prefix excludes this target and its solution but omits prior chapters/grades',
            'Reviewer notes and labels must be excluded from future model payloads',
            'Synthetic source_guard grammar does not support these problems; do not relabel unsupported parsing as textbook gaps']}
    freeze(DEST/'manifest.json', (json.dumps(manifest, indent=2)+'\n').encode())
    print(json.dumps({'sources': len(sources), 'chapter_pages': len(page_records), 'candidates': len(cases),
                      'labels': 'unreviewed', 'new_model_calls': 0, 'manifest': str(DEST/'manifest.json')}, indent=2))


if __name__ == '__main__':
    main()
