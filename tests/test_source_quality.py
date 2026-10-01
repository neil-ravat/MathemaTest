from src.ingestion.source_quality import formula_candidates, is_worked_example
from src.graph_store.graph_constructor import source_evidence_units


def test_formula_candidates_preserve_damaged_layout_and_exclude_solutions():
    text = 'Current is defined below.\n\n    Q\nI =\n    t\n\nExample 1.1\nI = 100/5\n\nSolution\nI = 20.'
    units = source_evidence_units(dict(content=text,start_offset=50,end_offset=50+len(text)))
    found = formula_candidates(units)
    assert len(found) == 1
    assert found[0]['content'] == 'Q\nI =\n    t'
    assert text[found[0]['start_offset']-50:found[0]['end_offset']-50] == found[0]['content']
    assert found[0]['formula_layout_verified'] is False
    assert found[0]['status'] == 'FORMULA_REVIEW_REQUIRED'
    assert not is_worked_example('For example, Ohm law states V = IR.')
    assert is_worked_example('  Solution:\nR = 15 ohms.')


def test_definition_cue_rejects_questions_and_negated_or_conditional_naming():
    from src.graph_store.relation_evidence import definition_witness
    assert definition_witness('resistance', 'Resistance is defined as the ratio of voltage to current.')
    assert definition_witness('electric circuit', 'A closed current path is called an electric circuit.')
    assert not definition_witness('conductor', 'Charge flows through a conductor.')
    assert not definition_witness('circuit', 'This is not called a circuit.')
    assert not definition_witness('circuit', 'If this is called a circuit')


def test_quantity_mentions_require_explicit_symbol_and_skip_examples():
    from src.ingestion.source_quality import quantity_symbol_mentions
    def u(text):return dict(content=text,evidence_id=0,start_offset=0,end_offset=len(text))
    assert quantity_symbol_mentions([u('Example 1.1\ncharge Q, time t.')])==[]
    assert quantity_symbol_mentions([u('The time taken is long and the charge flows.')])==[]
    assert quantity_symbol_mentions([u('What is the charge Q?')])==[]
    assert quantity_symbol_mentions([u('Call this charge a, for now.')])==[]
    assert quantity_symbol_mentions([u('charge Q, time t,')])[0]['symbol']=='Q'


def test_development_binding_expectations_and_exact_source_slices():
    from pathlib import Path
    from scripts.evaluate_symbol_bindings import evaluate
    result = evaluate(Path(__file__).parent/'fixtures/symbol_bindings_development.json')
    assert result['totals']['current_parser']['exact_cases'] == result['case_count']
    assert not result['expert_gold'] and not result['heldout']


def test_prose_coordination_and_inverse_labels_keep_exact_evidence():
    from src.ingestion.source_quality import quantity_symbol_mentions
    text='Potential difference V and current I. Read ammeter I, for the current and voltmeter V for the potential difference.'
    rows=quantity_symbol_mentions([dict(content=text,evidence_id=0,start_offset=0,end_offset=len(text))])
    assert {(r['symbol'],r['name']) for r in rows}=={('V','potential difference'),('I','current')}
    assert len(rows)==4
    assert all(text[r['start_offset']:r['end_offset']]==r['source_phrase'] for r in rows)
