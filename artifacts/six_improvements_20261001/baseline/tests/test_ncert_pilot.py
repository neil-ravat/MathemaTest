"""Chapter order and question/solution boundaries must survive PDF text extraction."""
import pytest

from scripts.prepare_ncert_pilot import freeze, locate_target


def test_example_boundary_keeps_solution_and_future_out_of_context():
    text = 'Prior definition.\n\fEarlier example solution.\n Example 11.1\nQuestion?\n Solution\nANSWER\nExample 11.2\nLater\nSolution\n'
    start, end = locate_target(text, '11.1')
    assert text[:start] == 'Prior definition.\n\fEarlier example solution.\n'
    assert 'Question?' in text[start:end] and 'ANSWER' not in text[:end]
    assert '11.2' not in text[:end]
    with pytest.raises(ValueError, match='one example'):
        locate_target(text, '11')
    with pytest.raises(ValueError, match='one example'):
        locate_target(text+text, '11.1')
    page_start = 'Previous page\f   Example 11.4\nQuestion?\nSolution\nAnswer'
    start, end = locate_target(page_start, '11.4')
    assert page_start[:start].endswith('\f') and 'Answer' not in page_start[:end]


def test_freeze_preserves_prepared_sources(tmp_path):
    path = tmp_path/'source'
    freeze(path, b'original'); freeze(path, b'original')
    with pytest.raises(ValueError, match='overwrite'):
        freeze(path, b'different')
    assert path.read_bytes() == b'original'
