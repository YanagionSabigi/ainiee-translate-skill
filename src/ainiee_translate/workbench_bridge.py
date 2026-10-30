"""Freeze business projections alongside the offline review-workbench runtime."""
import copy
import importlib
import json
from pathlib import Path
from types import SimpleNamespace
import uuid

from .artifact_io import write_json


def runtime():
    prefix = __package__ + '.workbench_runtime.review_workbench.'
    return SimpleNamespace(**{name: importlib.import_module(prefix + name)
                              for name in ('storage', 'model', 'gitops', 'history', 'server')})


def block(identity, text):
    return dict(id=identity, type='text', text=text)


def prepare_project(output, package, binding):
    output = Path(output).resolve()
    if output.exists():
        raise ValueError('审核项目已存在；新一轮请使用新目录')
    rt = runtime()
    rt.model.validate_package(package)
    output.mkdir(parents=True)
    # A nested repository keeps private materials out of the code repository.
    rt.gitops.git(output, 'init')
    if rt.gitops.git(output, 'config', 'user.name', check=False).returncode:
        rt.gitops.git(output, 'config', 'user.name', 'AiNiee local materials')
    if rt.gitops.git(output, 'config', 'user.email', check=False).returncode:
        rt.gitops.git(output, 'config', 'user.email', 'ainiee-local@localhost')
    binding = copy.deepcopy(binding)
    binding.update(schema='ainiee-workbench/1', package_id=package['package_id'])
    write_json(output / 'binding.json', binding)
    write_json(output / 'input.json', package)
    write_json(output / 'scope.json', ['binding.json', 'input.json'])
    rt.gitops.prepare(output, output / 'input.json', output / 'scope.json', output / 'review')
    return dict(project=str(output), package=str(output / 'review'), package_id=package['package_id'])


def load_project(project):
    project = Path(project).resolve()
    rt = runtime()
    store = rt.storage.Store(project / 'review')
    rt.gitops.verify_baseline(store.root, store.package)
    binding = rt.storage.read_json(project / 'binding.json')
    historical = rt.gitops.git(project, 'show', store.package['base_commit'] + ':binding.json')
    if (json.loads(historical.stdout.decode('utf-8')) != binding
            or binding.get('schema') != 'ainiee-workbench/1'
            or binding.get('package_id') != store.package['package_id']):
        raise ValueError('业务映射 binding 与冻结 Git 基准不一致')
    return store, binding


def compare_project(project, targets):
    store, _ = load_project(project)
    return runtime().gitops.compare(store.root, dict(package_id=store.package['package_id'],
                                                     base_commit=store.package['base_commit'], targets=targets))


def package(title, groups):
    return dict(schema_version='1', package_id='ainiee-' + uuid.uuid4().hex, title=title,
                base_commit=None, groups=groups, facets=[], assets=[], items=[])


def instruction_text(instruction):
    if (not isinstance(instruction, dict)
            or not isinstance(instruction.get('human_instruction'), str)
            or not instruction['human_instruction'].strip()
            or not isinstance(instruction.get('human_reference'), str)
            or not instruction['human_reference'].strip()):
        raise ValueError('需要用户在聊天中明确继续的原话和出处')
    return instruction


def application_lock(project):
    return runtime().storage.file_lock(Path(project) / '.application.lock', timeout=5)
