"""Compile reviewed publication policy without guessing page roles or book text.

This module consumes local inspection/provenance only. The resulting copy is
safe to compile again during build; legacy books without a policy are unchanged.
"""
from __future__ import annotations

from copy import deepcopy
from pathlib import Path
import re

from pdf_to_epub import load

EXCLUDED_ROLES = {'cover', 'back-cover', 'belly-band', 'copyright',
                  'publication-info', 'printed-toc', 'term-index'}


def _evidence(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + ' needs explicit evidence')


def _page(value, name):
    if type(value) is not int or value < 1:
        raise ValueError(name + ' needs a positive source page')
    return value


def _items(node):
    if isinstance(node, list):
        for child in node:
            yield from _items(child)
    elif isinstance(node, dict):
        if 'note' in node:
            yield node
        for field in ('inline', 'rows', 'items'):
            if field in node:
                yield from _items(node[field])


def _sources(node, chapter=False):
    result = list(node.get('heading_provenance' if chapter else 'provenance') or [])
    if not chapter and node.get('source_region') and node['source_region'] not in result:
        result.append(node['source_region'])
    if not chapter and node.get('asset'):
        result.append(node['asset'])
    return result


def _bounds(node, chapter=False):
    pages = [s['page'] for s in _sources(node, chapter) if type(s.get('page')) is int]
    if chapter:
        for b in node['blocks']:
            pages.extend(s['page'] for s in _sources(b) if type(s.get('page')) is int)
    return (min(pages), max(pages)) if pages else None


def _check_provenance(book, source_policy):
    excluded = set(source_policy.get('excluded_pages', []))
    retained = source_policy.get('retained_regions') or {}

    def check(source):
        page = source.get('page')
        if page in excluded:
            raise ValueError('Included content uses an excluded source page')
        if str(page) in retained:
            box = source.get('bbox')
            if not isinstance(box, list) or len(box) != 4:
                raise ValueError('Mixed-page content needs source bbox provenance')
            if not any(box[0] >= r['bbox'][0] and box[1] >= r['bbox'][1]
                       and box[2] <= r['bbox'][2] and box[3] <= r['bbox'][3]
                       for r in retained[str(page)]):
                raise ValueError('Included content extends outside a retained source region')

    def node_check(node, chapter=False):
        if node.get('role') in EXCLUDED_ROLES:
            raise ValueError('Excluded publication role remains in included content')
        for source in _sources(node, chapter):
            check(source)
        # Assets in inline/table/list containers also carry source provenance.
        def assets(value):
            if isinstance(value, list):
                for item in value:
                    assets(item)
            elif isinstance(value, dict):
                if value.get('asset'):
                    check(value['asset'])
                for field in ('inline', 'rows', 'items'):
                    if field in value:
                        assets(value[field])
        assets(node)

    for chapter in book['chapters']:
        node_check(chapter, True)
        for block in chapter['blocks']:
            node_check(block)
    for note in book['notes']:
        node_check(note)
        for block in note['blocks']:
            node_check(block)


def _check_reading_order(book):
    """Preserve known chapter/body page order, allowing shared source pages.

    Endnote sources are deliberately excluded: their reviewed chapter association
    moves them to chapter ends. Within-page order remains a review responsibility.
    """
    previous = None
    for chapter in book['chapters']:
        bounds = _bounds(chapter, True)
        if bounds is None:
            continue
        if previous is not None and previous[1] > bounds[0]:
            raise ValueError('Chapter reading order contradicts known body source page order')
        previous = bounds


def _compile_toc(book, config, inspection, source_policy):
    if not isinstance(config, dict) or config.get('source') != 'pdf-bookmarks':
        raise ValueError('Publication TOC must explicitly use pdf-bookmarks')
    _evidence(config.get('evidence'), 'TOC placement')
    original = config.get('original_pages')
    if not isinstance(original, list) or not original:
        raise ValueError('TOC needs recorded original_pages')
    for page in original:
        _page(page, 'Original TOC')
    printed = {e['page'] for e in source_policy.get('exclusions', []) if e['role'] == 'printed-toc'}
    if len(original) != len(set(original)) or set(original) != printed:
        raise ValueError('Original TOC pages must match all printed-toc exclusion evidence')
    bookmarks = inspection.get('bookmarks')
    if not isinstance(bookmarks, list) or not bookmarks:
        raise ValueError('PDF bookmarks are missing; record the problem before publication')
    chapters = {c['id']: c for c in book['chapters']}
    targets = {c['id']: (c, c, True) for c in book['chapters']}
    for chapter in book['chapters']:
        for block in chapter['blocks']:
            if block['kind'] == 'heading':
                targets[block['id']] = (chapter, block, False)
    entries = config.get('entries')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Publication TOC needs reviewed bookmark entries')
    seen = set(); seen_targets = set(); result = []; current = None; previous_index = -1
    for entry in entries:
        index = entry.get('bookmark_index')
        if type(index) is not int or not 0 <= index < len(bookmarks) or index in seen:
            raise ValueError('Invalid or duplicate TOC bookmark_index')
        if index <= previous_index:
            raise ValueError('TOC bookmark order must match the source outline')
        seen.add(index); previous_index = index
        bookmark = bookmarks[index]
        if not isinstance(bookmark, list) or len(bookmark) < 3:
            raise ValueError('Malformed source bookmark')
        native_level, title, page = bookmark[:3]
        if len(bookmark) > 3 and isinstance(bookmark[3], dict):
            destination = bookmark[3]
            if destination.get('uri') or destination.get('file') or destination.get('kind', 1) != 1:
                raise ValueError('Bookmark needs a local PDF page destination')
        _page(page, 'Bookmark target')
        if page in source_policy.get('excluded_pages', []):
            raise ValueError('Bookmark points to excluded content; record an explicit omission')
        if not isinstance(title, str) or not title.strip():
            raise ValueError('Bookmark title is empty')
        source_title = title
        if 'display_title' in entry:
            title = entry['display_title']
            if not isinstance(title, str) or not title.strip():
                raise ValueError('Reviewed bookmark display_title must be nonempty text')
            _evidence(entry.get('title_evidence'), 'Bookmark display title normalization')
        if inspection.get('page_count') and page > inspection['page_count']:
            raise ValueError('Bookmark target is outside the source PDF')
        level = entry.get('level')
        if level not in (1, 2) or type(level) is not int:
            raise ValueError('TOC must have chapter and section levels only')
        if native_level != level:
            _evidence(entry.get('mapping_evidence'), 'Bookmark level remapping')
        target = entry.get('target')
        if target not in targets:
            raise ValueError('TOC bookmark target is missing from included headings')
        if target in seen_targets:
            raise ValueError('Duplicate bookmark heading target needs explicit source resolution')
        seen_targets.add(target)
        chapter, node, is_chapter = targets[target]
        if level == 1:
            if not is_chapter:
                raise ValueError('Level-one TOC target must be a chapter')
            current = {'title': title, 'source_title': source_title,
                       'title_evidence': entry.get('title_evidence'), 'href': chapter['id'] + '.xhtml#' + target,
                       'target': target, 'chapter': chapter['id'], 'bookmark_index': index,
                       'source_page': page, 'sections': []}
            result.append(current)
        else:
            if is_chapter or current is None or current['chapter'] != chapter['id']:
                raise ValueError('Section TOC entry must belong to its preceding chapter')
            current['sections'].append({'title': title, 'source_title': source_title,
                                        'title_evidence': entry.get('title_evidence'), 'href': chapter['id'] + '.xhtml#' + target,
                                        'target': target, 'bookmark_index': index, 'source_page': page})
        source_pages = {s['page'] for s in _sources(node, is_chapter) if type(s.get('page')) is int}
        if page not in source_pages:
            _evidence(entry.get('mapping_evidence'), 'Bookmark source-to-heading page mapping')
    for omitted in config.get('omissions', []):
        index = omitted.get('bookmark_index')
        if type(index) is not int or not 0 <= index < len(bookmarks) or index in seen:
            raise ValueError('Invalid or duplicate omitted bookmark')
        _evidence(omitted.get('reason'), 'Bookmark omission reason')
        _evidence(omitted.get('evidence'), 'Bookmark omission')
        seen.add(index)
    if seen != set(range(len(bookmarks))):
        raise ValueError('Source bookmarks need entries or explicit omission evidence')
    placement = config.get('placement')
    if not isinstance(placement, dict):
        raise ValueError('TOC needs an explicit original-order placement')
    order = [c['id'] for c in book['chapters']]
    lower = upper = None
    if set(placement) in ({'before'}, {'after'}):
        key = next(iter(placement)); cid = placement[key]
        if cid not in chapters:
            raise ValueError('TOC placement refers to missing chapter')
        at = order.index(cid) + (key == 'after')
        if at: lower = _bounds(chapters[order[at - 1]], True)
        if at < len(order): upper = _bounds(chapters[order[at]], True)
    elif set(placement) == {'chapter', 'before_block'}:
        cid = placement['chapter']
        if cid not in chapters:
            raise ValueError('TOC placement refers to missing chapter')
        blocks = chapters[cid]['blocks']; ids = [b['id'] for b in blocks]
        if placement['before_block'] not in ids:
            raise ValueError('TOC placement refers to missing block')
        at = ids.index(placement['before_block'])
        heading_pages = [s['page'] for s in _sources(chapters[cid], True) if type(s.get('page')) is int]
        lower = _bounds(blocks[at - 1]) if at else ((min(heading_pages), max(heading_pages)) if heading_pages else None)
        upper = _bounds(blocks[at])
    else:
        raise ValueError('Invalid TOC placement shape')
    # Page boundaries may coincide for a mixed page; explicit placement evidence
    # records the region/order. Contradictory known page order is never accepted.
    if lower and lower[1] > min(original) or upper and upper[0] < max(original):
        raise ValueError('TOC placement contradicts the recorded original page order')
    return {'entries': result, 'placement': deepcopy(placement), 'original_pages': original,
            'evidence': config['evidence'], 'source': 'pdf-bookmarks'}


def _compile_notes(book):
    notes = {n['id']: n for n in book['notes']}
    order = []; labels = {}; refs = {}; owners = {}
    for chapter in book['chapters']:
        number = 0
        for block in chapter['blocks']:
            for ref in _items(block):
                nid = ref['note']
                if nid not in notes:
                    raise ValueError('Missing note body: ' + str(nid))
                if notes[nid]['chapter'] != chapter['id']:
                    refs.setdefault(nid, []).append(ref['id'])
                    continue
                if nid not in labels:
                    number += 1; labels[nid] = str(number); order.append(nid); owners[nid] = chapter['id']
                refs.setdefault(nid, []).append(ref['id'])
    if set(notes) != set(labels):
        raise ValueError('Publication notes need a verified body-first reference')
    for note in notes.values():
        _evidence(note.get('association_evidence'), 'Note association')
        note.setdefault('original_label', note.get('label'))
        note['label'] = labels[note['id']]
    for group in book['chapters'] + book['notes']:
        for block in group['blocks']:
            for ref in _items(block):
                if ref['note'] not in labels:
                    raise ValueError('Missing note body: ' + str(ref['note']))
                ref.setdefault('original_label', ref.get('label', notes[ref['note']].get('original_label')))
                ref['label'] = labels[ref['note']]; ref['placement'] = 'super'
    book['notes'] = [notes[nid] for nid in order]
    return [{'id': nid, 'chapter': owners[nid], 'label': labels[nid],
             'original_label': notes[nid].get('original_label'), 'body_reference_ids': refs[nid],
             'association_evidence': notes[nid].get('association_evidence')} for nid in order]


def apply_publication(book, work):
    """Return a policy-compiled copy; errors identify unresolved structure only."""
    book = deepcopy(book)
    policy = (book.get('structure_rules') or {}).get('publication')
    if policy is None:
        if book.get('publication_input'):
            raise ValueError('Reviewed extraction exclusions require a publication policy')
        if book.get('schema')=='epub-book/2': _compile_notes(book)
        return book
    if not isinstance(policy, dict):
        raise ValueError('Publication policy must be an object')
    work = Path(work)
    inspection = load(work / 'inspection.json')
    source_policy = book.get('publication_input')
    if not isinstance(source_policy, dict):
        raise ValueError('Publication policy needs the reviewed extraction exclusion plan')
    if inspection.get('source_sha256') != book['source_sha256'] or source_policy.get('source_sha256') != book['source_sha256']:
        raise ValueError('Publication inspection/exclusion source hash mismatch')
    _check_provenance(book, source_policy)
    _check_reading_order(book)
    toc = _compile_toc(book, policy.get('toc'), inspection, source_policy)
    images = []; roles = set(); image_ids = set()
    excluded_roles = {(item['page'], item['role']) for item in source_policy.get('exclusions', [])}
    for image in policy.get('images', []):
        role = image.get('role')
        if role not in {'cover', 'back-cover'} or role in roles:
            raise ValueError('Publication images allow one cover and one back-cover')
        roles.add(role); _evidence(image.get('evidence'), 'Packaging image')
        spec = image.get('asset')
        if not isinstance(spec, dict):
            raise ValueError('Packaging image needs an asset')
        ident = spec.get('id')
        if not isinstance(ident, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', ident) or ident in image_ids:
            raise ValueError('Packaging image needs a unique safe asset ID')
        image_ids.add(ident)
        page = _page(spec.get('page'), 'Packaging image')
        if (page, role) not in excluded_roles:
            raise ValueError('Packaging image must match its excluded source page role')
        if spec.get('path') and not re.fullmatch(r'[0-9a-fA-F]{64}', str(spec.get('sha256', ''))):
            raise ValueError('Returned packaging image needs a sha256')
        if spec.get('tex') or spec.get('xref') or spec.get('bbox'):
            raise ValueError('Packaging image must preserve the full source page')
        spec = deepcopy(spec); spec['alt'] = '封面' if role == 'cover' else '封底'
        images.append({'role': role, 'asset': spec, 'evidence': image['evidence'],
                       'file': 'publication-' + role + '.xhtml'})
    missing = {role for page, role in excluded_roles if role in {'cover', 'back-cover'}} - roles
    if missing:
        raise ValueError('Identified cover/back-cover needs its retained image asset')
    images.sort(key=lambda image: 0 if image['role'] == 'cover' else 1)
    book['publication'] = {'schema': 'epub-publication/1', 'toc': toc, 'images': images,
                           'note_numbering': _compile_notes(book),
                           'exclusions': deepcopy(source_policy.get('exclusions', []))}
    return book
