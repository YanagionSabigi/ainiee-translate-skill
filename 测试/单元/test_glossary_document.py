import copy
import json
import pytest
from ainiee_translate import glossary_document as gd


def person():
    return dict(id='person.test', source_form=dict(text='Émile', language='fr'), latin_form=dict(text='Emile', language='fr-Latn'), chinese_translation='埃米尔', name_system='latin')


def sample():
    d = gd.empty_document()
    d['persons'] = [person()]
    d['terminology'] = [dict(id='term.test', source_form=dict(text='law', language='en'), target_template='<<person:person.test>> 定律', references=['person.test'])]
    return d


def test_empty_and_modes():
    assert gd.empty_document()['categories'] == []
    d = sample()
    for mode, expected in [('A','埃米尔'), ('B','Emile'), ('C','Émile'), ('D','Émile')]:
        r = gd.runtime_view(d, dict(schema_version='1.0.0', person_name_mode=mode))
        assert r['characters'][0]['render'] == expected
        assert r['terms'][0]['dst'] == expected + ' 定律'
    d['persons'][0]['name_system'] = 'unknown'
    assert gd.runtime_view(d)['_issues']


@pytest.mark.parametrize('change', ['reference','cycle','exclusive','unknown'])
def test_invalid_contract(change):
    d = sample()
    if change == 'reference': d['terminology'][0]['references'] = ['person.missing']
    if change == 'cycle': d['categories'] = [dict(id='x', name='X', parent_id='y'),dict(id='y', name='Y',parent_id='x')]
    if change == 'exclusive': d['terminology'][0]['target_form'] = dict(text='law', language='en')
    if change == 'unknown': d['persons'][0]['invented'] = True
    with pytest.raises(ValueError): gd.validate_document(d)


def test_policy_roundtrip_and_tampering(tmp_path):
    p = tmp_path / 'table.json'
    gd.write_document(p, sample(), dict(schema_version='1.0.0', person_name_mode='B'))
    assert gd.load_runtime(p)['characters'][0]['render'] == 'Emile'
    policy = p.with_suffix('.policy.json')
    policy.write_text('{}', encoding='utf8')
    with pytest.raises(ValueError): gd.load_runtime(p)
    policy.unlink()
    with pytest.raises(ValueError): gd.load_runtime(p)


def test_filter_closure_and_new_candidates(tmp_path):
    from ainiee_translate.glossary import filter_locked, merge_newterms
    d = sample()
    out = filter_locked(d, ['law'])
    assert out['persons'][0]['id'] == 'person.test'
    merge_newterms(out, ['candidate'])
    assert out['terminology'][-1]['source_form']['text'] == 'candidate'
    assert 'target_form' not in out['terminology'][-1]


def test_ambiguous_verification():
    from ainiee_translate.verify import check_items
    d = sample()
    p = copy.deepcopy(person()); p['id'] = 'person.other'; p['chinese_translation'] = '另一人'
    d['persons'].append(p)
    r = check_items([dict(text_index=1, translation_status=1, source_text='Émile',translated_text='埃米尔')], gd.runtime_view(d))
    assert any(x['kind'] == 'ambiguous_source' and len(x['candidate_ids']) == 2 for x in r)

def test_person_forms_are_recognition_forms():
    d = sample()
    d['persons'][0].update(source_form=dict(text='Понтрягин', language='ru'),latin_form=dict(text='Pontryagin',language='ru-Latn'),chinese_translation='庞特里亚金')
    from ainiee_translate.verify import check_items
    rows=[dict(text_index=1,translation_status=1,source_text='Pontryagin',translated_text='错误姓名')]
    assert any(x['kind']=='target_not_preserved' for x in check_items(rows,gd.runtime_view(d,dict(schema_version='1.0.0',person_name_mode='A'))))


def test_malformed_new_contract_is_not_legacy():
    with pytest.raises(ValueError): gd.validate_document(dict(schema_version='1.0.0'))


def test_categories_descendants_and_cross_reference():
    d = sample()
    d['categories']=[dict(id='root',name='Root'),dict(id='child',name='Child',parent_id='root'),dict(id='outside',name='Outside')]
    d['terminology'][0]['category_ids']=['child'];d['persons'][0]['category_ids']=['outside']
    v=gd.runtime_view(d,dict(schema_version='1.0.0',person_name_mode='C',category_ids=['root']))
    assert v['terms'] and v['characters']
    with pytest.raises(ValueError): gd.runtime_view(d,dict(schema_version='1.0.0',person_name_mode='C',category_ids=['missing']))


def test_filter_cli_carries_policy_across_directories(tmp_path):
    from ainiee_translate.glossary import main
    locked=tmp_path/'table.json';gd.write_document(locked,sample(),dict(schema_version='1.0.0',person_name_mode='B'))
    src=tmp_path/'source.json';src.write_text(json.dumps([dict(source_text='law')]),encoding='utf8')
    out=tmp_path/'elsewhere/renamed.json'
    assert main(['filter','--locked',str(locked),'--for',str(src),'--out',str(out)])==0
    assert gd.load_runtime(out)['characters'][0]['render']=='Emile'

def test_pdf_review_accepts_raw_structured_glossary(tmp_path):
    from ainiee_translate.pdf_review import load_review_config
    p=tmp_path/'table.json';gd.write_document(p,sample(),dict(schema_version='1.0.0',person_name_mode='B'))
    prompt=tmp_path/'prompt.md';prompt.write_text('Translate',encoding='utf8')
    cfg=load_review_config(prompt,p)
    assert cfg['glossary']['characters'][0]['render']=='Emile'

@pytest.mark.parametrize('system,expected',[('han','埃米尔'),('latin','Émile'),('other','Emile'),('unknown','Émile')])
def test_default_name_system_decisions(system,expected):
    d=sample();d['persons'][0]['name_system']=system
    r=gd.runtime_view(d)
    assert r['characters'][0]['render']==expected
    assert any(i['kind']=='person_representation_missing' for i in r['_issues']) == (system=='unknown')


def test_scan_exposes_unresolved_structured_issues(tmp_path,monkeypatch,capsys):
    from ainiee_translate import scan
    d=sample();d['persons'][0]['name_system']='unknown'
    p=tmp_path/'table.json';gd.write_document(p,d)
    monkeypatch.setattr(scan,'_items',lambda path:[])
    scan.main(['cache','--locked',str(p),'--mode','terms'])
    assert 'person_representation_missing' in capsys.readouterr().out


def test_legacy_unknown_fields_are_unchanged(tmp_path):
    d=dict(characters=[],terms=[],non_translate=[],unknown=dict(private=1))
    p=tmp_path/'legacy.json';p.write_text(json.dumps(d),encoding='utf8')
    assert gd.read_document(p)==d and gd.load_runtime(p)==d

@pytest.mark.parametrize('bad', ['   ', '\t\n'])
def test_nonempty_text_rejects_whitespace(bad):
    d=sample();d['persons'][0]['source_form']['text']=bad
    with pytest.raises(ValueError):gd.validate_document(d)


def test_precedents_exposes_missing_representations():
    from ainiee_translate.precedents import build
    d=sample();d['persons'][0]['name_system']='unknown'
    assert 'person_representation_missing' in build([],['Émile'],gd.runtime_view(d))


def test_merge_skips_recognition_aliases():
    from ainiee_translate.glossary import merge_newterms
    d=sample();d['terminology'][0]['aliases']=[dict(text='principle',language='en',usage='recognition_only')]
    added,skipped=merge_newterms(d,['principle'])
    assert added==[] and skipped==['principle']
