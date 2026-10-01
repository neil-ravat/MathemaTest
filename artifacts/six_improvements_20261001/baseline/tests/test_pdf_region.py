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


@pytest.mark.parametrize('power', ['-3', '–3', '−3', '+3'])
def test_signed_superscripts_preserve_sign_and_require_geometry(power):
    base = span('10', 10, 20, width=12)
    raised = span(power, 22, 19, width=8, height=6, font=6)
    expected = power.replace('–', '-').replace('−', '-')
    assert layout_text([base, raised])[0] == f'10^({expected})'
    assert not layout_text([base, span(power, 22, 20)])[1]


@pytest.mark.skipif(not shutil.which('pdftohtml') or not shutil.which('pdftoppm'), reason='Poppler required')
def test_native_negative_exponent_crop(tmp_path):
    pdf = Path(__file__).resolve().parents[1]/'data/ncert10_pilot_v1/raw/jesc111.pdf'
    if not pdf.exists():
        pytest.skip('Pinned development PDF required')
    result = IngestionEngine.process_pdf_region(pdf, 2, (280, 251, 537, 266), tmp_path/'units')
    assert '10^(-3)' in result['layout_text'] and '10^(-6)' in result['layout_text']
    assert len(result['recovered_superscripts']) == 2
    assert result['clipped_span_count'] == 0
    assert result['solver_ready'] is False


def test_automatic_detector_requires_math_equality_not_prose():
    from src.ingestion.pdf_region import math_region_boxes
    assert math_region_boxes([span('This prose says x = y.',0,0,width=100)],200,200) == []
    assert math_region_boxes([span('Q',10,10),span('t',10,30)],200,200) == []


@pytest.mark.skipif(not shutil.which('pdftohtml') or not shutil.which('pdftoppm'), reason='Poppler required')
def test_automatic_math_regions_recover_fraction_symbols_and_mark_examples(tmp_path):
    pdf = Path(__file__).resolve().parents[1]/'data/ncert10_pilot_v1/raw/jesc111.pdf'
    if not pdf.exists():
        pytest.skip('Pinned development PDF required')
    result = IngestionEngine.process_pdf_math_candidates(pdf,2,tmp_path/'automatic')
    fractions = [p for p in result['candidates'] if p['layout_text']=='I = (Q)/(t)']
    assert len(fractions)==1
    packet=fractions[0]
    assert packet['clipped_span_count']==0
    assert {(m['symbol'],m['label']) for m in packet['symbol_mentions']} == {('I','current'),('Q','charge'),('t','time')}
    assert packet['source_role']=='unclassified_source'
    assert packet['dimension_check']['status']=='CONSISTENT_UNDER_BINDINGS'
    assert not packet['dimension_check']['formula_verified']
    assert any(p['source_role']=='example_or_later' for p in result['candidates'])
    assert all(not p['solver_ready'] and not p['symbol_meanings_verified'] for p in result['candidates'])
    assert any('10^(-3)' in p['layout_text'] and '10^(-6)' in p['layout_text'] for p in result['candidates'])


@pytest.mark.skipif(not shutil.which('pdftohtml') or not shutil.which('pdftoppm'), reason='Poppler required')
def test_potential_difference_binding_completes_split_definition_row(tmp_path):
    pdf = Path(__file__).resolve().parents[1]/'data/ncert10_pilot_v1/raw/jesc111.pdf'
    if not pdf.exists():
        pytest.skip('Pinned development PDF required')
    result = IngestionEngine.process_pdf_math_candidates(pdf,3,tmp_path/'voltage')
    packet = next(p for p in result['candidates'] if p['layout_text']=='V = W/Q')
    assert {(m['symbol'],m['label']) for m in packet['symbol_mentions']} == {
        ('V','potential difference'),('W','work'),('Q','charge')}
    for mention in packet['symbol_mentions']:
        assert packet['preceding_layout_text'][mention['context_start']:mention['context_end']]==mention['source_phrase']
    assert packet['dimension_check']['status']=='CONSISTENT_UNDER_BINDINGS'
    assert not packet['solver_ready'] and not packet['symbol_meanings_verified']
