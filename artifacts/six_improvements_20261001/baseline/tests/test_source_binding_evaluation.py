import json
from pathlib import Path
import shutil
import pytest
from scripts.evaluate_symbol_bindings import evaluate


@pytest.mark.skipif(not shutil.which('pdftohtml'), reason='Poppler required')
def test_source_fixture_provenance_is_checked_before_scoring(tmp_path):
    fixture=Path(__file__).parent/'fixtures/ncert_source_bindings_development.json'
    source=Path(__file__).resolve().parents[1]/'data/ncert10_pilot_v1/raw/jesc111.pdf'
    if not source.exists(): pytest.skip('Pinned development PDF required')
    report=evaluate(fixture)
    assert report['case_count']==18 and not report['heldout'] and not report['expert_gold']
    corrupted=json.loads(fixture.read_text())
    corrupted['cases'][0]['text']='Unsupported replacement text'
    bad=tmp_path/'bad.json';bad.write_text(json.dumps(corrupted))
    with pytest.raises(ValueError,match='Source evidence mismatch'):
        evaluate(bad)
