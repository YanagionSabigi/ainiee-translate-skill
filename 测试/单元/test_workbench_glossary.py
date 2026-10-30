import copy
import json
import pytest
from ainiee_translate.artifact_io import write_json


def setup_glossary(tmp_path, proposals=True):
    from ainiee_translate.workbench_glossary import prepare_glossary
    locked = tmp_path / 'glossary.json'
    data = dict(characters=[], terms=[dict(src='oxygen', dst='氧', category='science', private={'keep': 1}),
                                     dict(src='nitrogen', dst='氮')],
                non_translate=[dict(marker='<i>', note='保留标签')], custom={'unchanged': True})
    write_json(locked, data)
    proposal = tmp_path / 'proposals.json'
    changed = copy.deepcopy(data)
    changed['terms'][0]['dst'] = '氧气'
    write_json(proposal, changed)
    project = tmp_path / 'review'
    prepare_glossary(locked, project, proposals=proposal if proposals else None)
    return locked, project, data


def submit(project, mode='accept', edits=None):
    from ainiee_translate.workbench_bridge import load_project
    store, binding = load_project(project)
    item = store.package['items'][0]
    draft = store.state()['drafts']
    draft['items'][item['id']] = dict(mode=mode, touched=True,
                                    edits=edits or {}, comment='请再核查术语', quotes=[])
    store.save(draft, draft['revision'])
    return store.submit([item['id']], store.state()['drafts']['revision'])


INSTRUCTION = dict(human_instruction='继续', human_reference='chat:user:continue')


def test_accept_preserves_unknown_fields_and_other_term_edits(tmp_path):
    from ainiee_translate.workbench_glossary import apply_glossary
    locked, project, original = setup_glossary(tmp_path)
    submit(project)
    original['terms'][1]['dst'] = '氮气'
    write_json(locked, original)
    result = apply_glossary(project, locked, INSTRUCTION)
    assert result['applied'] == 1
    actual = json.loads(locked.read_text(encoding='utf-8'))
    assert actual['terms'][0]['dst'] == '氧气'
    assert actual['terms'][0]['private'] == {'keep': 1}
    assert actual['terms'][1]['dst'] == '氮气'
    assert actual['non_translate'] == original['non_translate']
    assert actual['custom'] == original['custom']
    assert list(tmp_path.glob('glossary.json.bak.*'))
    assert apply_glossary(project, locked, INSTRUCTION)['applied'] == 0


def test_draft_and_comment_do_not_apply(tmp_path):
    from ainiee_translate.workbench_glossary import apply_glossary
    locked, project, original = setup_glossary(tmp_path)
    assert apply_glossary(project, locked, INSTRUCTION)['applied'] == 0
    submit(project, 'comment')
    result = apply_glossary(project, locked, INSTRUCTION)
    assert result['needs_agent']
    assert json.loads(locked.read_text(encoding='utf-8')) == original


@pytest.mark.parametrize('change', ['translation', 'identity'])
def test_drift_rejected(tmp_path, change):
    from ainiee_translate.workbench_glossary import apply_glossary
    locked, project, data = setup_glossary(tmp_path)
    submit(project)
    data['terms'][0]['dst' if change == 'translation' else 'src'] = '外部改动'
    write_json(locked, data)
    assert apply_glossary(project, locked, INSTRUCTION)['conflicts'] == 1
    assert json.loads(locked.read_text(encoding='utf-8')) == data


def test_no_proposal_and_schema_failure_leave_file_unchanged(tmp_path, monkeypatch):
    from ainiee_translate.workbench_glossary import apply_glossary
    from ainiee_translate.workbench_bridge import load_project
    locked, project, data = setup_glossary(tmp_path, proposals=False)
    store, _ = load_project(project)
    assert store.package['items'][0]['proposal'] is None
    item = store.package['items'][0]
    edits = {b['id']: b['text'] for b in item['before']}
    edits['dst'] = '氧气'
    submit(project, 'edit', edits)
    schema = tmp_path / 'schema.json'
    write_json(schema, dict(type='object', properties={'terms': {'maxItems': 0}}))
    monkeypatch.setenv('AINIEE_GLOSSARY_SCHEMA', str(schema))
    with pytest.raises(ValueError):
        apply_glossary(project, locked, INSTRUCTION)
    assert json.loads(locked.read_text(encoding='utf-8')) == data
