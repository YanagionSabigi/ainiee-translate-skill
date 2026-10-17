"""Independent source-PDF proofreading tasks and publication evidence bindings."""
from __future__ import annotations

import argparse
import copy
import json
from pathlib import Path

from .artifact_io import sha256, write_json
from .pdf_bridge import contract
from .pdf_cache import _validated, _identity, _index, apply_cache_to_book

# The built-in locked-table contract is always enforced, before any terms are used.
GLOSSARY_SCHEMA = {
    'type': 'object', 'required': ['characters', 'terms', 'non_translate'],
    'properties': {
        'characters': {'type': 'array', 'items': {'type': 'object', 'required': ['canonical'],
            'properties': {'canonical': {'type': 'string', 'minLength': 1}, 'render': {'type': 'string'},
                           'aliases': {'type': 'array', 'items': {'type': 'string'}}}}},
        'terms': {'type': 'array', 'items': {'type': 'object', 'required': ['src', 'dst'],
            'properties': {'src': {'type': 'string', 'minLength': 1}, 'dst': {'type': 'string'},
                           'keep_source': {'type': 'boolean'}}}},
        'non_translate': {'type': 'array', 'items': {'anyOf':[{'type':'string'},
            {'type':'object','required':['marker'],'properties':{'marker':{'type':'string','minLength':1}}}]}}}}


def load_review_config(prompt_path, glossary_path, *, glossary_schema_path=None):
    from jsonschema import Draft202012Validator
    try:
        locked = json.loads(Path(glossary_path).read_text(encoding='utf8'))
        Draft202012Validator(GLOSSARY_SCHEMA).validate(locked)
        if glossary_schema_path:
            schema = json.loads(Path(glossary_schema_path).read_text(encoding='utf8'))
            Draft202012Validator.check_schema(schema)
            Draft202012Validator(schema).validate(locked)
    except Exception as exc:
        raise ValueError(f'Locked glossary Schema validation failed: {exc}') from exc
    prompt = Path(prompt_path).read_text(encoding='utf8')
    if not prompt.strip():
        raise ValueError('Translation prompt cannot be empty')
    return {'prompt_sha256': sha256(prompt_path), 'glossary_sha256': sha256(glossary_path),
            'prompt': prompt, 'glossary': locked}


def _pdf_path(book, work, explicit=None):
    candidates = [explicit] if explicit else [book.get('source_pdf'), book.get('source_path'),
                                             json.loads((Path(work)/'state.json').read_text(encoding='utf8')).get('source_path') if (Path(work)/'state.json').exists() else None,
                                             Path(work) / 'source.pdf', Path(work) / 'input.pdf']
    for path in candidates:
        if path:
            path = Path(path)
            if not path.is_absolute():
                path = Path(work) / path
            if path.is_file() and sha256(path) == book['source_sha256']:
                return path.resolve()
    raise ValueError('Original PDF evidence file is missing or its hash changed')


def export_review_tasks(book, cf, *, work, prompt_path, glossary_path, context_id,
                        translation_context_id, glossary_schema_path=None, unit_ids=None, source_pdf_path=None):
    units = _validated(book)
    _identity(book, cf)
    apply_cache_to_book(book, cf)
    if not context_id or not translation_context_id or context_id == translation_context_id:
        raise ValueError('Proofreading requires an independent context identity')
    config = load_review_config(prompt_path, glossary_path, glossary_schema_path=glossary_schema_path)
    pdf = _pdf_path(book, work, source_pdf_path)
    items = _index(cf)
    selected = set(unit_ids) if unit_ids is not None else {u['unit_id'] for u in units}
    if not selected.issubset(items):
        raise ValueError('Unknown proofreading unit ID')
    tasks = []
    for unit in units:
        if unit['unit_id'] not in selected:
            continue
        item = items[unit['unit_id']]
        target_text = unit['source_text'] if unit.get('translation_policy')=='preserve_source' else item.translated_text
        tasks.append({'unit_id': unit['unit_id'], 'chapter_id': unit['chapter_id'],
            'source_revision': unit['source_revision'], 'source_text': unit['source_text'],
            'structure_sha256': unit.get('structure_sha256'),
            'target_text': target_text, 'source_sha256': unit['source_sha256'],
            'target_sha256': contract().content_digest(target_text),
            'provenance': copy.deepcopy(unit.get('provenance', [])), 'markers': unit.get('markers', []),
            'context_id': context_id, 'translation_context_id': translation_context_id,
            'prompt_sha256': config['prompt_sha256'], 'glossary_sha256': config['glossary_sha256']})
    return {'schema': 'pdf-proofreading-tasks/1', 'document_id': book['document_id'],
        'source_sha256': book['source_sha256'], 'source_revision': book['revision'],
        'source_pdf': str(pdf), 'context_id': context_id, 'translation_context_id': translation_context_id,
        'prompt_sha256': config['prompt_sha256'], 'glossary_sha256': config['glossary_sha256'],
        'prompt': config['prompt'], 'glossary': config['glossary'], 'units': tasks,
        'required_checks': ['omissions', 'meaning', 'ocr', 'terminology', 'numbers', 'formulae', 'structure', 'references']}


def import_review_results(book, cf, tasks, results, *, work, prompt_path, glossary_path,
                          glossary_schema_path=None):
    _validated(book)
    _identity(book, cf)
    config = load_review_config(prompt_path, glossary_path, glossary_schema_path=glossary_schema_path)
    if tasks.get('schema') != 'pdf-proofreading-tasks/1' or tasks.get('document_id') != book['document_id']:
        raise ValueError('Proofreading task document identity mismatch')
    if (tasks.get('source_sha256') != book['source_sha256'] or not tasks.get('context_id')
            or tasks['context_id'] == tasks.get('translation_context_id') or not tasks.get('translation_context_id')):
        raise ValueError('Invalid independent proofreading context or PDF identity')
    for key in ('prompt_sha256', 'glossary_sha256'):
        if tasks.get(key) != config[key]:
            raise ValueError('Proofreading configuration version changed')
    _pdf_path(book, work, tasks.get('source_pdf'))
    apply_cache_to_book(book, cf)
    items, current = _index(cf), {u['unit_id']: u for u in contract().iter_units(book)}
    task_rows = {u['unit_id']: u for u in tasks['units']}
    if len(task_rows) != len(tasks['units']):
        raise ValueError('Duplicate proofreading task unit')
    records, pending = [], []
    seen = set()
    rows = results.get('records', []) if isinstance(results, dict) else results
    for row in rows:
        uid = row.get('unit_id')
        if uid not in task_rows or uid in seen or uid not in current:
            raise ValueError('Unknown/duplicate proofreading result unit')
        seen.add(uid)
        task, unit, item = task_rows[uid], current[uid], items[uid]
        target_text = unit['source_text'] if unit.get('translation_policy')=='preserve_source' else item.translated_text
        if (task.get('source_sha256') != unit['source_sha256']
                or task.get('source_revision') != unit['source_revision']
                or task.get('structure_sha256') != unit.get('structure_sha256')
                or task.get('target_sha256') != contract().content_digest(target_text)
                or task.get('provenance') != unit.get('provenance', [])):
            raise ValueError('Stale source/target proofreading task')
        if (row.get('context_id') != tasks['context_id'] or row.get('status') != 'passed'
                or row.get('source_sha256') != task['source_sha256']
                or row.get('target_sha256') != task['target_sha256']):
            raise ValueError('Proofreading result identity or conclusion mismatch')
        evidence = row.get('evidence')
        if (not isinstance(evidence, dict) or evidence.get('pdf_sha256') != book['source_sha256']
                or not evidence.get('pages') or not evidence.get('observations')
                or not unit.get('provenance')):
            raise ValueError('Proofreading requires actual PDF location evidence and observations')
        known_pages = {p.get('physical_page', p.get('page')) for p in unit['provenance'] if isinstance(p, dict)}
        known_pages.discard(None)
        if known_pages and not known_pages.issubset(set(evidence['pages'])):
            raise ValueError('PDF evidence does not cover source provenance')
        findings = row.get('findings')
        if not isinstance(findings, list) or any(not f.get('resolution') or f.get('status') != 'resolved' for f in findings):
            raise ValueError('Findings require explicit resolution and recheck')
        if set(row.get('checks', [])) != set(tasks['required_checks']):
            raise ValueError('Proofreading did not cover required checks')
        record = {key: copy.deepcopy(task[key]) for key in ('unit_id', 'source_revision', 'source_sha256',
            'target_sha256', 'provenance', 'context_id', 'translation_context_id', 'prompt_sha256', 'glossary_sha256')}
        record.update(status='passed', independent=True, evidence=copy.deepcopy(evidence),
                      findings=copy.deepcopy(findings), checks=row['checks'],
                      structure_sha256=task.get('structure_sha256'))
        contract().validate_proof_record(record, unit, source_sha256=book['source_sha256'],
            target_text=target_text, prompt_sha256=config['prompt_sha256'],
            glossary_sha256=config['glossary_sha256'])
        records.append(record)
        pending.append((item, record))
    # No cache mutation until every submitted record has passed all gates.
    for item, record in pending:
        item.extra['ainiee_pdf']['proofreading'] = record
        item.extra['ainiee_pdf']['source_verification'] = {'status': 'verified', 'evidence': record['evidence']}
    return {'schema': 'pdf-proofreading/1', 'records': records}


def build_translation_manifest(book, target, cf, *, work, cache_path, glossary_path, prompt_path,
                               review_path, decisions_path=None, glossary_schema_path=None):
    config = load_review_config(prompt_path, glossary_path, glossary_schema_path=glossary_schema_path)
    expected = apply_cache_to_book(book, cf)
    if expected != target:
        raise ValueError('Translated book differs from current cache')
    from .cache_io import load_cache
    disk_project = load_cache(str(cache_path))
    disk_files = [f for f in disk_project.files.values()
                  if f.extra.get('ainiee_pdf', {}).get('document_id') == book['document_id']]
    if len(disk_files) != 1 or disk_files[0].to_dict() != cf.to_dict():
        raise ValueError('Current disk cache differs from selected translation cache')
    proofs = json.loads(Path(review_path).read_text(encoding='utf8'))
    if proofs.get('schema') != 'pdf-proofreading/1':
        raise ValueError('Expected independent proofreading artifact')
    records = {r['unit_id']: r for r in proofs['records']}
    if len(records) != len(proofs['records']):
        raise ValueError('Duplicate proofreading artifact unit')
    if decisions_path is None:
        decisions_path = Path(work) / 'pdf-decisions.json'
        if not Path(decisions_path).exists():
            write_json(decisions_path, {'schema': 'pdf-decisions/1', 'revision': book['revision'], 'decisions': []})
    decisions = json.loads(Path(decisions_path).read_text(encoding='utf8'))
    if (decisions.get('schema') != 'pdf-decisions/1' or type(decisions.get('revision')) is not int
            or not 1<=decisions['revision']<=book['revision']):
        raise ValueError('Decision revision mismatch')
    items, bound = _index(cf), {}
    for unit in contract().iter_units(book):
        item = items[unit['unit_id']]
        preserve = unit.get('translation_policy') == 'preserve_source'
        translated = unit['source_text'] if preserve else item.translated_text
        entry = {'source_sha256': unit['source_sha256'], 'target_sha256': contract().content_digest(translated)}
        if preserve:
            entry['translation_policy'] = 'preserve_source'
            entry['policy_evidence'] = unit['policy_evidence']
        record = records.get(unit['unit_id'])
        if (not record or record != item.extra['ainiee_pdf'].get('proofreading')
                or record.get('status') != 'passed' or record.get('independent') is not True
                or record.get('source_sha256') != entry['source_sha256']
                or record.get('source_revision') != unit['source_revision']
                or record.get('target_sha256') != entry['target_sha256']
                or record.get('prompt_sha256') != config['prompt_sha256']
                or record.get('glossary_sha256') != config['glossary_sha256']
                or record.get('provenance') != unit.get('provenance', [])):
            raise ValueError(f'Missing/stale independent proofreading: {unit["unit_id"]}')
        entry['proofreading'] = record
        contract().validate_proof_record(record, unit, source_sha256=book['source_sha256'],
            target_text=translated, prompt_sha256=config['prompt_sha256'],
            glossary_sha256=config['glossary_sha256'])
        entry['source_verified'] = item.extra['ainiee_pdf'].get('source_verification', unit.get('source_verification'))
        bound[unit['unit_id']] = entry
    paths = {'cache': cache_path, 'prompt': prompt_path, 'glossary': glossary_path,
             'proofreading': review_path, 'decisions': decisions_path}
    return {'schema': 'translation-manifest/1', 'document_id': book['document_id'],
        'target_language':target['metadata']['language'],
        'editorial_labels':target['labels'],
        'source_revision': book['revision'], 'source_book_sha256': contract().content_digest(book),
        'translated_book_sha256': contract().content_digest(target),
        **{k: book[k] for k in ('source_sha256', 'raw_sha256', 'review_sha256')},
        'artifacts': {name: {'path': str(Path(path).resolve()), 'sha256': sha256(path)} for name, path in paths.items()},
        'units': bound}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=['export', 'import', 'reconcile'])
    for name in ('book', 'cache', 'work', 'output'):
        parser.add_argument('--' + name, required=True)
    for name in ('prompt', 'glossary', 'glossary-schema', 'context-id', 'translation-context-id',
                 'tasks', 'results', 'source-pdf', 'id-mapping'):
        parser.add_argument('--' + name)
    args = parser.parse_args(argv)
    from .cache_io import load_cache, save_cache, locked
    from .helpers import backup_file
    book = json.loads(Path(args.book).read_text(encoding='utf8'))
    with locked(args.cache):
        project = load_cache(args.cache)
        files = [cf for cf in project.files.values() if cf.extra.get('ainiee_pdf')]
        if len(files) != 1:
            raise ValueError('Select a project with exactly one PDF cache file')
        cf = files[0]
        if args.action == 'reconcile':
            from .pdf_cache import reconcile_cache
            mapping = json.loads(Path(args.id_mapping).read_text(encoding='utf8')) if args.id_mapping else None
            reconciled = reconcile_cache(book, cf, mapping)
            key = next(k for k, value in project.files.items() if value is cf)
            # Existing IDs retain batch indices. Newly introduced unit IDs are
            # allocated above every file in this CacheProject, not just the PDF.
            old_ids = set(_index(cf))
            next_index = max((i.text_index for f in project.files.values() for i in f.items), default=0) + 1
            for item in reconciled.items:
                if item.extra['ainiee_pdf']['unit_id'] not in old_ids:
                    item.text_index = next_index
                    next_index += 1
            indices = [i.text_index for f in project.files.values() if f is not cf for i in f.items]
            indices.extend(i.text_index for i in reconciled.items)
            if len(indices) != len(set(indices)):
                raise ValueError('Duplicate project text_index; repair cache batch indices first')
            project.files[key] = reconciled
            backup_file(args.cache)
            save_cache(project, args.cache)
            write_json(args.output, {'schema': 'pdf-reconcile/1', 'revision': book['revision'],
                                    'id_mapping': mapping or {}})
        elif args.action == 'export':
            tasks = export_review_tasks(book, cf, work=args.work, prompt_path=args.prompt,
                glossary_path=args.glossary, glossary_schema_path=args.glossary_schema,
                context_id=args.context_id, translation_context_id=args.translation_context_id,
                source_pdf_path=args.source_pdf)
            write_json(args.output, tasks)
        else:
            tasks = json.loads(Path(args.tasks).read_text(encoding='utf8'))
            results = json.loads(Path(args.results).read_text(encoding='utf8'))
            ledger = import_review_results(book, cf, tasks, results, work=args.work,
                prompt_path=args.prompt, glossary_path=args.glossary, glossary_schema_path=args.glossary_schema)
            previous = json.loads(Path(args.output).read_text(encoding='utf8')) if Path(args.output).exists() else {'records': []}
            combined = {r['unit_id']: r for r in previous['records']}
            combined.update({r['unit_id']: r for r in ledger['records']})
            ledger['records'] = list(combined.values())
            backup_file(args.cache)
            save_cache(project, args.cache)
            write_json(args.output, ledger)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
