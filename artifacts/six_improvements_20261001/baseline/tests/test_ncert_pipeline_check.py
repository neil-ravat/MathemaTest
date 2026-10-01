from scripts.check_ncert_pipeline import source_violation


def test_leakage_oracle_checks_source_and_entire_span():
    case = {'source_id': 'math', 'target_start_offset': 100}
    assert source_violation({'source_id': 'math', 'end_offset': 100}, case) is None
    assert source_violation({'source_id': 'math', 'end_offset': 101}, case) == 'target_or_later_material'
    assert source_violation({'source_id': 'physics', 'end_offset': 1}, case) == 'different_source'
    assert source_violation({'source_id': 'math'}, case) == 'target_or_later_material'
