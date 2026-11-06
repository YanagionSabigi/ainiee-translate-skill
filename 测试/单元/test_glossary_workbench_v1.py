import copy
import json
import pytest
from ainiee_translate.glossary_document import empty_document, write_document, read_document, runtime_view
from ainiee_translate.workbench_glossary import prepare_glossary, apply_glossary
from ainiee_translate.workbench_bridge import load_project

INSTRUCTION = dict(human_instruction='继续', human_reference='chat:user:continue')


def setup(tmp_path, template=False):
    d = empty_document()
    d['persons'] = [dict(id='person.one', source_form=dict(text='Name',language='en'),name_system='latin')]
    row = dict(id='term.one',source_form=dict(text='law',language='en'),references=['person.one'],note='original')
    row.update(dict(target_template='<<person:person.one>> 法则') if template else dict(target_form=dict(text='法则',language='zh')))
    d['terminology'] = [row]
    locked=tmp_path/'table.json'; write_document(locked,d,dict(schema_version='1.0.0',person_name_mode='C'))
    project=tmp_path/'review'; prepare_glossary(locked,project)
    return locked, project


def submit_term(project, key, value):
    store,binding=load_project(project)
    item=next(i for i in store.package['items'] if i['group_id']=='terminology')
    edits={b['id']:b['text'] for b in item['before']};edits[key]=value
    draft=store.state()['drafts'];draft['items'][item['id']]=dict(mode='edit',touched=True,edits=edits,comment='',quotes=[])
    store.save(draft,draft['revision']);store.submit([item['id']],store.state()['drafts']['revision'])


@pytest.mark.parametrize('template',[False,True])
def test_structured_real_submit_writeback(tmp_path,template):
    locked,project=setup(tmp_path,template)
    submit_term(project,'target_template' if template else 'target_form.text','<<person:person.one>> 定律' if template else '定律')
    result=apply_glossary(project,locked,INSTRUCTION)
    assert result['applied']==1
    data=read_document(locked);row=data['terminology'][0]
    assert row['references']==['person.one'] and row['note']=='original'
    assert 'terms' not in data and row['id']=='term.one'
    if template:
        assert 'target_form' not in row
        assert runtime_view(data)['terms'][0]['dst']=='Name 定律'
    else: assert row['target_form']==dict(text='定律',language='zh')
    assert list(tmp_path.glob('table.json.bak.*'))


def test_policy_drift_requires_new_review(tmp_path):
    locked,project=setup(tmp_path)
    submit_term(project,'target_form.text','定律')
    d=read_document(locked);write_document(locked,d,dict(schema_version='1.0.0',person_name_mode='B'))
    with pytest.raises(ValueError,match='policy|政策'): apply_glossary(project,locked,INSTRUCTION)

def test_stable_id_survives_row_reordering(tmp_path):
    locked,project=setup(tmp_path)
    submit_term(project,'target_form.text','定律')
    d=read_document(locked)
    d['terminology'].insert(0,dict(id='term.other',source_form=dict(text='other',language='en'),target_form=dict(text='其他',language='zh')))
    write_document(locked,d)
    assert apply_glossary(project,locked,INSTRUCTION)['applied']==1
    assert read_document(locked)['terminology'][1]['target_form']['text']=='定律'


def test_project_schema_validates_raw_document_before_write(tmp_path,monkeypatch):
    locked,project=setup(tmp_path)
    submit_term(project,'target_form.text','定律')
    schema=tmp_path/'schema.json';schema.write_text(json.dumps(dict(type='object',properties=dict(terminology=dict(maxItems=0)))),encoding='utf8')
    before=locked.read_bytes();monkeypatch.setenv('AINIEE_GLOSSARY_SCHEMA',str(schema))
    with pytest.raises(ValueError):apply_glossary(project,locked,INSTRUCTION)
    assert locked.read_bytes()==before
