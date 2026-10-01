from scripts.run_book_pilot import stratify, target_context


def test_chapter_selection_retains_flagged_cases_and_is_repeatable():
    rows=[dict(target={'chapter':chapter,'id':f'{chapter}-{i}'},input_issues=['flag']) for chapter in range(1,7) for i in range(20)]
    chosen=stratify(rows,100)
    assert len(chosen)==100 and chosen==stratify(rows,100)
    assert {r['target']['chapter'] for r in chosen}==set(range(1,7))
    assert all(r['input_issues'] for r in chosen)
    assert len({r['target']['id'] for r in chosen})==100


def test_shared_task_instruction_and_table_are_not_lost(tmp_path):
    module=tmp_path/'source/modules/m';module.mkdir(parents=True)
    (module/'index.cnxml').write_text('<document xmlns="http://cnx.rice.edu/cnxml"><section><para id="p">Compare these values.</para><exercise id="e"><table><row>1 2</row></table></exercise></section></document>')
    rows=[dict(id='m:p',module_id='m',anchor='p',kind='para',content='Compare these values.'),dict(id='m:e',module_id='m',anchor='e',kind='exercise',content='1 2')]
    result=target_context(rows,tmp_path)[0]
    assert result['target']['content']=='Compare these values.\n\n1 2'
    assert result['original_content']=='1 2' and rows[1]['content']=='1 2'
    assert result['input_issues']==['Table layout needs review']


def test_continuation_preserves_parent_and_retries_errors(tmp_path,monkeypatch):
    import json
    from scripts import run_book_pilot as runner
    corpus=tmp_path/'corpus';corpus.write_text('data')
    monkeypatch.setattr(runner,'CORPUS',corpus)
    monkeypatch.setattr(runner,'freeze_sources',lambda run:{'revision':'new'})
    parent=tmp_path/'parent';parent.mkdir()
    runner.save(parent/'manifest.json',{'corpus_sha256':runner.digest(corpus),'selection':[1,2,3],'planned':3})
    for i,(status,finished) in enumerate([('REVIEW_REQUIRED',True),('ERROR',True),('INTERRUPTED',False)],1):
        runner.save(parent/f'case-{i:03}.json',{'status':status,'_finished':finished})
    original={p.name:p.read_bytes() for p in parent.iterdir()}
    child=runner.continue_run(parent,tmp_path/'child')
    assert (child/'case-001.json').exists() and not (child/'case-002.json').exists()
    assert not (child/'case-003.json').exists()
    assert {p.name:p.read_bytes() for p in parent.iterdir()}==original
    manifest=json.loads((child/'manifest.json').read_text())
    assert manifest['selection']==[1,2,3] and len(manifest['inherited_results'])==1
    assert manifest['parent_manifest_sha256']==runner.digest(parent/'manifest.json')


def test_explicit_question_does_not_inherit_earlier_group_task(tmp_path):
    module=tmp_path/'source/modules/m';module.mkdir(parents=True)
    (module/'index.cnxml').write_text('<document xmlns="http://cnx.rice.edu/cnxml"><section><para id="p">Find second derivatives.</para><exercise id="e"><problem>Find constants from the initial position.</problem></exercise></section></document>')
    rows=[dict(id='m:p',module_id='m',anchor='p',kind='para',content='Find second derivatives.'),dict(id='m:e',module_id='m',anchor='e',kind='exercise',content='Find constants from the initial position.')]
    result=target_context(rows,tmp_path)[0]
    assert result['target']['content']==rows[1]['content'] and 'shared_context_id' not in result['target']


def test_shared_expression_list_is_preserved_without_previous_answers(tmp_path):
    module=tmp_path/'source/modules/m';module.mkdir(parents=True)
    (module/'index.cnxml').write_text('''<document xmlns="http://cnx.rice.edu/cnxml"
        xmlns:m="http://www.w3.org/1998/Math/MathML"><section>
        <para id="p">Interpret these two expressions.</para>
        <list id="l"><item><m:math><m:mi>A</m:mi></m:math></item>
        <item><m:math><m:mi>B</m:mi></m:math></item></list>
        <exercise id="earlier"><problem>Earlier task.</problem><solution>SECRET ANSWER</solution></exercise>
        <exercise id="e"><problem>Population at time t.</problem></exercise>
        </section></document>''')
    rows=[dict(id='m:p',module_id='m',anchor='p',kind='para',content='Interpret these two expressions.'),
          dict(id='m:e',module_id='m',anchor='e',kind='exercise',content='Population at time t.')]
    result=target_context(rows,tmp_path)[0]
    assert result['target']['content']=='Interpret these two expressions.\n\nA\nB\n\nPopulation at time t.'
    assert result['target']['shared_context_blocks'][0]['id']=='m:l'
    assert len(result['target']['shared_context_blocks'][0]['xml_sha256'])==64
    assert result['input_issues']==[] and 'SECRET' not in result['target']['content']


def test_nested_checkpoint_and_linked_graph_are_tagged(tmp_path):
    from scripts.prepare_context_corpus import source_metadata
    p=tmp_path/'source.cnxml';p.write_text('<document xmlns="http://cnx.rice.edu/cnxml"><note id="n"><exercise id="e"><solution>answer</solution></exercise></note><para id="p">See <link target-id="f"/></para><figure id="f"><media/></figure></document>')
    metadata=source_metadata(p)
    assert metadata['n']['contains_exercise_content']
    assert metadata['p']['requires_external_media']


def test_group_request_and_separate_definitions_are_both_retained(tmp_path):
    module=tmp_path/'source/modules/m';module.mkdir(parents=True)
    (module/'index.cnxml').write_text('''<document xmlns="http://cnx.rice.edu/cnxml"><section>
      <para id="old">Find derivatives.</para>
      <exercise id="earlier"><problem>Old task</problem><solution>SECRET ANSWER</solution></exercise>
      <para id="request">State the domain and range of each listed function.</para>
      <para id="definitions">p(x)=1/(x+7), q(x)=x+2</para>
      <exercise id="e"><problem>p</problem></exercise>
    </section></document>''')
    rows=[dict(id='m:'+anchor,module_id='m',anchor=anchor,kind=kind,content=text)
          for anchor,kind,text in [('old','para','Find derivatives.'),
              ('request','para','State the domain and range of each listed function.'),
              ('definitions','para','p(x)=1/(x+7), q(x)=x+2'),('e','exercise','p')]]
    result=target_context(rows,tmp_path)[0]
    assert result['target']['content']=='State the domain and range of each listed function.\n\np(x)=1/(x+7), q(x)=x+2\n\np'
    assert result['target']['shared_context_id']=='m:request'
    assert result['target']['shared_context_blocks'][0]['id']=='m:definitions'
    assert result['input_issues']==[] and rows[-1]['content']=='p'


def test_paragraphs_inside_examples_and_solutions_remain_ineligible(tmp_path):
    from scripts.prepare_context_corpus import source_metadata
    from src.verification.curriculum_audit import eligible_records
    source=tmp_path/'source.cnxml'
    source.write_text('<document><example id="example"><para id="hint">Hidden answer</para>'
                      '<solution id="solution"><para id="answer">42</para></solution></example>'
                      '<para id="lesson">Ordinary lesson</para></document>')
    meta=source_metadata(source)
    rows=[dict(id=k,content=k,source_id='book',position=i,**meta[k])
          for i,k in enumerate(['hint','answer','lesson'])]
    assert [r['id'] for r in eligible_records(rows,dict(source_id='book',position=5))]==['lesson']
