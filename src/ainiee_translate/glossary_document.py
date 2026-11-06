"""Validated authoritative glossary documents and policy-bound runtime projections.

Legacy tables are deliberately returned unchanged. Structured tables never persist
runtime projections; the companion policy is validated before any write occurs.
"""
import copy
import hashlib
import json
import os
from pathlib import Path
import re

from jsonschema import Draft202012Validator
from .artifact_io import write_json
from .helpers import backup_file, normalize_apostrophes

GROUPS = ('persons', 'terminology', 'abbreviations')


def structured(data):
    return 'schema_version' in data or any(k in data for k in GROUPS)


def empty_document():
    return dict(schema_version='1.0.0', taxonomy_version='1.0.0', categories=[], persons=[], terminology=[], abbreviations=[], non_translate=[])


def _schema(data, name):
    schema = json.loads((Path(__file__).parent / 'schemas' / (name + '.schema.json')).read_text(encoding='utf8'))
    Draft202012Validator.check_schema(schema)
    errors = list(Draft202012Validator(schema).iter_errors(data))
    if errors:
        raise ValueError('Invalid ' + name + ': ' + errors[0].message)


def validate_document(data):
    if not structured(data):
        return
    _schema(data, 'glossary')
    categories = {c['id']: c for c in data['categories']}
    rows = [r for g in GROUPS for r in data[g]]
    ids = {r['id'] for r in rows}
    if len(categories) != len(data['categories']) or len(ids) != len(rows) or ids & categories.keys():
        raise ValueError('Duplicate ID')
    for c in data['categories']:
        seen = {c['id']}; parent = c.get('parent_id')
        while parent:
            if parent not in categories or parent in seen:
                raise ValueError('Invalid category parent or cycle')
            seen.add(parent); parent = categories[parent].get('parent_id')
    for group in GROUPS:
        preferred = {}
        for row in data[group]:
            preferred.setdefault(recognition_key(row['source_form']['text']), []).append(row)
        for same in preferred.values():
            if len(same) > 1 and any(not row.get('note', '').strip() for row in same):
                raise ValueError('Homonymous preferred forms require a disambiguation note')
    for row in rows:
        if set(row.get('category_ids', [])) - categories.keys():
            raise ValueError('Unknown category reference')
        refs = row.get('references', [])
        if set(refs) - ids:
            raise ValueError('Unknown entry reference')
        template = row.get('target_template', '')
        tokens = re.findall(r'<<person:([^<>]+)>>', template)
        if any(t not in refs or not t.startswith('person.') for t in tokens):
            raise ValueError('Template person must be an explicit reference')
        if '<<' in re.sub(r'<<person:[^<>]+>>', '', template):
            raise ValueError('Invalid person template')
    project = os.environ.get('AINIEE_GLOSSARY_SCHEMA')
    if project:
        schema = json.loads(Path(project).read_text(encoding='utf8'))
        Draft202012Validator.check_schema(schema)
        if list(Draft202012Validator(schema).iter_errors(data)):
            raise ValueError('Locked glossary failed project JSON Schema validation')


def policy_path(path):
    p = Path(path)
    return p.with_name(p.stem + '.policy.json')


def read_document(path):
    data = json.loads(Path(path).read_text(encoding='utf8'))
    validate_document(data)
    return data


def read_policy(path, document=None):
    document = read_document(path) if document is None else document
    p = policy_path(path)
    bound = document.get('policy_sha256')
    if not p.exists():
        if bound:
            raise ValueError('Missing bound glossary policy')
        return dict(schema_version='1.0.0', person_name_mode='D')
    raw = p.read_bytes()
    if bound and hashlib.sha256(raw).hexdigest() != bound:
        raise ValueError('Glossary policy hash mismatch')
    policy = json.loads(raw)
    _schema(policy, 'glossary-policy')
    if set(policy.get('category_ids', [])) - {c['id'] for c in document.get('categories', [])}:
        raise ValueError('Unknown policy category')
    return policy


def write_document(path, document, policy=None):
    path = Path(path)
    data = copy.deepcopy(document)
    if structured(data):
        if policy is None and data.get('policy_sha256'):
            policy = read_policy(path, data)
        if policy is not None:
            _schema(policy, 'glossary-policy')
            if set(policy.get('category_ids', [])) - {c['id'] for c in data['categories']}:
                raise ValueError('Unknown policy category')
            # artifact_io uses the same canonical encoding for policy and hash.
            raw = (json.dumps(policy, ensure_ascii=False, indent=2) + '\n').replace('\n', os.linesep).encode('utf8')
            data['policy_sha256'] = hashlib.sha256(raw).hexdigest()
        validate_document(data)
    path.parent.mkdir(parents=True, exist_ok=True)
    for p in (path, policy_path(path)):
        if p.exists(): backup_file(str(p))
    if structured(data) and policy is not None:
        # The pair is recoverable, not a two-file atomic transaction.
        write_json(policy_path(path), policy)
    write_json(path, data)


def recognition_key(text):
    """The exact normalization used by latin_boundary_search; case stays significant."""
    return normalize_apostrophes(text)


def recognition(row):
    forms = [row['source_form']['text']] + [a['text'] for a in row.get('aliases', [])] + [a['text'] for a in row.get('derived_forms', [])]
    if 'latin_form' in row: forms.append(row['latin_form']['text'])
    if 'chinese_translation' in row: forms.append(row['chinese_translation'])
    return list(dict.fromkeys(forms))


def select_document(data, category_ids=None):
    validate_document(data)
    if not category_ids: return copy.deepcopy(data)
    selected = set(category_ids)
    if selected - {c['id'] for c in data['categories']}: raise ValueError('Unknown selected category')
    while True:
        expanded = selected | {c['id'] for c in data['categories'] if c.get('parent_id') in selected}
        if expanded == selected: break
        selected = expanded
    keep = {r['id'] for g in GROUPS for r in data[g] if not r.get('category_ids') or r.get('common') or set(r['category_ids']) & selected}
    return reference_subset(data, keep)


def reference_subset(data, keep):
    keep = set(keep)
    while True:
        expanded = keep | {ref for g in GROUPS for r in data[g] if r['id'] in keep for ref in r.get('references', [])}
        if expanded == keep: break
        keep = expanded
    out = copy.deepcopy(data)
    for g in GROUPS: out[g] = [r for r in out[g] if r['id'] in keep]
    return out


def runtime_view(data, policy=None):
    if not structured(data): return data
    validate_document(data)
    policy = policy or dict(schema_version='1.0.0', person_name_mode='D')
    _schema(policy, 'glossary-policy')
    data = select_document(data, policy.get('category_ids'))
    mode = policy['person_name_mode']; issues = []; names = {}; chars = []; terms = []
    for p in data['persons']:
        wanted = mode
        if mode == 'D': wanted = dict(han='A', latin='C', other='B').get(p.get('name_system'), '?')
        target = p.get('chinese_translation') if wanted == 'A' else p.get('latin_form', {}).get('text') if wanted == 'B' else p['source_form']['text'] if wanted == 'C' else None
        if not target:
            issues.append(dict(kind='person_representation_missing', id=p['id'], mode=mode))
            target = p['source_form']['text']
        names[p['id']] = target
        chars.append(dict(id=p['id'], canonical=p['source_form']['text'], aliases=recognition(p)[1:], render=target))
    for g in ('terminology', 'abbreviations'):
        for t in data[g]:
            dst = t.get('target_form', {}).get('text', '')
            if t.get('target_template'):
                dst = re.sub(r'<<person:([^<>]+)>>', lambda m: names[m[1]], t['target_template'])
            if t.get('keep_source'): dst = t['source_form']['text']
            if not dst: issues.append(dict(kind='target_missing', id=t['id']))
            terms.append(dict(id=t['id'], src=t['source_form']['text'], aliases=recognition(t)[1:], dst=dst, keep_source=bool(t.get('keep_source'))))
    forms = {}
    for r in chars + terms:
        for form in [r.get('canonical', r.get('src'))] + r['aliases']:
            forms.setdefault(recognition_key(form), set()).add(r['id'])
    for form, ids in forms.items():
        if len(ids) > 1: issues.append(dict(kind='ambiguous_source', source=form, candidate_ids=sorted(ids)))
    for g in GROUPS:
        for r in data[g]:
            if not r.get('category_ids'): issues.append(dict(kind='uncategorized', id=r['id']))
    return dict(characters=chars, terms=terms, non_translate=data['non_translate'], _issues=issues, _structured=True)


def load_runtime(path):
    data = read_document(path)
    return runtime_view(data, read_policy(path, data)) if structured(data) else data
