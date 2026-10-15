"""Versioned, JSON-serializable source/target book, independent of translation caches."""
from __future__ import annotations

from collections import Counter
import copy
import json
from pathlib import Path
import re
from typing import Any, TypeAlias

from .mineru_local import digest, safe_relative, sha256, write_json
from .pdf_publication import validate_publication_input

BookDocument: TypeAlias = dict[str, Any]
_ID = re.compile(r'^[A-Za-z][A-Za-z0-9_.-]*$')


def _unique_ids(rows, label):
    ids = [row.get('id', '') for row in rows]
    if any(not isinstance(i, str) or not _ID.fullmatch(i) for i in ids) or len(ids) != len(set(ids)):
        raise ValueError(f'Invalid or duplicate {label} IDs')
    return set(ids)


def validate_book(book: BookDocument, *, require_translation=False) -> None:
    if book.get('schema') != 'ainiee-book/1' or book.get('source_structure_reviewed') is not True:
        raise ValueError('Book requires reviewed ainiee-book/1 source structure')
    chapters = _unique_ids(book['chapters'], 'chapter')
    blocks = _unique_ids(book['blocks'], 'block')
    notes = _unique_ids(book.get('notes', []), 'note')
    assets = _unique_ids(book.get('assets', []), 'asset')
    if len(chapters | blocks | notes | assets) != len(chapters) + len(blocks) + len(notes) + len(assets):
        raise ValueError('IDs must be unique across book entities')
    units = []
    for block in book['blocks']:
        if block['chapter_id'] not in chapters:
            raise ValueError('Block has unknown chapter')
        if block.get('asset_id') and block['asset_id'] not in assets:
            raise ValueError('Block has unknown asset')
        if block.get('unit_id'):
            units.append(block['unit_id'])
            if not isinstance(block.get('source_text'), str):
                raise ValueError('Translation unit needs source text')
            if require_translation and not block.get('target_text', '').strip():
                raise ValueError('Incomplete translation unit')
    if len(units) != len(set(units)):
        raise ValueError('Duplicate translation unit IDs')
    for note in book.get('notes', []):
        if (note.get('chapter_id') not in chapters or not note.get('block_ids')
                or any(b not in blocks for b in note['block_ids'])
                or not note.get('association_evidence') or not note.get('original_label')):
            raise ValueError('Unresolved note association or missing evidence/original label')
        if any(b['chapter_id'] != note['chapter_id'] for b in book['blocks'] if b['id'] in note['block_ids']):
            raise ValueError('Cross-chapter note body association')
    if any(issue.get('blocking', True) for issue in book.get('issues', [])):
        raise ValueError('Unresolved blocking structure issues')
    if require_translation and not book.get('translation_complete') and not book.get('diagnostic_draft'):
        raise ValueError('Book translation is incomplete')


def normalize_book(work: Path) -> BookDocument:
    work = Path(work).resolve()
    def read(name):
        return json.loads((work / name).read_text(encoding='utf8'))
    inspection, plan, extraction, review = [read(n) for n in (
        'inspection.json', 'publication-input.json', 'extraction.json', 'publication.review.json')]
    source_hash = inspection['source_sha256']
    if sha256(Path(inspection['source_path'])) != source_hash:
        raise ValueError('Source changed since inspection')
    validate_publication_input(plan, source_hash)
    if (extraction.get('status') != 'completed' or extraction['source_sha256'] != source_hash
            or extraction['publication_input_sha256'] != digest(plan)):
        raise ValueError('Extraction is stale for this source/publication input')
    if (review.get('schema') != 'ainiee-pdf-review/1' or review.get('reviewed') is not True
            or not review.get('evidence', '').strip() or review['source_sha256'] != source_hash
            or review['extraction_sha256'] != digest(extraction)):
        raise ValueError('Structure review is unreviewed or stale')
    # Validate immutable imported bytes independently of the review's assertions.
    for imp in extraction['imports']:
        root = work / safe_relative(Path(imp['root']).as_posix())
        if read(str(Path(imp['root']) / 'manifest.json')) != imp['manifest']:
            raise ValueError('Imported manifest changed after extraction')
        for name, expected in imp['manifest']['files'].items():
            path = root / safe_relative(name)
            if not path.is_file() or sha256(path) != expected:
                raise ValueError('Immutable raw extraction changed')
    # Rebuild canonical candidates, rather than trusting editable copies in review.
    from .pdf import extraction_candidates
    candidates = {c['raw_id']: c for c in extraction_candidates(work, extraction)}
    accounted = set()
    blocks = copy.deepcopy(review['blocks'])
    for block in blocks:
        refs = block.get('raw_ids', [])
        if not refs or any(raw_id not in candidates for raw_id in refs):
            raise ValueError('Block has missing/unknown semantic coverage')
        accounted.update(refs)
        block['source_refs'] = [copy.deepcopy(candidates[raw_id]['source_ref']) for raw_id in refs]
        if block.get('source_text', '').strip():
            block['unit_id'] = 'u-' + digest([source_hash, refs, block['id']])[:32]
            block.setdefault('protected_tokens', [])
        block.pop('target_text', None)
    for resolution in review.get('resolutions', []):
        if (resolution.get('raw_id') not in candidates or resolution.get('action') not in ('omitted', 'resolved')
                or not resolution.get('evidence', '').strip()):
            raise ValueError('Invalid semantic resolution evidence')
        accounted.add(resolution['raw_id'])
    if accounted != set(candidates):
        raise ValueError('Unaccounted semantic block coverage; resolve every raw block')
    for asset in review.get('assets', []):
        path = work / safe_relative(asset['path'])
        if not path.is_file() or sha256(path) != asset['sha256']:
            raise ValueError('Missing or changed reviewed asset')
    book = dict(schema='ainiee-book/1', source_sha256=source_hash,
                source_structure_reviewed=True, translation_complete=False,
                metadata=copy.deepcopy(review.get('metadata', {})), chapters=copy.deepcopy(review['chapters']),
                blocks=blocks, notes=copy.deepcopy(review.get('notes', [])), assets=copy.deepcopy(review.get('assets', [])),
                toc=copy.deepcopy(review.get('toc', {})), issues=copy.deepcopy(review.get('issues', [])),
                provenance=dict(work=str(work), extraction_sha256=digest(extraction), review_sha256=digest(review),
                                publication_input_sha256=digest(plan), bookmarks=inspection['bookmarks']))
    bookmarks = {b['bookmark_index']: b for b in inspection['bookmarks']}
    for entry in book['toc'].get('entries', []):
        bookmark = bookmarks.get(entry.get('bookmark_index'))
        if bookmark is None:
            raise ValueError('Unknown PDF bookmark')
        entry['source_title'] = bookmark['source_title']
        entry['source_page_idx'] = bookmark['source_page_idx']
    validate_book(book)
    output = work / 'book.source.json'
    if output.exists() and read('book.source.json') != book:
        raise ValueError('Existing source book differs; preserve existing translations and use a new work directory')
    write_json(output, book)
    return book
