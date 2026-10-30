import json
import pytest
from ainiee_translate.artifact_io import write_json
from test_workbench_glossary import setup_glossary, submit, INSTRUCTION


@pytest.mark.parametrize('change', ['package', 'base', 'blocks'])
def test_tampered_submission_is_rejected(tmp_path, change):
    from ainiee_translate.workbench_glossary import apply_glossary
    locked, project, data = setup_glossary(tmp_path)
    submission = submit(project)
    path = project / 'review/submissions' / (submission['submission_id'] + '.json')
    if change == 'package':
        submission['package_id'] = 'other-package'
    elif change == 'base':
        submission['base_commit'] = '0' * 40
    else:
        submission['decisions'][0]['blocks'][0]['text'] = 'forged'
    write_json(path, submission)
    with pytest.raises(ValueError):
        apply_glossary(project, locked, INSTRUCTION)
    assert json.loads(locked.read_text(encoding='utf-8')) == data


def test_duplicate_source_rows_cannot_be_swapped(tmp_path):
    from ainiee_translate.workbench_glossary import prepare_glossary, apply_glossary
    locked, proposal = tmp_path / 'locked.json', tmp_path / 'proposal.json'
    data = dict(terms=[dict(src='bank', dst='old', private_id='first'), dict(src='bank', dst='old', private_id='second')])
    write_json(locked, data)
    proposed = json.loads(json.dumps(data))
    proposed['terms'][0]['dst'] = 'new'
    write_json(proposal, proposed)
    project = tmp_path / 'review'
    prepare_glossary(locked, project, proposal)
    submit(project)
    data['terms'].reverse()
    write_json(locked, data)
    assert apply_glossary(project, locked, INSTRUCTION)['conflicts'] == 1
    assert json.loads(locked.read_text(encoding='utf-8')) == data


def test_new_submission_between_comparison_and_write_aborts(tmp_path, monkeypatch):
    import ainiee_translate.workbench_bridge as bridge
    import ainiee_translate.workbench_glossary as glossary
    locked, project, data = setup_glossary(tmp_path)
    submit(project)
    original = bridge.compare_project
    def concurrent(project, targets):
        comparison = original(project, targets)
        submit(project, 'keep')
        return comparison
    monkeypatch.setattr(bridge, 'compare_project', concurrent)
    monkeypatch.setattr(glossary, 'compare_project', concurrent)
    with pytest.raises(ValueError, match='提交|history|更新'):
        glossary.apply_glossary(project, locked, INSTRUCTION)
    assert json.loads(locked.read_text(encoding='utf-8')) == data


def test_optional_fields_can_stay_empty_or_be_cleared(tmp_path):
    from ainiee_translate.workbench_glossary import prepare_glossary, apply_glossary
    from ainiee_translate.workbench_bridge import load_project
    locked = tmp_path / 'locked.json'
    write_json(locked, dict(characters=[dict(canonical='Jim', render='旧译名', aliases=[], note='原说明')]))
    project = tmp_path / 'review'
    prepare_glossary(locked, project)
    store, _ = load_project(project)
    edits = {b['id']: b['text'] for b in store.package['items'][0]['before']}
    edits.update(render='新译名', note='', aliases='')
    submit(project, 'edit', edits)
    assert apply_glossary(project, locked, INSTRUCTION)['applied'] == 1
    row = json.loads(locked.read_text(encoding='utf-8'))['characters'][0]
    assert row['render'] == '新译名' and row['aliases'] == [] and row['note'] == ''


@pytest.mark.parametrize('mode', ['accept', 'keep'])
def test_interrupted_decision_registration_recovers_projection(tmp_path, monkeypatch, mode):
    from test_workbench_reading import setup_reading
    import ainiee_translate.reading_decisions as decisions
    from ainiee_translate.workbench_reading import apply_reading
    from ainiee_translate.reading_round import load_issues
    root, rd, _, project = setup_reading(tmp_path)
    submit(project, mode)
    original = decisions.save_state
    def crash(*args):
        raise RuntimeError('crash after immutable decision before issue projection')
    monkeypatch.setattr(decisions, 'save_state', crash)
    with pytest.raises(RuntimeError):
        apply_reading(project, root / 'cache.json', INSTRUCTION)
    monkeypatch.setattr(decisions, 'save_state', original)
    result = apply_reading(project, root / 'cache.json', INSTRUCTION)
    assert result['conflicts'] == 0
    issue = load_issues(rd)['issues'][0]
    assert issue['active_decision_id'] in issue['decision_ids']
    assert issue['status'] == ('applied' if mode == 'accept' else 'kept')
