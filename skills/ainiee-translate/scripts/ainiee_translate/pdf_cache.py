"""Stable epub-book/2 cache adapter and content-scoped reconciliation."""
from __future__ import annotations

import copy
from .pdf_bridge import contract
from ._vendor.ModuleFolders.Service.Cache.CacheFile import CacheFile
from ._vendor.ModuleFolders.Service.Cache.CacheItem import CacheItem


def _validated(book):
    if book.get('schema') != 'epub-book/2':
        raise ValueError('PDF translation requires epub-book/2; create a new project from the PDF')
    contract().validate_v2(book)
    return list(contract().iter_units(book))


def _meta(book, unit):
    return dict(version=2, backend='pdf-to-epub', document_id=book['document_id'],
                source_sha256=unit['source_sha256'], source_revision=unit['source_revision'],
                unit_id=unit['unit_id'], chapter_id=unit['chapter_id'],
                block_id=unit.get('block_id'), slot_path=copy.deepcopy(unit['path']),
                structure_sha256=unit.get('structure_sha256'),
                source_refs=copy.deepcopy(unit.get('provenance', [])),
                protected_tokens=copy.deepcopy(unit.get('markers', [])),
                translation_policy=unit.get('translation_policy', 'translate'),
                policy_evidence=unit.get('policy_evidence', ''),
                source_verification=copy.deepcopy(unit.get('source_verification', {'status': 'pending'})))


def book_to_cache_file(book, *, storage_path, target_language='zh'):
    units = _validated(book)
    cf = CacheFile(storage_path=str(storage_path), file_project_type='Pdf')
    cf.extra['ainiee_pdf'] = dict(version=2, backend='pdf-to-epub', document_id=book['document_id'],
        source_sha256=book['source_sha256'], source_revision=book['revision'],
        book_sha256=contract().content_digest(book), target_language=target_language,historical_units=[])
    for unit in units:
        preserve = unit.get('translation_policy') == 'preserve_source'
        cf.items.append(CacheItem(text_index=len(cf.items) + 1, source_text=unit['source_text'],
            translation_status=7 if preserve else 0, extra={'ainiee_pdf': _meta(book, unit)}))
    return cf


def _index(cf):
    result = {}
    for item in cf.items:
        uid = item.extra.get('ainiee_pdf', {}).get('unit_id')
        if not uid or uid in result:
            raise ValueError('Missing/duplicate cache unit ID')
        result[uid] = item
    return result


def _identity(book, cf):
    m = cf.extra.get('ainiee_pdf', {})
    if m.get('version') != 2 or m.get('backend') != 'pdf-to-epub':
        raise ValueError('Legacy PDF cache cannot migrate; create a new epub-book/2 project')
    if m.get('source_sha256') != book['source_sha256'] or m.get('document_id') != book['document_id']:
        raise ValueError('Different PDF/document identity; create a new project')
    return m


def apply_cache_to_book(book, cache_file, *, allow_partial=False):
    units = _validated(book)
    m = _identity(book, cache_file)
    if m.get('book_sha256') != contract().content_digest(book):
        raise ValueError('Source book changed; reconcile cache before applying')
    items = _index(cache_file)
    if set(items) != {u['unit_id'] for u in units}:
        raise ValueError('Cache translation unit set differs from source book')
    target = copy.deepcopy(book)
    missing = []
    for unit in units:
        item = items[unit['unit_id']]
        meta = item.extra['ainiee_pdf']
        if (item.source_text != unit['source_text'] or meta.get('source_sha256') != unit['source_sha256']
                or meta.get('source_revision') != unit['source_revision']):
            raise ValueError('Cache source unit version differs from source book')
        if unit.get('translation_policy') == 'preserve_source':
            text = unit['source_text']
        elif item.translation_status not in (1, 2) or not item.translated_text.strip():
            missing.append(unit['unit_id'])
            text = f"[UNTRANSLATED {unit['unit_id']}]"
        else:
            from .pdf_protection import validate_protected_tokens
            if validate_protected_tokens(unit['source_text'], item.translated_text, expected=unit.get('markers', [])):
                raise ValueError('Translation has damaged protected structure tokens')
            text = item.translated_text
        node = target
        for part in unit['path'][:-1]:
            node = node[part]
        node[unit['path'][-1]] = text
    if missing and not allow_partial:
        raise ValueError(f'Incomplete translation: {len(missing)} untranslated units')
    target['translation'] = {'source_revision': book['revision'], 'missing_units': missing,
                             'diagnostic_draft': bool(missing),'target_language':m.get('target_language','zh')}
    target['metadata']['language']=m.get('target_language','zh')
    target['labels']=contract().localized_labels(m.get('target_language','zh'),book['labels'],m.get('target_labels'))
    return target


def reconcile_cache(book, cache_file, id_mapping=None):
    units = _validated(book)
    old_meta = _identity(book, cache_file)
    old = _index(cache_file)
    fresh = book_to_cache_file(book, storage_path=cache_file.storage_path,target_language=old_meta.get('target_language','zh'))
    new = _index(fresh)
    removed, added = set(old) - set(new), set(new) - set(old)
    # A split commonly retains the first leaf ID and adds another; a merge
    # retains one ID and removes its sibling. Neither has both removed+added.
    def owner(item):
        meta = item.extra['ainiee_pdf']
        return (meta.get('chapter_id'), meta.get('block_id'))
    changed = {uid for uid in set(old) & set(new)
               if old[uid].source_text != new[uid].source_text}
    split_sources = {uid for uid in changed if any(owner(old[uid]) == owner(new[n]) for n in added)}
    merge_targets = {uid for uid in changed if any(owner(new[uid]) == owner(old[n]) for n in removed)}
    split_destinations = {uid for uid in added if any(owner(new[uid]) == owner(old[n]) for n in split_sources)}
    merge_sources = {uid for uid in removed if any(owner(old[uid]) == owner(new[n]) for n in merge_targets)}
    mapping = id_mapping or {}
    if ((removed and added) or split_sources or merge_targets) and not mapping:
        raise ValueError('Split/merge requires explicit ID mapping')
    if mapping:
        if not isinstance(mapping, dict) or any(k not in old for k in mapping):
            raise ValueError('Invalid old unit ID in mapping')
        destinations = set()
        for values in mapping.values():
            values = [values] if isinstance(values, str) else values
            if (not isinstance(values, list) or not values
                    or any(not isinstance(v, str) or v not in new for v in values)):
                raise ValueError('Invalid new unit ID mapping')
            if len(values) != len(set(values)):
                raise ValueError('Duplicate new unit ID in mapping')
            destinations.update(values)
        if not removed.issubset(mapping) or not added.issubset(destinations):
            raise ValueError('Incomplete split/merge ID mapping')
        if (not (split_sources | merge_sources | merge_targets).issubset(mapping)
                or not (split_sources | split_destinations | merge_targets).issubset(destinations)):
            raise ValueError('Split/merge requires complete explicit ID mapping')
    historical = copy.deepcopy(old_meta.get('historical_units', []))
    mapped_new = {v for values in mapping.values() for v in ([values] if isinstance(values, str) else values)}
    next_index = max((i.text_index for i in old.values()), default=0) + 1
    for uid, item in new.items():
        previous = old.get(uid)
        if previous:
            item.text_index = previous.text_index
        else:
            item.text_index = next_index
            next_index += 1
        if previous and uid not in mapping and uid not in mapped_new:
            pm, nm = previous.extra['ainiee_pdf'], item.extra['ainiee_pdf']
            unchanged = all(pm.get(k) == nm.get(k) for k in
                            ('source_sha256', 'source_revision', 'protected_tokens', 'translation_policy', 'source_refs'))
            if unchanged and previous.source_text == item.source_text:
                item.translated_text = previous.translated_text
                item.translation_status = previous.translation_status
                item.model = previous.model
                for key, value in pm.items():
                    if key not in nm:
                        nm[key] = copy.deepcopy(value)
                # Source verification is content-bound, and must survive an
                # unrelated source-book revision just like translation proof.
                nm['source_verification'] = copy.deepcopy(pm.get('source_verification', nm['source_verification']))
                proof = nm.get('proofreading')
                if proof and (proof.get('target_sha256') != contract().content_digest(
                        item.source_text if nm['translation_policy'] == 'preserve_source' else item.translated_text)
                        or proof.get('structure_sha256') != nm.get('structure_sha256')):
                    nm.setdefault('proofreading_history', []).append(
                        {'reason': 'translation_or_structure_changed', 'record': nm.pop('proofreading')})
                continue
        if previous:
            historical.append({'unit_id': uid, 'reason': 'source_changed', 'item': previous.to_dict()})
    for uid in removed:
        historical.append({'unit_id': uid, 'reason': 'removed_or_remapped', 'item': old[uid].to_dict()})
    fresh.extra['ainiee_pdf']['historical_units'] = historical
    fresh.extra['ainiee_pdf']['id_mapping'] = copy.deepcopy(mapping)
    # Routing and project configuration are not new source fingerprints.
    for key, value in old_meta.items():
        if key not in fresh.extra['ainiee_pdf']:
            fresh.extra['ainiee_pdf'][key] = copy.deepcopy(value)
    for key, value in cache_file.extra.items():
        if key != 'ainiee_pdf':
            fresh.extra[key] = copy.deepcopy(value)
    return fresh
