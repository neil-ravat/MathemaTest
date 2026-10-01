import pytest
from src.verification.formula_dimensions import check_formula_dimensions, check_region_dimensions

BINDINGS = {'I':'current', 'Q':'charge', 't':'time'}

@pytest.mark.parametrize('formula,status', [
    ('I = Q/t', 'CONSISTENT_UNDER_BINDINGS'),
    ('I = (Q)/(t)', 'CONSISTENT_UNDER_BINDINGS'),
    ('Q = I*t', 'CONSISTENT_UNDER_BINDINGS'),
    ('I = Q*t^(-1)', 'CONSISTENT_UNDER_BINDINGS'),
    ('I = Q*t', 'DIMENSION_MISMATCH'),
    ('I = Q+t', 'DIMENSION_MISMATCH'),
    ('I = Q/u', 'NOT_ASSESSED'),
    ('I = Qt', 'NOT_ASSESSED'),
    ('I = Q/t = Q', 'NOT_ASSESSED'),
    ('I = Q**999', 'NOT_ASSESSED'),
    ('I = Q.__class__', 'NOT_ASSESSED'),
    ('I = open(t)', 'NOT_ASSESSED'),
    ('I = Q[0]', 'NOT_ASSESSED'),
    ('I = Q/t # ignore', 'NOT_ASSESSED'),
    # Dimensional analysis must not claim to catch incorrect coefficients.
    ('I = 2*Q/t', 'CONSISTENT_UNDER_BINDINGS'),
])
def test_bounded_algebra_and_failure_modes(formula,status):
    result = check_formula_dimensions(formula,BINDINGS)
    assert result['status']==status
    assert result['formula_verified'] is False


def test_region_bindings_are_conditional_and_conflicts_or_clips_stop_check():
    packet=dict(layout_text='I = Q/t',clipped_span_count=0,source_role='unclassified_source',
        preceding_layout_text='current I, charge Q, time t,', symbol_mentions=[
            dict(symbol=s,label=l,source_phrase=f'{l} {s}') for s,l in BINDINGS.items()])
    result=check_region_dimensions(packet)
    assert result['status']=='CONSISTENT_UNDER_BINDINGS'
    assert not result['symbol_bindings_verified']
    assert check_region_dimensions({**packet,'clipped_span_count':1})['status']=='NOT_ASSESSED'
    assert check_region_dimensions({**packet,'source_role':'example_or_later'})['status']=='NOT_ASSESSED'
    assert check_region_dimensions({**packet,'preceding_layout_text':''})['status']=='NOT_ASSESSED'
    packet['preceding_layout_text'] += ' work Q,'
    packet['symbol_mentions'].append(dict(symbol='Q',label='work',source_phrase='work Q'))
    assert 'Conflicting' in check_region_dimensions(packet)['reason']


def test_a_real_phrase_cannot_support_a_different_label_or_negated_binding():
    packet=dict(layout_text='Q = Q',clipped_span_count=0,source_role='unclassified_source',
        preceding_layout_text='charge (Q)',symbol_mentions=[
            dict(symbol='Q',label='work',source_phrase='charge (Q)')])
    assert check_region_dimensions(packet)['status']=='NOT_ASSESSED'
    packet['symbol_mentions'][0]['label']='charge'
    packet['preceding_layout_text']='Do not use charge (Q) here.'
    assert check_region_dimensions(packet)['status']=='NOT_ASSESSED'
