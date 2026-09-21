from scripts.prepare_ncert_fresh_feasibility import select


def test_first_two_prefixes_exclude_own_solution_and_future():
    text = 'Earlier material.\nExample 1 : Q1\nSolution : SECRET1\n\fExample 2\nQ2\nSolution\nSECRET2\nExample 3 : Q3\nSolution SECRET3'
    rows, rejected = select(text, 'new')
    assert not rejected and len(rows) == 2
    assert rows[0]['target_raw'] == 'Example 1 : Q1\n'
    assert rows[1]['target_raw'] == 'Example 2\nQ2\n'
    assert rows[1]['pdf_page'] == 2
    for row in rows:
        assert 'SECRET' not in row['target_raw']
        assert row['earlier_context_end'] == row['target_start_offset']


def test_missing_solution_is_recorded_not_invented():
    rows, rejected = select('Example 1 : no solution\nExample 2 : valid\nSolution : x', 'new')
    assert len(rows) == 1 and rows[0]['example'] == '2'
    assert rejected == [{'example': '1', 'reason': 'NO_BOUNDED_SOLUTION_MARKER'}]
