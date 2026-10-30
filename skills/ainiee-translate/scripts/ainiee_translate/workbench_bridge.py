"""Freeze business projections alongside the offline review-workbench runtime."""
import copy
from contextlib import contextmanager
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
    with store.lock():
        validate_submissions(store)
    return store, binding


def validate_submissions(store):
    """Local files have the same trust boundary as returned review results."""
    rt = runtime()
    submissions = store.submissions()
    by_id = {s.get('submission_id'): s for s in submissions}
    if len(by_id) != len(submissions):
        raise ValueError('提交编号重复')
    items = {i['id']: i for i in store.package['items']}
    edges = {}
    for s in submissions:
        rt.model.validate_schema(s, 'submission')
        if (s['package_id'], s['base_commit']) != (store.package['package_id'], store.package['base_commit']):
            raise ValueError('提交的审核包或 Git 基准不匹配')
        if len({d['item_id'] for d in s['decisions']}) != len(s['decisions']):
            raise ValueError('提交包含重复条目')
        for d in s['decisions']:
            item = items.get(d['item_id'])
            if item is None:
                raise ValueError('提交包含未知条目')
            draft = dict(mode=d['action'], comment=d.get('instruction', ''), quotes=d.get('quotes', []), touched=True)
            if d['action'] == 'edit':
                draft['edits'] = {b['id']: b.get('rows') if b['type'] == 'table' else b.get('text')
                                  for b in d['blocks'] if b['type'] != 'image'}
            if rt.model.resolve_decision(item, draft) != d:
                raise ValueError('提交决定与冻结展示内容不一致')
        edges[s['submission_id']] = set()
        for ref in s.get('resolves', []):
            prior = by_id.get(ref['submission_id'])
            if (prior is None or prior is s
                    or not any(d['target_id'] == ref['target_id'] for d in prior['decisions'])
                    or not any(d['target_id'] == ref['target_id'] for d in s['decisions'])):
                raise ValueError('冲突解决引用无效')
            edges[s['submission_id']].add(ref['submission_id'])
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting:
            raise ValueError('冲突解决引用形成循环')
        if key in visited:
            return
        visiting.add(key)
        for parent in edges[key]:
            visit(parent)
        visiting.remove(key)
        visited.add(key)
    for key in edges:
        visit(key)
    return submissions


@contextmanager
def submitted_comparison(project, targets):
    """Prevent a later human submission from invalidating an in-flight write."""
    store, _ = load_project(project)
    rt = runtime()
    with store.lock():
        history = rt.storage.fingerprint(validate_submissions(store))
    comparison = compare_project(project, targets)
    with store.lock():
        store._assert_frozen()
        if rt.storage.fingerprint(validate_submissions(store)) != history:
            raise ValueError('比较后人工提交已更新，请重新比较')
        yield comparison


def compare_project(project, targets):
    store, _ = load_project(project)
    return runtime().gitops.compare(store.root, dict(package_id=store.package['package_id'],
                                                     base_commit=store.package['base_commit'], targets=targets),
                                    diff_dir=store.root)


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
