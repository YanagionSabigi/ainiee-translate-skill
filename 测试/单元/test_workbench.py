import copy
import json
import subprocess

import pytest


def material():
    blocks = [dict(id='body', type='text', text='当前译名')]
    return dict(schema_version='1', package_id='test-material', title='词表校对',
                base_commit=None, groups=[dict(id='terms', title='术语')], facets=[], assets=[],
                items=[dict(id='term-1', target_id='term-1', group_id='terms', facets={},
                            requires_human=False, before=blocks, baseline=copy.deepcopy(blocks),
                            proposal=[dict(id='body', type='text', text='建议译名')],
                            evidence=[], rationale='统一用语', location='oxygen')])


def test_frozen_project_does_not_change_parent_head_and_drafts_are_not_submissions(tmp_path):
    from ainiee_translate.workbench_bridge import prepare_project, load_project, compare_project, runtime
    parent = tmp_path / 'parent'
    parent.mkdir()
    subprocess.run(['git', 'init', str(parent)], check=True, capture_output=True)
    project = parent / 'review'
    prepare_project(project, material(), dict(kind='test', items={}))
    store, binding = load_project(project)
    assert binding['kind'] == 'test'
    assert store.package['base_commit']
    assert (project / '.git').is_dir()
    assert subprocess.run(['git', '-C', str(parent), 'rev-parse', '--verify', 'HEAD'], capture_output=True).returncode != 0
    draft = store.state()['drafts']
    draft['items']['term-1'] = dict(mode='accept')
    store.save(draft, draft['revision'])
    targets = [dict(target_id='term-1', blocks=material()['items'][0]['baseline'])]
    assert compare_project(project, targets)['items'] == []
    store.submit(['term-1'], store.state()['drafts']['revision'])
    assert compare_project(project, targets)['items'][0]['status'] == 'ready'


def test_binding_tampering_rejected(tmp_path):
    from ainiee_translate.workbench_bridge import prepare_project, load_project
    prepare_project(tmp_path / 'review', material(), dict(kind='test', items={}))
    path = tmp_path / 'review' / 'binding.json'
    data = json.loads(path.read_text(encoding='utf-8'))
    data['kind'] = 'reading'
    path.write_text(json.dumps(data), encoding='utf-8')
    with pytest.raises(ValueError, match='binding|映射'):
        load_project(path.parent)


def test_comparison_keeps_temporary_book_text_inside_review(tmp_path, monkeypatch):
    from ainiee_translate.workbench_bridge import prepare_project, load_project, compare_project, runtime
    from pathlib import Path
    project = tmp_path / 'review'
    prepare_project(project, material(), dict(kind='test', items={}))
    store, _ = load_project(project)
    draft = store.state()['drafts']
    draft['items']['term-1'] = dict(mode='accept')
    store.save(draft, draft['revision'])
    store.submit(['term-1'], store.state()['drafts']['revision'])
    original = runtime().gitops.tempfile.TemporaryDirectory
    def project_temp(*args, **kwargs):
        assert kwargs.get('dir') is not None, 'book text must stay in the private review project'
        assert Path(kwargs['dir']).resolve() == (project / 'review').resolve()
        return original(*args, **kwargs)
    monkeypatch.setattr(runtime().gitops.tempfile, 'TemporaryDirectory', project_temp)
    result = compare_project(project, [dict(target_id='term-1', blocks=material()['items'][0]['baseline'])])
    assert result['items'][0]['status'] == 'ready'
