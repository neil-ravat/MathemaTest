"""Prepare AI reference review only after the declared prediction lock exists.

No model outputs are opened or included. Only source questions/prefixes and blank
annotations are copied. The lock is an attestation; its referenced prediction files
must be frozen and verified by the caller before invoking this script.
"""
import argparse
import hashlib
import html
import json
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.prepare_ncert_review_packet import write_frozen


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build(cases_file, output, prediction_lock):
    lock = json.loads(prediction_lock.read_text())
    if lock.get('predictions_frozen') is not True:
        raise ValueError('Review packets require an explicit completed prediction lock')
    if lock.get('cases_sha256') != digest(cases_file):
        raise ValueError('Prediction lock does not match candidate inputs')
    candidates = json.loads(cases_file.read_text())
    cases, sections, blanks = [], [], []
    for number, row in enumerate(candidates, 1):
        sid = row['source_id']
        if not isinstance(sid, str) or not re.fullmatch(r'[A-Za-z0-9_-]+', sid):
            raise ValueError('Invalid source identifier')
        source = cases_file.parent / 'raw' / f'{sid}.txt'
        pdf = source.with_suffix('.pdf')
        if digest(source) != row['source_text_sha256'] or digest(pdf) != row['source_pdf_sha256']:
            raise ValueError('Pinned source hash mismatch')
        text = source.read_text()
        start, end = row['target_start_offset'], row['target_end_offset']
        if type(start) is not int or type(end) is not int or not 0 <= start < end <= len(text):
            raise ValueError('Invalid target bounds')
        if text[start:end] != row['target_raw']:
            raise ValueError('Question differs from pinned source')
        case_id = f'FRESH-{number:02d}'
        prefix = f'prefixes/{case_id}.txt'
        write_frozen(output / prefix, text[:start])
        case = {k: row[k] for k in ('source_id', 'pdf_page', 'source_pdf_sha256', 'source_text_sha256',
                                    'target_start_offset', 'target_end_offset', 'target_raw')}
        case.update(case_id=case_id, original_case_id=row['id'], earlier_context_file=prefix,
                    source_pdf=os.path.relpath(pdf, output), context_complete_for_curriculum=False)
        cases.append(case)
        blanks.append(dict(case_id=case_id, original_case_id=row['id'], answer=None, answer_unit=None,
                           derivation=None, printed_solution_consulted=None, transcription_verified=None,
                           corrected_question=None, answer_tolerance=None, prerequisites=[],
                           supporting_passages=[], assumptions=[], curricular_judgment=None,
                           unresolved_source_issues=[], rationale=None))
        sections.append(f'<section><h2>{case_id}</h2><pre>{html.escape(row["target_raw"])}</pre>'
                        f'<p><a href="{html.escape(case["source_pdf"])}#page={row["pdf_page"]}">Original PDF</a> · '
                        f'<a href="{prefix}">Earlier prefix</a></p></section>')
    write_frozen(output / 'cases.json', json.dumps(cases, indent=2, ensure_ascii=False) + '\n')
    for reviewer in 'AB':
        write_frozen(output / f'reviewer_{reviewer}_blank.json', json.dumps(dict(
            reviewer=reviewer, status='UNREVIEWED_AI_REFERENCE_NOT_EXPERT_GOLD',
            prior_exposure=None, completed_at=None, labels=blanks), indent=2) + '\n')
    page = '<!doctype html><html lang="en"><meta charset="utf-8"><title>Fresh AI source review</title><style>body{font:17px/1.6 system-ui;max-width:950px;margin:40px auto}pre{white-space:pre-wrap}section{border-top:1px solid #ccc}</style><h1>Fresh AI source review</h1><p>Predictions are frozen and hidden. Review source evidence independently before comparing annotations. These are AI reference judgments, not expert gold. Raw extraction may be damaged. Full-curriculum context is incomplete. Record solution consultation. Original PDFs remain local.</p>' + ''.join(sections) + '</html>\n'
    write_frozen(output / 'review.html', page)
    generated = ['cases.json', 'review.html', 'reviewer_A_blank.json', 'reviewer_B_blank.json'] + [c['earlier_context_file'] for c in cases]
    manifest = dict(status='AWAITING_SEPARATE_AI_REVIEWS', count=len(cases), expert_gold=False,
                    cases_sha256=digest(cases_file), prediction_lock_sha256=digest(prediction_lock),
                    files={f:digest(output / f) for f in generated})
    write_frozen(output / 'manifest.json', json.dumps(manifest, indent=2) + '\n')
    return len(cases)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cases-file', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, required=True)
    parser.add_argument('--prediction-lock', type=Path, required=True)
    args = parser.parse_args()
    count = build(args.cases_file.resolve(), args.output_dir.resolve(), args.prediction_lock.resolve())
    print(f'Prepared {count} prediction-blind AI review cases; no source text displayed.')
