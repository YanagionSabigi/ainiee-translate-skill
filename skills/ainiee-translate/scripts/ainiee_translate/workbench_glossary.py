"""Locked glossary projections and field-preserving, atomic human writeback."""
import copy
import json
import os
from pathlib import Path
import uuid

from .artifact_io import write_json, digest
from .glossary import load_locked, lint_locked
from . import glossary_document as gd
from .helpers import backup_file
from .glossary_review_data import load_review_data, term_review_info
from .workbench_bridge import (runtime, block, package, prepare_project, load_project,
                               compare_project, instruction_text, application_lock, submitted_comparison)

GROUPS = [('characters', '人物与命名', 'canonical'), ('terms', '术语', 'src'),
          ('non_translate', '禁翻项', 'marker')]
FIELDS = {'characters': ['render', 'aliases', 'gender', 'note'],
          'terms': ['dst', 'category', 'note', 'keep_source'], 'non_translate': ['category', 'note']}


STRUCTURED_GROUPS = [('persons', '人名', 'id'), ('terminology', '术语', 'id'), ('abbreviations', '缩写', 'id'), ('non_translate', '禁翻项', 'marker')]


def _value(row, key, default=''):
    if '.' in key:
        parent, child = key.split('.', 1)
        return row.get(parent, {}).get(child, default)
    return row.get(key, default)


def _immutable(row, fields):
    value = copy.deepcopy(row)
    for f in fields:
        key = f['key']
        if '.' in key:
            parent, child = key.split('.', 1)
            if parent in value: value[parent].pop(child, None)
        else: value.pop(key, None)
    return value


def _structured_fields(group, row):
    if group == 'persons':
        keys = ['source_form.text']
        if 'latin_form' in row: keys.append('latin_form.text')
        if 'chinese_translation' in row: keys.append('chinese_translation')
    elif group in ('terminology', 'abbreviations'):
        keys = ['target_template'] if 'target_template' in row else ['target_form.text']
    else: return _fields(group, row)
    fields = [dict(key=k, kind='str') for k in keys + ['note']]
    if group == 'abbreviations': fields.append(dict(key='keep_source', kind='bool'))
    return fields


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
        value = _value(row, f['key'], False if f['kind'] == 'bool' else [] if f['kind'] == 'list' else '')
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
    if info['identity_key'] == 'id':
        matches = [r for r in rows if r.get('id') == info['identity']]
        rows = matches
        info = dict(info, index=0)
    if (not isinstance(rows, list) or info['index'] >= len(rows)
            or not isinstance(rows[info['index']], dict)
            or rows[info['index']].get(info['identity_key']) != info['identity']):
        return None
    row = rows[info['index']]
    immutable = _immutable(row, info['fields'])
    if digest(immutable) != info.get('identity_hash'):
        return None
    return row


def prepare_glossary(locked, output, proposals=None, review_data=None):
    data = load_locked(locked)
    structured = gd.structured(data)
    policy = gd.read_policy(locked, data) if structured else None
    groups = STRUCTURED_GROUPS if structured else GROUPS
    metadata = load_review_data(data.get('terms', []), review_data)
    suggested = load_locked(proposals) if proposals else None
    p = package('术语表校对 · ' + Path(locked).stem,
                [dict(id=k, title=title) for k, title, _ in groups])
    p['review_profile'] = 'glossary'
    binding = dict(kind='glossary', locked=str(Path(locked).resolve()), items={})
    if structured: binding['policy_hash'] = data.get('policy_sha256') or digest(policy)
    for group, _, identity_key in groups:
        for index, row in enumerate(data.get(group, [])):
            identity = row.get(identity_key)
            if not isinstance(identity, str) or not identity:
                raise ValueError('词条缺少稳定原词身份')
            iid = row['id'] if structured and group != 'non_translate' else f'{group}-{index + 1}'
            fields = _structured_fields(group, row) if structured else [dict(key='dst', kind='str')] if group == 'terms' else _fields(group, row)
            before = _blocks(row, fields)
            info = dict(group=group, index=index, identity_key=identity_key, identity=identity, fields=fields)
            info['identity_hash'] = digest(_immutable(row, fields))
            other = _row(suggested, info) if suggested else None
            proposal = _blocks(other, fields) if other is not None and other != row else None
            if proposal == before:
                proposal = None
            p['items'].append(dict(id=iid, target_id=iid, group_id=group, facets={}, requires_human=False,
                before=before, baseline=copy.deepcopy(before), proposal=proposal,
                evidence=[block('source', '原词：' + identity),
                          block('metadata', '\n'.join(f'{k}：{v}' for k, v in row.items() if k not in [f['key'] for f in fields]))],
                allow_empty_blocks=[f['key'] for f in fields if f['key'] not in ('dst', 'render', 'keep_source')],
                rationale='逐项核对译名、分类与说明；别名每行一项，“保留原文”使用是或否。', location=identity))
            if structured and group == 'terminology' and 'target_template' in row:
                preview = next(t['dst'] for t in gd.runtime_view(data, dict(policy, category_ids=[]))['terms'] if t['id'] == row['id'])
                p['items'][-1]['evidence'].append(block('preview', '当前模式展开（只读）：' + preview))
            if group == 'terms':
                item = p['items'][-1]
                item['term_info'], item['requires_human'] = term_review_info(row, metadata)
                item['evidence'] = []
                item['rationale'] = ''
            binding['items'][iid] = info
    return prepare_project(output, p, binding)


def glossary_targets(binding, locked):
    data = load_locked(locked)
    if 'policy_hash' in binding and (data.get('policy_sha256') or digest(gd.read_policy(locked, data))) != binding['policy_hash']:
        raise ValueError('Glossary policy changed; prepare review again')
    if gd.structured(data): gd.read_policy(locked, data)
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
        with submitted_comparison(project, glossary_targets(binding, locked)) as comparison:
            return _consume(project, locked, instruction, data, binding, comparison)


def _consume(project, locked, instruction, data, binding, comparison):
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
                if '.' in f['key']:
                    parent, child = f['key'].split('.', 1)
                    if parent in row or value:
                        row.setdefault(parent, dict(language='und'))[child] = value
                elif f['key'] in row or value:
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
        if gd.structured(data):
            gd.write_document(locked, data)
        else:
            backup_file(str(locked))
            write_json(locked, data)
    write_json(Path(project) / 'applications' / (uuid.uuid4().hex + '.json'),
               dict(instruction=instruction, result=result))
    return result
