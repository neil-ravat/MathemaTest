"""Select source-ordered fresh questions without displaying answers or evaluating models."""
import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'data/ncert_fresh_reservation_v1'
EXAMPLE = re.compile(r'(?:^|(?<=\f))[ \t]*Example[ \t]+(\d+(?:\.\d+)?)[ \t]*[:.]?[ \t]*', re.M)
SOLUTION = re.compile(r'(?:^|(?<=\f))[ \t]*Solution[ \t]*:?[ \t]*', re.M)


def sha(b):
    return hashlib.sha256(b).hexdigest()


def frozen(path, b):
    if path.exists() and path.read_bytes() != b:
        raise ValueError(f'Refusing changed frozen file {path}')
    path.write_bytes(b)


def select(text, source_id):
    matches = list(EXAMPLE.finditer(text))
    result, rejected, seen = [], [], set()
    for index, match in enumerate(matches):
        if match.group(1) in seen:
            continue
        seen.add(match.group(1))
        boundary = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        solution = SOLUTION.search(text, match.end(), boundary)
        if solution is None or solution.start() - match.start() > 8000:
            rejected.append({'example': match.group(1), 'reason': 'NO_BOUNDED_SOLUTION_MARKER'})
            continue
        start, end = match.start(), solution.start()
        result.append({'id': f'{source_id}:example-{match.group(1)}', 'source_id': source_id,
                       'example': match.group(1), 'pdf_page': text[:start].count('\f') + 1,
                       'target_start_offset': start, 'target_end_offset': end,
                       'target_raw': text[start:end], 'earlier_context_file': f'raw/{source_id}.txt',
                       'earlier_context_start': 0, 'earlier_context_end': start,
                       'transcription_qa': 'NOT_REVIEWED', 'reference_status': 'UNREVIEWED',
                       'context_complete_for_curriculum': False})
        if len(result) == 2:
            break
    return result, rejected


def main():
    reservation = json.loads((DEST / 'reservation.json').read_text())
    candidates, inventory = [], []
    for sid in reservation['source_ids']:
        pdf = DEST / 'raw' / f'{sid}.pdf'
        if not pdf.exists():
            inventory.append({'source_id': sid, 'status': 'SOURCE_DOWNLOAD_FAILED', 'selected': 0})
            continue
        text = subprocess.run(['pdftotext', '-layout', str(pdf), '-'], check=True, capture_output=True).stdout.decode()
        frozen(DEST / 'raw' / f'{sid}.txt', text.encode())
        selected, rejected = select(text, sid)
        for c in selected:
            c.update(source_pdf_sha256=sha(pdf.read_bytes()), source_text_sha256=sha(text.encode()))
        candidates.extend(selected)
        inventory.append({'source_id': sid, 'selected': len(selected), 'boundary_failures': rejected})
    frozen(DEST / 'fresh_candidates.json', (json.dumps(candidates, indent=2, ensure_ascii=False) + '\n').encode())
    report = {'status': 'FRESH_INPUT_SELECTION_LOCK_ONLY', 'selected_count': len(candidates), 'selected_ids': [c['id'] for c in candidates],
              'inventory': inventory, 'model_calls': 0, 'reference_reviews': 0,
              'hashes': {str(p.relative_to(ROOT)): sha(p.read_bytes()) for p in [DEST / 'reservation.json', DEST / 'fresh_candidates.json', ROOT / 'docs/ncert_fresh_feasibility_amendment_v1.md', Path(__file__)]},
              'limitations': ['Unreviewed native formula extraction', 'Convenience first-two selection', 'Chapter prefix is not full curriculum', 'No expert gold', 'Not proof of pretraining novelty']}
    frozen(DEST / 'fresh_selection_lock.json', (json.dumps(report, indent=2) + '\n').encode())
    print(json.dumps({'selected_count': len(candidates), 'inventory': inventory}))


if __name__ == '__main__':
    main()
