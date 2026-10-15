"""Stable translation-unit mapping. text_index is never a publication identifier."""
from __future__ import annotations

import copy
from pathlib import Path

from .book_model import BookDocument, validate_book
from .mineru_local import digest
from ._vendor.ModuleFolders.Service.Cache.CacheFile import CacheFile
from ._vendor.ModuleFolders.Service.Cache.CacheItem import CacheItem


def book_to_cache_file(book: BookDocument, *, storage_path: str) -> CacheFile:
    validate_book(book)
    cf = CacheFile(storage_path=storage_path, file_project_type='Pdf')
    cf.extra['ainiee_pdf'] = dict(version=1, backend='mineru', source_sha256=book['source_sha256'],
                                 book_source='book.source.json', manifest='extraction.json',
                                 book_sha256=digest(book))
    for block in book['blocks']:
        if not block.get('unit_id'):
            continue
        meta = dict(version=1, unit_id=block['unit_id'], chapter_id=block['chapter_id'],
                    source_refs=copy.deepcopy(block['source_refs']), protected_tokens=block.get('protected_tokens', []),
                    kind=block['kind'])
        cf.items.append(CacheItem(text_index=len(cf.items) + 1, source_text=block['source_text'],
                                  extra={'ainiee_pdf': meta}))
    return cf


def apply_cache_to_book(book: BookDocument, cache_file: CacheFile, *, allow_partial: bool = False) -> BookDocument:
    from .mineru_local import digest
    validate_book(book)
    meta = cache_file.extra.get('ainiee_pdf', {})
    if (meta.get('backend') != 'mineru' or meta.get('source_sha256') != book['source_sha256']
            or meta.get('book_sha256') != digest(book)):
        raise ValueError('Cache source/book fingerprint mismatch')
    items = {}
    for item in cache_file.items:
        uid = item.extra.get('ainiee_pdf', {}).get('unit_id')
        if not uid or uid in items:
            raise ValueError('Missing/duplicate cache unit ID')
        items[uid] = item
    expected = {b['unit_id'] for b in book['blocks'] if b.get('unit_id')}
    if set(items) != expected:
        raise ValueError('Cache translation unit set differs from source book')
    target = copy.deepcopy(book)
    missing = []
    for block in target['blocks']:
        if not block.get('unit_id'):
            continue
        item = items[block['unit_id']]
        if item.source_text != block['source_text']:
            raise ValueError('Cache source text differs from reviewed book')
        if item.translation_status not in (1, 2) or not item.translated_text.strip():
            missing.append(block['unit_id'])
            block['target_text'] = f"[UNTRANSLATED {block['unit_id']}]"
            block['diagnostic_missing'] = True
        else:
            from .pdf_protection import validate_protected_tokens
            if validate_protected_tokens(block['source_text'], item.translated_text, expected=block.get('protected_tokens', [])):
                raise ValueError('Translation has damaged protected structure tokens')
            block['target_text'] = item.translated_text
    if missing and not allow_partial:
        raise ValueError(f'Incomplete translation: {len(missing)} untranslated units')
    target['translation_complete'] = not missing
    target['missing_units'] = missing
    target['diagnostic_draft'] = bool(missing)
    return target
