"""Ensure reviewer materials remain prediction-blind and immutable."""
import json
import pytest
from scripts import prepare_ncert_review_packet as packet


def test_packet_blinding_and_prefix_boundaries(tmp_path, monkeypatch):
    if not (packet.SOURCE / 'candidates.json').exists():
        pytest.skip('Local development inputs required')
    candidates = json.loads((packet.SOURCE / 'candidates.json').read_text())
    if any(not (packet.SOURCE / 'raw' / f"{c['source_id']}.pdf").exists() for c in candidates):
        pytest.skip('Original textbook PDFs are not distributed with the code release')
    monkeypatch.setattr(packet, 'OUT', tmp_path)
    packet.main()
    cases = json.loads((tmp_path / 'cases.json').read_text())
    assert len(cases) == 12
    for c in cases:
        assert not {'target_reviewed', 'reviewer_notes', 'prerequisite_label', 'answer'} & c.keys()
        prefix = (tmp_path / c['earlier_context_file']).read_text()
        assert len(prefix) == c['target_start_offset']
    for reviewer in 'AB':
        form = json.loads((tmp_path / f'reviewer_{reviewer}_blank.json').read_text())
        assert all(row['answer'] is None and row['curricular_judgment'] is None for row in form['labels'])
    before = (tmp_path / 'manifest.json').read_bytes()
    # Reviewer submissions must not change the reproducible blank-packet manifest.
    (tmp_path / 'reviewer_A_ai.json').write_text('{}')
    packet.main()
    assert (tmp_path / 'manifest.json').read_bytes() == before


def test_frozen_writer_rejects_changes(tmp_path):
    path = tmp_path / 'blank.json'
    packet.write_frozen(path, 'first')
    packet.write_frozen(path, 'first')
    with pytest.raises(ValueError, match='Refusing'):
        packet.write_frozen(path, 'different')
    assert path.read_text() == 'first'
