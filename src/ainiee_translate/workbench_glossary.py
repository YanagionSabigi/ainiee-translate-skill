"""Locked glossary projections and field-preserving, atomic human writeback."""
import copy
import json
import os
from pathlib import Path
import uuid

from .artifact_io import write_json
from .glossary import load_locked, lint_locked
from .helpers import backup_file
from .workbench_bridge import (runtime, block, package, prepare_project, load_project,
                               compare_project, instruction_text, application_lock)

GROUPS = [('characters', '人物与命名', 'canonical'), ('terms', '术语', 'src'),
          ('non_translate', '禁翻项', 'marker')]
FIELDS = {'characters': ['render', 'aliases', 'gender', 'note'],
          'terms': ['dst', 'category', 'note', 'keep_source'], 'non_translate': ['category', 'note']}


def _fields(group, row):
    fields = []
    for key in FIELDS[group]:
        if key in row or key in ('render', 'dst'):
            value = row.get(key, '')
            kind = 'bool' if isinstance(value, bool) else 'list' if isinstance(value, list) else 'str'
            if kind == 'list' and not all(isinstance(x, str) for x in value):
                raise ValueError('词表 aliases 必须是字符串列表')
            if kind == 'str' and not isinstance(value, str):
                raise ValueError('词表字段类型不受支持：' + key)
            fields.append(dict(key=key, kind=kind))
    # Marker-only entries remain reviewable without making the marker editable.
    return fields or [dict(key='note', kind='str')]


def _blocks(row, fields):
    result = []
    for f in fields:
        value = row.get(f['key'], False if f['kind'] == 'bool' else [] if f['kind'] == 'list' else '')
        if ((f['kind'] == 'bool' and not isinstance(value, bool))
                or (f['kind'] == 'list' and (not isinstance(value, list) or not all(isinstance(v, str) for v in value)))
                or (f['kind'] == 'str' and not isinstance(value, str))):
            raise ValueError('词表字段类型已改变：' + f['key'])
        if f['kind'] == 'bool':
            value = '是' if value else '否'
        elif f['kind'] == 'list':
            value = '\n'.join(value)
        result.append(block(f['key'], value))
    return result


def _row(data, info):
    rows = data.get(info['group'], [])
    if (not isinstance(rows, list) or info['index'] >= len(rows)
            or not isinstance(rows[info['index']], dict)
            or rows[info['index']].get(info['identity_key']) != info['identity']):
        return None
    return rows[info['index']]


def prepare_glossary(locked, output, proposals=None):
    data = load_locked(locked)
    suggested = load_locked(proposals) if proposals else None
    p = package('术语表校对 · ' + Path(locked).stem,
                [dict(id=k, title=title) for k, title, _ in GROUPS])
    binding = dict(kind='glossary', locked=str(Path(locked).resolve()), items={})
    for group, _, identity_key in GROUPS:
        for index, row in enumerate(data.get(group, [])):
            identity = row.get(identity_key)
            if not isinstance(identity, str) or not identity:
                raise ValueError('词条缺少稳定原词身份')
            iid = f'{group}-{index + 1}'
            fields = _fields(group, row)
            before = _blocks(row, fields)
            info = dict(group=group, index=index, identity_key=identity_key, identity=identity, fields=fields)
            other = _row(suggested, info) if suggested else None
            proposal = _blocks(other, fields) if other is not None and other != row else None
            if proposal == before:
                proposal = None
            p['items'].append(dict(id=iid, target_id=iid, group_id=group, facets={}, requires_human=False,
                before=before, baseline=copy.deepcopy(before), proposal=proposal,
                evidence=[block('source', '原词：' + identity),
                          block('metadata', '\n'.join(f'{k}：{v}' for k, v in row.items() if k not in [f['key'] for f in fields]))],
                rationale='逐项核对译名、分类与说明；别名每行一项，“保留原文”使用是或否。', location=identity))
            binding['items'][iid] = info
    return prepare_project(output, p, binding)


def glossary_targets(binding, locked):
    data = load_locked(locked)
    result = []
    for iid, info in binding['items'].items():
        row = _row(data, info)
        if row is not None:
            result.append(dict(target_id=iid, blocks=_blocks(row, info['fields'])))
    return result


def apply_glossary(project, locked, instruction):
    instruction_text(instruction)
    with application_lock(project), runtime().storage.file_lock(str(Path(locked).resolve()) + '.lock'):
        store, binding = load_project(project)
        if binding['kind'] != 'glossary':
            raise ValueError('该包不是术语表校对')
        if Path(locked).resolve() != Path(binding['locked']).resolve():
            raise ValueError('词表路径与本轮业务绑定不同')
        data = load_locked(locked)
        comparison = compare_project(project, glossary_targets(binding, locked))
        result = dict(applied=0, conflicts=0, needs_agent=[], results=[])
        for entry in comparison['items']:
            status = entry['status']
            if status == 'needs_agent':
                result['needs_agent'].append(entry)
            elif status in ('conflict', 'missing_current'):
                result['conflicts'] += 1
            elif status == 'ready':
                info = binding['items'][entry['item_id']]
                row = _row(data, info)
                values = {b['id']: b['text'] for b in entry['decision']['blocks']}
                for f in info['fields']:
                    value = values[f['key']]
                    if f['kind'] == 'bool':
                        if value not in ('是', '否'):
                            raise ValueError('保留原文字段只接受“是”或“否”')
                        value = value == '是'
                    elif f['kind'] == 'list':
                        value = [line.strip() for line in value.splitlines() if line.strip()]
                    # Do not introduce an empty optional field on a keep decision.
                    if f['key'] in row or value:
                        row[f['key']] = value
                result['applied'] += 1
            result['results'].append(dict(item_id=entry['item_id'], status=status,
                                          submission_id=entry['submission_id']))
        if result['applied']:
            # Validate without touching the live file, including project-specific schema.
            schema_path = os.environ.get('AINIEE_GLOSSARY_SCHEMA')
            if schema_path:
                from jsonschema import Draft202012Validator
                schema = json.loads(Path(schema_path).read_text(encoding='utf-8'))
                Draft202012Validator.check_schema(schema)
                if list(Draft202012Validator(schema).iter_errors(data)):
                    raise ValueError('修改后的词表不符合项目 JSON Schema')
            if any(x['kind'] in ('character_missing_render', 'term_missing_src', 'term_missing_dst') for x in lint_locked(data)):
                raise ValueError('修改后的词表未通过结构检查')
            backup_file(str(locked))
            write_json(locked, data)
        write_json(Path(project) / 'applications' / (uuid.uuid4().hex + '.json'),
                   dict(instruction=instruction, result=result))
        return result
