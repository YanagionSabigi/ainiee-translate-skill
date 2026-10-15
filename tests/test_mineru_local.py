"""Independent contract fixtures; no model download or inference in unit tests."""
import importlib
import json
import os
from pathlib import Path
import subprocess
import sys
import zipfile

import pytest


def adapter():
    assert importlib.util.find_spec('ainiee_translate.mineru_local'), 'local MinerU adapter is not implemented'
    return importlib.import_module('ainiee_translate.mineru_local')


def middle(image=False):
    blocks = [{'type': 'text', 'index': 0, 'bbox': [0.1, 0.1, 0.9, 0.2],
               'content': [{'type': 'text', 'content': 'An original paragraph.'}]}]
    if image:
        blocks.append({'type': 'image', 'index': 1, 'bbox': [0.1, 0.3, 0.9, 0.8],
                       'content': [{'type': 'image_body', 'index': 1, 'image_path': 'images/figure.png', 'content': ''}]})
    return {'schema': 'docvortex.middle', 'schema_version': '2.0',
            'metadata': {'file_suffix': 'pdf', 'producer': {'name': 'fixture', 'version': '1'}},
            'is_full_document': True, 'pages': [{'page_idx': 0, 'blocks': blocks}]}


def bundle(tmp_path, document=None, assets=None, entries=()):
    path = tmp_path / '中文 result.zip'
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('middle.json', json.dumps(document if document is not None else middle()))
        for name, data in (assets or {}).items():
            z.writestr(name, data)
        for name, data in entries:
            info = zipfile.ZipInfo('placeholder')
            info.filename = name  # Bypass Windows ZipInfo's slash normalization.
            z.writestr(info, data)
    return path


def test_complete_bundle_is_immutable_and_repeatable(tmp_path):
    api = adapter()
    path = bundle(tmp_path)
    destination = tmp_path / 'imports'
    first = api.import_bundle(path, destination)
    second = api.import_bundle(path, destination)
    assert first == second
    assert first['status'] == 'completed'
    assert first['schema'] == 'docvortex.middle'
    assert (destination / first['middle_json']).is_file()
    changed = middle(); changed['pages'][0]['blocks'][0]['content'][0]['content'] = 'Changed'
    with pytest.raises((ValueError, FileExistsError), match='immutable|different|conflict'):
        api.import_bundle(bundle(tmp_path, changed), destination)


def test_import_rejects_structure_without_assets(tmp_path):
    api = adapter()
    destination = tmp_path / 'imports'
    with pytest.raises(ValueError, match='asset|image'):
        api.import_bundle(bundle(tmp_path, middle(True)), destination)
    assert not (destination / 'manifest.json').exists()


@pytest.mark.parametrize('change', [{'is_full_document': False}, {'pages': []}])
def test_partial_or_empty_middle_never_completes(tmp_path, change):
    api = adapter(); document = middle(); document.update(change)
    with pytest.raises(ValueError, match='full|partial|page'):
        api.import_bundle(bundle(tmp_path, document), tmp_path / 'raw')
    assert not (tmp_path / 'raw/manifest.json').exists()


@pytest.mark.parametrize('change', [
    {'schema': 'legacy'}, {'schema_version': '1.0'}, {'pages': 'wrong'},
    {'is_full_document': 'yes'}, {'metadata': {}},
    {'pages': [{'page_idx': -1, 'blocks': []}]},
    {'pages': [{'page_idx': 0, 'blocks': [{'type': 'text', 'index': 0, 'content': 'legacy'}]}]},
])
def test_invalid_protocol_is_rejected(tmp_path, change):
    api = adapter()
    data = middle(); data.update(change)
    with pytest.raises(ValueError):
        api.import_bundle(bundle(tmp_path, data), tmp_path / 'imports')


@pytest.mark.parametrize('name', ['../escape', '/absolute', 'C:/absolute', 'a\\b', 'a/../../b', 'AUX.txt'])
def test_unsafe_zip_members_are_rejected(tmp_path, name):
    api = adapter()
    with pytest.raises(ValueError, match='path|member'):
        api.import_bundle(bundle(tmp_path, entries=[(name, 'bad')]), tmp_path / 'imports')
    assert not (tmp_path / 'escape').exists()


def test_duplicate_zip_members_are_rejected(tmp_path):
    api = adapter()
    with pytest.warns(UserWarning):
        path = bundle(tmp_path, entries=[('middle.json', '{}')])
    with pytest.raises(ValueError, match='(?i)duplicate|collision'):
        api.import_bundle(path, tmp_path / 'imports')


def test_wrong_python_has_actionable_diagnostic(tmp_path):
    api = adapter()
    with pytest.raises(api.MinerUError, match='Python|python|interpreter'):
        api.probe_mineru(tmp_path / 'missing python', env={})


@pytest.fixture
def runner(monkeypatch):
    api = adapter()
    calls = []
    config = {'mineru_version': '4.0.10', 'docvortex_version': '0.5.8',
              'model_source': 'local', 'vlm_server_url': '', 'llm_features_enabled': False,
              'config_sha256': 'config-one', 'models_ready': True}
    def run(args, **kwargs):
        calls.append((args, kwargs))
        if '-c' in args:
            return subprocess.CompletedProcess(args, 0, json.dumps(config), '')
        output = Path(args[args.index('-o') + 1])
        with zipfile.ZipFile(output, 'w') as z:
            z.writestr('middle.json', json.dumps(middle()))
        return subprocess.CompletedProcess(args, 0, 'done', '')
    monkeypatch.setattr(api, '_run', run)
    return api, calls, config


def test_paths_are_passed_as_arguments_with_no_shell(tmp_path, runner):
    api, calls, _ = runner
    pdf = tmp_path / '中文 source with spaces.pdf'; pdf.write_bytes(b'pdf one')
    path = api.extract_bundle(pdf, tmp_path / 'result', python=Path(sys.executable), env={})
    assert path.is_file()
    command, kwargs = calls[-1]
    assert command[:5] == [sys.executable, '-B', '-m', 'mineru.kit.main', 'parse']
    assert command[5] == str(pdf.resolve())
    assert command[-4:] == ['--format', 'zip', '--tier', 'standard']
    assert kwargs['env']['HF_HUB_OFFLINE'] == '1'


def test_resume_invalidates_changed_input(tmp_path, runner):
    api, calls, config = runner
    pdf = tmp_path / 'in.pdf'; pdf.write_bytes(b'one')
    args = dict(python=Path(sys.executable), env={})
    first = api.extract_bundle(pdf, tmp_path / 'result', **args)
    api.extract_bundle(pdf, tmp_path / 'result', **args)
    assert len([c for c, _ in calls if 'parse' in c]) == 1
    pdf.write_bytes(b'two')
    second = api.extract_bundle(pdf, tmp_path / 'result', **args)
    assert first != second and first.is_file()
    config['config_sha256'] = 'config-two'
    third = api.extract_bundle(pdf, tmp_path / 'result', **args)
    assert third != second


@pytest.mark.parametrize('change', [
    {'model_source': 'auto'}, {'vlm_server_url': 'https://example.invalid/v1'},
    {'llm_features_enabled': True}, {'models_ready': False},
])
def test_nonlocal_or_unready_configuration_never_extracts(tmp_path, runner, change):
    api, calls, config = runner; config.update(change)
    pdf = tmp_path / 'in.pdf'; pdf.write_bytes(b'one')
    with pytest.raises(api.MinerUError):
        api.extract_bundle(pdf, tmp_path / 'out', python=Path(sys.executable), env={})
    assert not any('parse' in c for c, _ in calls)


@pytest.mark.parametrize('error', [subprocess.CalledProcessError(2, 'parse', stderr='missing model'),
                                 subprocess.TimeoutExpired('parse', 1), KeyboardInterrupt()])
def test_failed_or_cancelled_extract_retains_diagnostics(tmp_path, runner, monkeypatch, error):
    api, calls, _ = runner; original = api._run
    def fail(args, **kwargs):
        if 'parse' in args:
            raise error
        return original(args, **kwargs)
    monkeypatch.setattr(api, '_run', fail)
    pdf = tmp_path / 'in.pdf'; pdf.write_bytes(b'one')
    with pytest.raises((api.MinerUError, KeyboardInterrupt)):
        api.extract_bundle(pdf, tmp_path / 'out', python=Path(sys.executable), env={})
    statuses = [json.loads(p.read_text())['status'] for p in (tmp_path / 'out').rglob('manifest.json')]
    assert statuses and all(s in ('failed', 'cancelled') for s in statuses)
