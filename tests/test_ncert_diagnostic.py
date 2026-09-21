import copy
import json

import pytest

from scripts.run_ncert_diagnostic import assess, locate, validate_payload


def payload():
    return {'case_id': 'case', 'task_scope': 'selected', 'target': 'question',
            'target_position': 100, 'source_id': 'source',
            'background': [{'id': 'b', 'text': 'algebra'}],
            'context': [{'id': 'c', 'source_id': 'source', 'text': 'rule',
                         'pdf_page': 1, 'printed_page': 1, 'section': '1',
                         'pdf_page_end': 1, 'printed_page_end': 1,
                         'start_offset': 0, 'end_offset': 100}]}


def test_payload_rejects_future_and_reviewer_fields():
    original = payload()
    validate_payload(original)
    changed = copy.deepcopy(original)
    changed['context'][0]['end_offset'] = 101
    with pytest.raises(ValueError, match='future'):
        validate_payload(changed)
    changed = copy.deepcopy(original)
    changed['reviewer_notes'] = 'answer'
    with pytest.raises(ValueError, match='Unexpected'):
        validate_payload(changed)
    changed = copy.deepcopy(original)
    changed['context'][0]['solution'] = 'answer'
    with pytest.raises(ValueError, match='Unexpected'):
        validate_payload(changed)


def test_anchors_require_unambiguous_ordered_source_spans():
    assert locate('before START rule END after', 'START', 'END') == (7, 21)
    with pytest.raises(ValueError):
        locate('START START END', 'START', 'END')
    with pytest.raises(ValueError):
        locate('END before START', 'START', 'END')


def test_citations_checked_separately_from_schema_and_truth():
    result = {'prerequisites': [{'name': 'rule', 'support': 'context',
              'evidence_ids': ['b', 'invented'], 'rationale': 'claimed support'}],
              'assumptions': [], 'outcome': 'attempted', 'answer': 'wrong answer',
              'reasoning': 'wrong reasoning can still satisfy a schema', 'unresolved': []}
    parsed, checks = assess(json.dumps(result), payload())
    assert parsed['answer'] == 'wrong answer'
    assert checks['citation_count'] == 2 and checks['in_bounds_citations'] == 1
    assert checks['consistency_issues']
    assert 'correct' not in checks
