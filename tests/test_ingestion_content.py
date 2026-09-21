"""Pipeline regressions: actual prose survives; failed blocks are never evidence."""
import shutil
from types import SimpleNamespace

import pytest
from PIL import Image, ImageDraw, ImageFont

from scripts.build_ncert_study_corpus import graph_prefix_cutoffs
from src.ingestion.ingestion_engine import IngestionEngine
from src.ingestion.layout_parser import LayoutAnalyzer
from src.models.schemas import BlockType, BoundingBox, LayoutBlock


def engine(kinds):
    blocks = [LayoutBlock(block_id=str(i), block_type=kind,
        bbox=BoundingBox(x1=0, y1=0, x2=1000, y2=180), confidence=1, page_number=1)
        for i, kind in enumerate(kinds)]
    return IngestionEngine(use_gpu=False,
        layout_analyzer=SimpleNamespace(detect_blocks=lambda **kw: blocks,
                                       crop_block=lambda image, block: LayoutAnalyzer.crop_block(None, image, block)),
        formula_extractor=SimpleNamespace(extract_latex_batch=lambda *a, **kw: ['']))


def test_failed_and_unsupported_blocks_reported_without_losing_good_prose():
    instance = engine([BlockType.TEXT, BlockType.FORMULA, BlockType.FIGURE, BlockType.TEXT])
    calls = iter(['A definition that must survive.', ValueError('unreadable crop')])
    def extract(crop):
        value = next(calls)
        if isinstance(value, Exception):
            raise value
        return value
    instance._extract_text = extract
    result = instance.process_image(Image.new('RGB', (1000, 180), 'white'))
    assert [b.raw_content for b in result.blocks] == ['A definition that must survive.']
    assert len(result.errors) == 3
    assert any('formula OCR' in e for e in result.errors)
    assert any('visual review' in e for e in result.errors)
    assert any('unreadable crop' in e for e in result.errors)


@pytest.mark.skipif(not shutil.which('tesseract'), reason='Local Tesseract required')
def test_real_text_ocr_reaches_structured_output():
    image = Image.new('RGB', (1000, 180), 'white')
    ImageDraw.Draw(image).text((30, 40), 'Electric current is charge per unit time.',
                              font=ImageFont.load_default(size=32), fill='black')
    result = engine([BlockType.TEXT]).process_image(image)
    assert not result.errors
    assert 'Electric current is charge per unit time.' == result.blocks[0].raw_content
    assert not result.blocks[0].symbolic_metadata.sympy_parseable


def test_shared_graph_cannot_see_first_target_or_solution():
    cases = [dict(id='later', source_id='jemh104', target_start_offset=90, target_end_offset=100),
             dict(id='first', source_id='jemh104', target_start_offset=20, target_end_offset=30),
             dict(id='other', source_id='jesc111', target_start_offset=0, target_end_offset=5)]
    assert graph_prefix_cutoffs(cases) == {'jemh104': 20, 'jesc111': 0}
    source = 'prior material'.ljust(20) + 'FIRST TARGET AND SOLUTION' + 'later material'
    assert source[:graph_prefix_cutoffs(cases)['jemh104']] == 'prior material'.ljust(20)
