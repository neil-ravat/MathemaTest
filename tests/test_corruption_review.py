from scripts.prepare_corruption_review import cases, blinded


def test_corruption_matrix_and_blind_packet_separation():
    rows=cases();packet,key=blinded(rows)
    assert len(rows)==len(packet)==len(key)==8
    for family in {'work','lens'}:
        group=[r for r in rows if r['family']==family]
        assert {r['operator'] for r in group}=={'clean','missing_rule','damaged_symbol','wrong_unit'}
        clean=next(r for r in group if r['operator']=='clean')
        for r in group:
            assert r['question']==clean['question'] if r['operator']!='wrong_unit' else r['source']==clean['source']
    assert all(set(r)=={'id','question','source','background'} for r in packet)
    assert set(key.values())=={r['id'] for r in rows}
    assert blinded(rows)==(packet,key)
