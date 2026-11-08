"""Exercise portable user configuration and glossary transfer at file boundaries."""
import json
from pathlib import Path
from zipfile import ZipFile

import pytest
from jsonschema import Draft202012Validator, ValidationError
from ainiee_translate import module, glossary_document as gd


def test_chinese_module_loads_all_user_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME', str(tmp_path / 'home'))
    folder = Path(module.create_module('我的书', name_mode='B', punctuation_mode='half'))
    assert folder == tmp_path / 'home/翻译预设/翻译模组/我的书'
    for filename in ('初次翻译.md', '预设参数.md', '润色校对.md', '语言风格.md',
                     'glossary.locked.json', 'glossary.locked.schema.json'):
        assert (folder / filename).is_file()
    (folder / '初次翻译.md').write_text('完整传达信息', encoding='utf8')
    (folder / '语言风格.md').write_text('简洁自然', encoding='utf8')
    settings = (folder / '预设参数.md').read_text(encoding='utf8')
    assert 'half' in settings and 'B' in settings
    module.load_module('我的书', str(tmp_path / 'book'))
    work = tmp_path / 'book/work'
    assert (work / 'user_prompt.md').read_text(encoding='utf8') == '完整传达信息'
    assert (work / 'style.md').read_text(encoding='utf8') == '简洁自然'
    assert (work / '预设参数.md').read_text(encoding='utf8') == settings
    schema = json.loads((work / 'glossary.locked.schema.json').read_text(encoding='utf8'))
    Draft202012Validator(schema).validate(gd.read_document(work / 'glossary.locked.json'))
    assert gd.read_policy(work / 'glossary.locked.json')['person_name_mode'] == 'B'


def test_old_module_load_remains_read_only_for_source(tmp_path, monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME', str(tmp_path))
    old = tmp_path / 'modules/old'
    old.mkdir(parents=True)
    (old / 'module.json').write_text('{}', encoding='utf8')
    (old / 'translate_prompt.md').write_text('旧提示', encoding='utf8')
    (old / 'style.md').write_text('旧风格', encoding='utf8')
    module.load_module('old', str(tmp_path / 'project'))
    assert (tmp_path / 'project/work/user_prompt.md').read_text(encoding='utf8') == '旧提示'
    assert (tmp_path / 'project/work/style.md').read_text(encoding='utf8') == '旧风格'
    assert [m['name'] for m in module.list_modules()] == ['old']
    assert not (tmp_path / '翻译预设/翻译模组/old').exists()


def test_switch_to_old_module_backs_up_and_removes_stale_settings(tmp_path, monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME', str(tmp_path / 'home'))
    module.create_module('new', name_mode='B', punctuation_mode='half')
    project = tmp_path / 'project'
    module.load_module('new', str(project))
    old = tmp_path / 'home/modules/old'
    old.mkdir(parents=True)
    (old / 'module.json').write_text('{}', encoding='utf8')
    (old / 'translate_prompt.md').write_text('旧初翻', encoding='utf8')
    module.load_module('old', str(project))
    work = project / 'work'
    for filename in ('预设参数.md', 'glossary.locked.schema.json', 'polish_prompt.md',
                     'style.md', 'glossary.locked.json', 'glossary.locked.policy.json'):
        assert not (work / filename).exists()
        assert list(work.glob(filename + '.bak.*'))
    assert (work / 'user_prompt.md').read_text(encoding='utf8') == '旧初翻'


def test_edited_name_preset_binds_only_loaded_project(tmp_path, monkeypatch):
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME', str(tmp_path / 'home'))
    folder = Path(module.create_module('demo'))
    preset = folder / '预设参数.md'
    preset.write_text(preset.read_text(encoding='utf8').replace('人名翻译模式：D', '人名翻译模式：A'), encoding='utf8')
    module.load_module('demo', str(tmp_path / 'project'))
    assert gd.read_policy(tmp_path / 'project/work/glossary.locked.json')['person_name_mode'] == 'A'
    assert gd.read_policy(folder / 'glossary.locked.json')['person_name_mode'] == 'D'


def test_glossary_zip_survives_move_and_documents_local_exceptions(tmp_path):
    from ainiee_translate import glossary_bundle
    glossary = tmp_path / 'original/glossary.locked.json'
    data = gd.empty_document()
    data['terminology'] = [dict(id='term.n', source_form=dict(text='n-tuple', language='en'),
                                target_form=dict(text='$n$-元组', language='zh'),
                                note='公式须使用 TeX，n 保留变量含义')]
    gd.write_document(glossary, data, dict(schema_version='1.0.0', person_name_mode='D'))
    notes = tmp_path / 'special.md'
    notes.write_text('本书采用半角标点；只迁移代数领域。', encoding='utf8')
    dest = tmp_path / 'portable.zip'
    glossary_bundle.pack(glossary, dest, notes=notes)
    with ZipFile(dest) as archive:
        names = archive.namelist()
        assert {'glossary.locked.json', 'glossary.locked.schema.json',
                'glossary.locked.policy.json', 'glossary-policy.schema.json',
                '术语表文档.md', '本表说明.md'} <= set(names)
        assert all('/' not in name and '\\' not in name for name in names)
        archive.extractall(tmp_path / 'moved')
    moved = tmp_path / 'moved'
    schema = json.loads((moved / 'glossary.locked.schema.json').read_text(encoding='utf8'))
    doc = gd.read_document(moved / 'glossary.locked.json')
    Draft202012Validator(schema).validate(doc)
    assert gd.load_runtime(moved / 'glossary.locked.json')['terms'][0]['dst'] == '$n$-元组'
    description = (moved / '本表说明.md').read_text(encoding='utf8')
    assert '本书采用半角标点' in description and '公式须使用 TeX' in description


def test_glossary_pack_rejects_tampered_policy_and_existing_output(tmp_path):
    from ainiee_translate import glossary_bundle
    glossary = tmp_path / 'glossary.locked.json'
    gd.write_document(glossary, gd.empty_document(), dict(schema_version='1.0.0', person_name_mode='D'))
    dest = tmp_path / 'existing.zip'
    dest.write_bytes(b'keep')
    with pytest.raises(FileExistsError):
        glossary_bundle.pack(glossary, dest)
    gd.policy_path(glossary).write_text('{}', encoding='utf8')
    with pytest.raises(ValueError):
        glossary_bundle.pack(glossary, tmp_path / 'bad.zip')
    assert not (tmp_path / 'bad.zip').exists()
    assert dest.read_bytes() == b'keep'


def test_glossary_pack_preserves_custom_schema_and_forbidden_marker_notes(tmp_path):
    from ainiee_translate import glossary_bundle
    glossary = tmp_path / 'glossary.locked.json'
    data = gd.empty_document()
    data['non_translate'] = [dict(marker='MAGIC', note='这是程序占位符', regex=False)]
    gd.write_document(glossary, data)
    schema_path = tmp_path / 'glossary.locked.schema.json'
    schema_path.write_text(json.dumps({'type': 'object', 'title': '本书特有约束'}), encoding='utf8')
    dest = tmp_path / 'custom.zip'
    glossary_bundle.pack(glossary, dest)
    with ZipFile(dest) as archive:
        assert json.loads(archive.read('glossary.locked.schema.json'))['title'] == '本书特有约束'
        assert '这是程序占位符' in archive.read('本表说明.md').decode('utf8')


def test_glossary_pack_rejects_external_schema_dependencies(tmp_path):
    from ainiee_translate import glossary_bundle
    glossary = tmp_path / 'glossary.locked.json'
    gd.write_document(glossary, gd.empty_document())
    (tmp_path / 'glossary.locked.schema.json').write_text(json.dumps({
        'properties': {'terminology': {'items': {'$ref': 'term.schema.json'}}}
    }), encoding='utf8')
    with pytest.raises(ValueError, match='自包含'):
        glossary_bundle.pack(glossary, tmp_path / 'incomplete.zip')
    assert not (tmp_path / 'incomplete.zip').exists()


def test_glossary_pack_preserves_active_project_schema(tmp_path, monkeypatch):
    from ainiee_translate import glossary_bundle
    glossary = tmp_path / 'glossary.locked.json'
    gd.write_document(glossary, gd.empty_document())
    contract = tmp_path / 'project.schema.json'
    contract.write_text(json.dumps({'properties': {'persons': {'maxItems': 0}}}), encoding='utf8')
    monkeypatch.setenv('AINIEE_GLOSSARY_SCHEMA', str(contract))
    glossary_bundle.pack(glossary, tmp_path / 'project.zip')
    with ZipFile(tmp_path / 'project.zip') as archive:
        schema = json.loads(archive.read('glossary.locked.schema.json'))
        candidate = gd.empty_document()
        candidate['persons'] = [dict(id='person.demo', source_form=dict(text='Demo', language='en'))]
        with pytest.raises(ValidationError):
            Draft202012Validator(schema).validate(candidate)


def test_glossary_pack_requires_loading_changed_module_preset(tmp_path, monkeypatch):
    from ainiee_translate import glossary_bundle
    monkeypatch.setenv('AINIEE_TRANSLATE_HOME', str(tmp_path / 'home'))
    folder = Path(module.create_module('demo'))
    preset = folder / '预设参数.md'
    preset.write_text(preset.read_text(encoding='utf8').replace('人名翻译模式：D', '人名翻译模式：A'), encoding='utf8')
    with pytest.raises(ValueError, match='加载'):
        glossary_bundle.pack(folder / 'glossary.locked.json', tmp_path / 'wrong.zip')
    module.load_module('demo', str(tmp_path / 'project'))
    glossary_bundle.pack(tmp_path / 'project/work/glossary.locked.json', tmp_path / 'right.zip')
    with ZipFile(tmp_path / 'right.zip') as archive:
        assert json.loads(archive.read('glossary.locked.policy.json'))['person_name_mode'] == 'A'
