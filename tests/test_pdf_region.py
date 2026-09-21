from pathlib import Path
import shutil

import pytest
from PIL import Image, ImageDraw

from src.ingestion.pdf_region import layout_text, recover_fractions
from src.ingestion.ingestion_engine import IngestionEngine
from src.verification.auditor_prover import AuditorProver


def span(text, x, y, width=8, height=10, font=11):
    return dict(text=text, left=x, top=y, width=width, height=height, font_size=font)


def test_superscript_requires_small_raised_adjacent_digit():
    base = span('x', 10, 20)
    power = span('2', 18, 20, 4, 6, 6)
    assert layout_text([base, power])[0] == 'x^(2)'
    assert not layout_text([base, span('2', 18, 20)])[1]
    assert not layout_text([base, span('2', 50, 20, 4, 6, 6)])[1]


def test_fraction_requires_visible_bar_not_only_stacked_tokens():
    spans = [span('Q', 10, 10), span('t', 12, 25, width=4)]
    image = Image.new('RGB', (80, 80), 'white')
    assert recover_fractions(spans, image, (0, 0, 40, 40))[1] == []
    ImageDraw.Draw(image).line((20, 44, 36, 44), fill='black', width=2)
    recovered, candidates = recover_fractions(spans, image, (0, 0, 40, 40))
    assert candidates[0]['text'] == '(Q)/(t)'
    assert len(recovered) == 1


def test_unreviewed_region_stops_before_retrieval_or_model():
    auditor = AuditorProver.__new__(AuditorProver)  # No model/retriever initialized.
    result = auditor.audit_question('flattened fraction', source_id='s', before_position=10,
                                    background='arithmetic', question_region={'layout_text': 'Q I t'})
    assert result['status'] == 'INPUT_REVIEW_REQUIRED'
    assert result['model_call_executed'] is False


@pytest.mark.skipif(not shutil.which('pdftohtml') or not shutil.which('pdftoppm'), reason='Poppler required')
def test_native_fraction_crop_roundtrip_and_invalid_bounds(tmp_path):
    pdf = Path(__file__).resolve().parents[1]/'data/ncert10_pilot_v1/raw/jesc111.pdf'
    if not pdf.exists():
        pytest.skip('Pinned development PDF required')
    result = IngestionEngine.process_pdf_region(pdf, 2, (195, 116, 232, 149), tmp_path/'fraction')
    assert result['layout_text'] == 'I = (Q)/(t)'
    assert result['clipped_span_count'] == 0 and not result['solver_ready']
    assert len(result['native_spans']) == 4
    with Image.open(result['image_path']) as image:
        assert image.size == (74, 66)
    with pytest.raises(ValueError, match='outside'):
        IngestionEngine.process_pdf_region(pdf, 2, (0, 0, 10000, 10000), tmp_path/'bad')
    with pytest.raises(FileExistsError):
        IngestionEngine.process_pdf_region(pdf, 2, (195, 116, 232, 149), tmp_path/'fraction')
