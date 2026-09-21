import hashlib
import json
import pytest
from scripts.prepare_fresh_ai_review_packet import build


def test_prediction_lock_required_and_model_notes_not_copied(tmp_path):
    raw = tmp_path / 'raw'; raw.mkdir()
    text = 'Prior.\nExample1 Q?\nSolution SECRET'
    source = raw / 's.txt'; source.write_text(text)
    pdf = raw / 's.pdf'; pdf.write_bytes(b'%PDF-synthetic-test')
    sha = lambda p: hashlib.sha256(p.read_bytes()).hexdigest()
    start, end = text.index('Example'), text.index('Solution')
    candidate = dict(id='s:1', source_id='s', pdf_page=1, target_start_offset=start,
                     target_end_offset=end, target_raw=text[start:end],
                     source_text_sha256=sha(source), source_pdf_sha256=sha(pdf),
                     answer='SECRET', reviewer_notes='Do not copy', prediction='Do not copy')
    cases = tmp_path / 'cases.json'; cases.write_text(json.dumps([candidate]))
    lock = tmp_path / 'lock.json'; lock.write_text(json.dumps(dict(predictions_frozen=False, cases_sha256=sha(cases))))
    with pytest.raises(ValueError, match='prediction lock'):
        build(cases, tmp_path / 'out', lock)
    lock.write_text(json.dumps(dict(predictions_frozen=True, cases_sha256=sha(cases))))
    assert build(cases, tmp_path / 'out', lock) == 1
    packet = (tmp_path / 'out/cases.json').read_text()
    assert 'SECRET' not in packet and 'Do not copy' not in packet
    assert (tmp_path / 'out/prefixes/FRESH-01.txt').read_text() == 'Prior.\n'
    assert build(cases, tmp_path / 'out', lock) == 1
