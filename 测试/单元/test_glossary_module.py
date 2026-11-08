import json
import pytest
from ainiee_translate import module


def test_default_module_and_snapshot(tmp_path, monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME', str(tmp_path/'home'))
    d = module.create_module('demo', name_mode='B')
    data = json.loads((tmp_path/'home/翻译预设/翻译模组/demo/glossary.locked.json').read_text(encoding='utf8'))
    assert data['categories'] == [] and data['schema_version'] == '1.0.0'
    assert module.show_module('demo')['person_name_mode'] == 'B'
    module.load_module('demo', str(tmp_path/'project'))
    assert (tmp_path/'project/work/glossary.locked.policy.json').exists()
    with pytest.raises(ValueError): module.create_module('demo', name_mode='C')

def test_duplicate_create_is_idempotent_and_bad_import_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME',str(tmp_path/'home'))
    path=module.create_module('demo',name_mode='B')
    before=(tmp_path/'home/翻译预设/翻译模组/demo/glossary.locked.json').read_bytes()
    assert module.create_module('demo',name_mode='B')==path
    assert (tmp_path/'home/翻译预设/翻译模组/demo/glossary.locked.json').read_bytes()==before
    with pytest.raises((ValueError,OSError)): module.create_module('bad',categories=str(tmp_path/'missing.json'))

def test_bad_categories_wrapper_is_rejected(tmp_path,monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME',str(tmp_path/'home'))
    with pytest.raises(ValueError): module.create_module('bad',categories={'catgories':[]})
