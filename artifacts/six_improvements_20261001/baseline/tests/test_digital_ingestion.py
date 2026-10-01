"""Native extraction preserves evidence offsets without claiming formula fidelity."""
import hashlib
import shutil
from pathlib import Path
from subprocess import CompletedProcess

import pytest

from src.ingestion.ingestion_engine import IngestionEngine, _digital_documents


def test_offsets_pages_layout_and_safe_target_boundary():
    text = "  rho = R A / l\n    table  10−6\n\nPrior. TARGET solution\f\nNext page\f"
    target = text.index("TARGET")
    docs, pages = _digital_documents(text, "sample", 11, [target])
    assert pages == 2
    assert len({d['id'] for d in docs}) == len(docs)
    assert all(d['content'] == text[d['start_offset']:d['end_offset']] for d in docs)
    assert all(d['pdf_page'] == text.count('\f', 0, d['start_offset']) + 1 for d in docs)
    assert all(not d['formula_layout_verified'] for d in docs)
    earlier = [d for d in docs if d['end_offset'] <= target]
    assert earlier[-1]['content'] == 'Prior. '
    assert all('TARGET' not in d['content'] and 'solution' not in d['content'] for d in earlier)
    assert docs[0]['content'] == '  rho = R A / l\n    table  10−6'
    with pytest.raises(ValueError, match='boundaries'):
        _digital_documents(text, 'sample', 11, [-1])


def test_empty_native_extraction_fails(tmp_path, monkeypatch):
    pdf = tmp_path / 'image.pdf'
    pdf.write_bytes(b'%PDF-placeholder-for-mocked-extractor')
    monkeypatch.setattr('src.ingestion.ingestion_engine.subprocess.run',
                        lambda *a, **kw: CompletedProcess(a, 0, b'\n\f', b''))
    with pytest.raises(ValueError, match='no extractable native text'):
        IngestionEngine.process_digital_pdf(pdf, 'image', 1)


@pytest.mark.parametrize('source,chapter,pages', [('jemh104', 4, 11), ('jesc111', 11, 24)])
def test_pinned_pdf_matches_frozen_text(source, chapter, pages):
    raw = Path(__file__).resolve().parents[1] / 'data/ncert10_pilot_v1/raw'
    pdf = raw / f'{source}.pdf'
    if not pdf.exists() or not shutil.which('pdftotext'):
        pytest.skip('Local pinned PDF and Poppler required for smoke check')
    result = IngestionEngine.process_digital_pdf(pdf, source, chapter)
    assert result['text'] == (raw / f'{source}.txt').read_bytes().decode('utf-8')
    assert result['pdf_sha256'] == hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert result['total_pages'] == pages
    assert {d['pdf_page'] for d in result['documents']} == set(range(1, pages + 1))
    assert all(d['content'] == result['text'][d['start_offset']:d['end_offset']]
               for d in result['documents'])
