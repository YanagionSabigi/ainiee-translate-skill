#!/usr/bin/env python3
"""Import preserved MinerU result bundles into pdf-raw/1 without network calls.

Supported contracts: legacy pdf_info middle/layout JSON, Content List V1/V2,
and docvortex.middle 2.0. Model output is evidence, never reading content.
All semantic/TeX candidates remain unverified until source comparison.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
import stat
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

MAX_FILE_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILES = 50000
_AUX = {'header', 'footer', 'page_header', 'page_footer', 'page_number', 'aside_text', 'page_aside_text'}
_STYLE = {'bold': 'bold', 'italic': 'italic', 'underline': 'underline', 'emphasis': 'emphasis-dot',
          'emphasis-dot': 'emphasis-dot', 'superscript': 'sup', 'subscript': 'sub', 'sup': 'sup', 'sub': 'sub'}
_BODY = {'image_body', 'table_body', 'chart_body', 'equation', 'interline_equation'}
_KNOWN = _AUX | _BODY | {'text', 'paragraph', 'ref_text', 'title', 'doc_title', 'paragraph_title', 'abstract',
    'page_footnote', 'footnote', 'image', 'table', 'chart', 'code', 'code_body', 'algorithm_body',
    'image_caption', 'image_footnote', 'table_caption', 'table_footnote', 'chart_caption', 'chart_footnote',
    'code_caption', 'code_footnote', 'list', 'index', 'equation_inline', 'inline_equation'}


def _sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def _name(value):
    """Reject Windows aliases as well as POSIX traversal before writing files."""
    if not isinstance(value, str) or not value or '\\' in value or '\x00' in value:
        raise ValueError(f'Unsafe MinerU bundle path: {value!r}')
    path = PurePosixPath(value)
    if path.is_absolute() or ':' in value or any(p in {'', '.', '..'} for p in value.split('/')):
        raise ValueError(f'Unsafe MinerU bundle path: {value!r}')
    for part in path.parts:
        if part.rstrip(' .') != part or re.fullmatch(r'(?i)(CON|PRN|AUX|NUL|COM[1-9]|LPT[1-9])(?:\..*)?', part):
            raise ValueError(f'Unsafe Windows bundle path: {value!r}')
    return path.as_posix()


def _regular(path):
    info = path.lstat()
    if stat.S_ISLNK(info.st_mode) or getattr(info, 'st_file_attributes', 0) & getattr(stat, 'FILE_ATTRIBUTE_REPARSE_POINT', 1024):
        raise ValueError(f'Symlink/reparse point in MinerU bundle: {path.name}')
    return info


def _within(path, work):
    if not path.resolve().is_relative_to(work):
        raise ValueError('MinerU import directory escapes work directory')
    current = path
    while current != work and current.is_relative_to(work):
        if current.exists():
            _regular(current)
        current = current.parent


def _preserve(result_path, work):
    """Validate the entire input before materialization; immutable hash-addressed copy."""
    incoming = Path(result_path).absolute()
    _regular(incoming)
    source = incoming.resolve()
    files, total, seen = [], 0, set()

    def add(name, size, origin):
        nonlocal total
        name = _name(name)
        if name.casefold() in seen:
            raise ValueError('Duplicate/aliased MinerU bundle entry: ' + name)
        seen.add(name.casefold())
        total += size
        if size > MAX_FILE_BYTES or total > MAX_TOTAL_BYTES or len(files) >= MAX_FILES:
            raise ValueError('MinerU bundle exceeds import size/file limits')
        files.append((name, size, origin))

    archive = None
    if source.is_dir():
        _regular(source)
        for folder, dirs, names in os.walk(source, followlinks=False):
            for name in dirs:
                _regular(Path(folder) / name)
            for name in names:
                path = Path(folder) / name
                info = _regular(path)
                if not stat.S_ISREG(info.st_mode):
                    raise ValueError('Nonregular MinerU bundle entry: ' + name)
                add(path.relative_to(source).as_posix(), info.st_size, path)
        files.sort(key=lambda item: item[0])
        hashes = [(name, size, _sha(path)) for name, size, path in files]
        bundle_hash = hashlib.sha256(json.dumps(hashes, ensure_ascii=False).encode()).hexdigest()
    elif source.is_file() and zipfile.is_zipfile(source):
        _regular(source)
        archive = zipfile.ZipFile(source)
        try:
            directory_names = set()
            for item in archive.infolist():
                # ZipInfo normalizes backslashes on Windows, but orig_filename
                # retains the wire spelling and must be validated first.
                _name(item.orig_filename.rstrip('/') if item.is_dir() else item.orig_filename)
                mode = item.external_attr >> 16
                if stat.S_ISLNK(mode) or (stat.S_IFMT(mode) not in {0, stat.S_IFREG, stat.S_IFDIR}):
                    raise ValueError('Nonregular/symlink MinerU ZIP entry: ' + item.filename)
                if item.flag_bits & 1:
                    raise ValueError('Encrypted MinerU ZIP entries are unsupported')
                if item.is_dir():
                    directory_name = _name(item.filename.rstrip('/')).casefold()
                    if directory_name in directory_names or directory_name in seen:
                        raise ValueError('Duplicate/aliased MinerU ZIP directory entry')
                    directory_names.add(directory_name)
                    continue
                if item.filename.casefold() in directory_names:
                    raise ValueError('File/directory alias in MinerU ZIP bundle')
                add(item.filename, item.file_size, item)
            bundle_hash = _sha(source)
            hashes = []
        except Exception:
            archive.close()
            raise
    else:
        raise ValueError('MinerU result must be a ZIP bundle or a result directory')
    if not files:
        if archive:
            archive.close()
        raise ValueError('Empty MinerU result bundle')
    imports = work / 'mineru' / 'imports'
    destination = imports / bundle_hash
    _within(destination, work)
    imports.mkdir(parents=True, exist_ok=True)
    try:
        if destination.exists():
            manifest_path = destination / 'import-manifest.json'
            _within(manifest_path, work)
            if not manifest_path.is_file():
                raise ValueError('Incomplete MinerU import already exists; preserve it for inspection')
            manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
            if manifest.get('bundle_sha256') != bundle_hash or len(manifest.get('files', [])) != len(files):
                raise ValueError('MinerU import manifest mismatch')
            expected_names = {name for name, _, _ in files}
            if {item['path'] for item in manifest['files']} != expected_names:
                raise ValueError('MinerU import manifest file list mismatch')
            for item in manifest['files']:
                preserved = destination / 'originals' / _name(item['path'])
                _within(preserved, work)
                if not preserved.is_file() or _sha(preserved) != item['sha256']:
                    raise ValueError('Preserved MinerU original changed: ' + item['path'])
            # Bind preserved bytes to the input too; a rewritten manifest cannot
            # make edited originals appear to be the same result bundle.
            recorded = {item['path']: item['sha256'] for item in manifest['files']}
            for name, size, origin in files:
                if archive:
                    hasher = hashlib.sha256()
                    with archive.open(origin) as stream:
                        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
                            hasher.update(chunk)
                    expected_hash = hasher.hexdigest()
                else:
                    expected_hash = _sha(origin)
                if recorded[name] != expected_hash:
                    raise ValueError('Preserved MinerU original differs from input: ' + name)
            return destination / 'originals', manifest
        with tempfile.TemporaryDirectory(prefix='import-', dir=imports) as temp:
            stage = Path(temp) / bundle_hash
            originals = stage / 'originals'
            originals.mkdir(parents=True)
            records = []
            for name, size, origin in files:
                target = originals / name
                target.parent.mkdir(parents=True, exist_ok=True)
                with (archive.open(origin) if archive else origin.open('rb')) as inp, target.open('wb') as out:
                    copied = 0
                    while chunk := inp.read(1024 * 1024):
                        copied += len(chunk)
                        if copied > size or copied > MAX_FILE_BYTES:
                            raise ValueError('MinerU entry exceeded declared size: ' + name)
                        out.write(chunk)
                if copied != size:
                    raise ValueError('MinerU entry size mismatch: ' + name)
                records.append({'path': name, 'size': size, 'sha256': _sha(target)})
            manifest = {'schema': 'mineru-import/1', 'bundle_sha256': bundle_hash, 'files': records}
            (stage / 'import-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
            stage.rename(destination)
        return destination / 'originals', manifest
    finally:
        if archive:
            archive.close()


def _read_formats(root):
    documents = []
    for path in sorted(root.rglob('*.json')):
        name = path.name.lower()
        rich = name in {'layout.json', 'middle.json', 'middle_json.json'} or name.endswith('_middle.json')
        content = name == 'content_list.json' or name.endswith('_content_list.json') or name.endswith('content_list_v2.json')
        structured = name == 'structured_content.json'
        if not (rich or content or structured):
            continue
        try:
            data = json.loads(path.read_text(encoding='utf-8-sig'))
        except (UnicodeError, json.JSONDecodeError) as exc:
            raise ValueError('Invalid MinerU result JSON: ' + path.name) from exc
        if isinstance(data, dict) and 'schema' in data:
            if data['schema'] == 'docvortex.model':
                continue
            if data.get('schema') != 'docvortex.middle' or data.get('schema_version') != '2.0':
                raise ValueError(f'Unsupported MinerU schema {data.get("schema")!r} version {data.get("schema_version")!r}')
            documents.append((0, path, data, 'docvortex.middle/2.0'))
        elif rich and isinstance(data, dict) and isinstance(data.get('pdf_info'), list):
            documents.append((1, path, data, 'legacy-pdf_info'))
        elif content and isinstance(data, list):
            documents.append((3 if 'v2' in name else 2, path, data, 'content-list-v2' if 'v2' in name else 'content-list-v1'))
        elif structured and isinstance(data, dict) and isinstance(data.get('pages'), list) and data.get('metadata', {}).get('producer', {}).get('name', '').lower() == 'mineru':
            documents.append((4, path, data, 'mineru-structured-content'))
        elif rich:
            raise ValueError('Unsupported/unidentified MinerU layout schema: ' + path.name)
    if not documents:
        raise ValueError('No postprocessed MinerU middle/layout/content-list result found; model/Markdown alone cannot be imported')
    documents.sort(key=lambda item: (item[0], str(item[1])))
    rank = documents[0][0]
    same_rank = [item for item in documents if item[0] == rank]
    if any(item[2] != same_rank[0][2] for item in same_rank[1:]):
        raise ValueError('Bundle contains multiple documents; import each document separately')
    return documents[0], [{'path': p.relative_to(root).as_posix(), 'format': fmt} for _, p, _, fmt in documents]


def _number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def _box(value):
    return isinstance(value, (list, tuple)) and len(value) == 4 and all(_number(x) for x in value) and value[0] < value[2] and value[1] < value[3]


def _kind(value):
    if value in {'title', 'doc_title', 'paragraph_title'}:
        return 'heading'
    if value in {'equation', 'interline_equation'}:
        return 'formula'
    if value in {'image', 'chart'}:
        return 'figure'
    return value


class _PageImporter:
    def __init__(self, root, work, document_path, fmt, page, region, coordinate_size, unit):
        self.root, self.work, self.path, self.fmt = root, work, document_path, fmt
        self.page, self.region, self.size, self.unit = page, region, coordinate_size, unit
        self.blocks = []
        self.issues = region['issues']
        self.counter = 0

    def geometry(self, value, fallback=None):
        clip = self.region['bbox']
        if self.unit.startswith('ambiguous') or not _box(value):
            return list(fallback or clip), False
        width, height = self.size
        if value[0] < -.01 or value[1] < -.01 or value[2] > width + .01 or value[3] > height + .01:
            self.issues.append('MinerU bbox outside declared coordinate space; fallback crop needs manual geometry verification')
            return list(fallback or clip), False
        sx, sy = (clip[2] - clip[0]) / width, (clip[3] - clip[1]) / height
        return [clip[0] + value[0] * sx, clip[1] + value[1] * sy,
                clip[0] + value[2] * sx, clip[1] + value[3] * sy], True

    def asset(self, record, bbox, aid, verified):
        result = {'id': aid, 'page': self.page, 'bbox': bbox, 'alt': '', 'crop_geometry_verified': verified}
        ref = next((record.get(k) for k in ['image_path', 'img_path', 'path'] if record.get(k)), None)
        if ref:
            try:
                name = _name(ref)
                candidates = [self.path.parent / name, self.root / name]
                found = next((p for p in candidates if p.resolve().is_relative_to(self.root.resolve()) and p.is_file()), None)
                if found:
                    _within(found, self.work)
                    result['path'] = found.relative_to(self.work).as_posix()
                else:
                    self.issues.append('MinerU referenced asset missing: ' + name + '; source crop retained')
            except ValueError:
                self.issues.append('Unsafe/nonlocal MinerU asset reference retained only in original record; no URL fetched')
        if record.get('image_url') or record.get('image_base64'):
            self.issues.append('MinerU non-file image reference retained as evidence; no remote URL fetched or base64 trusted')
        return result

    def line(self, original, block, bid, bbox, role, pointer, force_asset=False):
        line_bbox, precise = self.geometry(original.get('bbox'), bbox)
        spans = original.get('spans')
        if spans is None:
            spans = original.get('content', original.get('text', ''))
            if isinstance(spans, str):
                spans = [{'type': 'text', 'content': spans}]
            elif not isinstance(spans, list):
                spans = []
        if force_asset:
            spans = [{'type': role, **original}]
        raw_spans, candidates, offset = [], [], 0
        unknown = []

        def append(span):
            nonlocal offset
            if isinstance(span, str):
                span = {'type': 'text', 'content': span}
            if not isinstance(span, dict):
                unknown.append(span)
                return
            typ = span.get('type', 'text')
            if typ == 'hyperlink' and isinstance(span.get('content'), list):
                start = offset
                for child in span['content']:
                    append(child)
                candidates.append({'type': 'hyperlink', 'start': start, 'end': offset, 'url': span.get('url'), 'verified': False})
                return
            is_asset = typ in {'equation_inline', 'inline_equation', 'equation', 'interline_equation', 'image', 'table', 'chart'} or force_asset
            content = span.get('content', span.get('text', ''))
            if not isinstance(content, str):
                unknown.append(span)
                return
            text = '\ufffc' if is_asset else content
            box, exact = self.geometry(span.get('bbox'), line_bbox)
            styles = []
            for style in span.get('styles', []):
                if style in _STYLE:
                    styles.append(_STYLE[style])
                else:
                    self.issues.append('Unsupported MinerU text style retained in source record: ' + str(style))
            raw = {'text': text, 'styles': list(dict.fromkeys(styles)), 'bbox': box, 'mineru_type': typ}
            for keys, target in [(['font', 'font_name'], 'font'), (['size', 'font_size'], 'size'), (['confidence', 'score'], 'confidence')]:
                for key in keys:
                    if key in span:
                        raw[target] = span[key]
                        break
            raw_spans.append(raw)
            if is_asset:
                aid = f'{bid}-line-{len(self.region["lines"]) + 1:04d}-asset-{len(candidates) + 1}'
                asset = self.asset(span, box, aid, exact or precise)
                if typ in {'equation_inline', 'inline_equation', 'equation', 'interline_equation'} or role in {'equation', 'interline_equation'}:
                    asset.update({'candidate_tex': content, 'tex_verified': False})
                    if typ in {'equation_inline', 'inline_equation'} and not exact:
                        asset['crop_geometry_verified'] = False
                        self.issues.append('Inline MinerU formula has no precise bbox; locate formula before using block crop')
                if typ in {'table', 'table_body'} or role == 'table_body':
                    asset['candidate_html'] = span.get('html', content)
                candidates.append({'type': typ, 'start': offset, 'end': offset + len(text), 'asset': asset})
            offset += len(text)

        for span in spans:
            append(span)
        if unknown:
            self.issues.append('Unknown MinerU span content retained in original line; manual recovery needed')
        lid = f'{self.region["id"]}-l{len(self.region["lines"]) + 1:04d}'
        result = {'id': lid, 'bbox': line_bbox, 'block': bid, 'spans': raw_spans,
                  'confidence': original.get('confidence', original.get('score')),
                  'source': {'page': self.page, 'bbox': line_bbox, 'method': 'mineru'},
                  'role': role, 'type': role, 'discard_candidate': role in _AUX,
                  'mineru_record': {'pointer': pointer, 'line': original},
                  'geometry': {'coordinate_unit': self.unit, 'precise_line_bbox': precise}}
        if candidates:
            result['mineru_inline'] = candidates
        if unknown:
            result['issues'] = ['Unknown spans require manual recovery; exact originals retained']
        self.region['lines'].append(result)
        return result

    def block(self, block, pointer, parent=None, discarded=False):
        if not isinstance(block, dict):
            self.issues.append('Nonobject MinerU block retained in original JSON; manual recovery needed')
            return None
        self.counter += 1
        bid = f'mineru-{self.region["id"]}-b{self.counter:04d}'
        typ = str(block.get('type', 'unknown'))
        bbox, precise = self.geometry(block.get('bbox'))
        semantic = {'id': bid, 'type': _kind(typ), 'mineru_type': typ, 'page': self.page,
                    'bbox': bbox, 'sources': [], 'mineru_record': {'pointer': pointer, 'block': block},
                    'geometry': {'coordinate_unit': self.unit, 'precise_block_bbox': precise}}
        if parent:
            semantic['parent_id'] = parent
        if discarded or typ in _AUX:
            semantic['discard_candidate'] = True
        level = block.get('level', block.get('text_level', block.get('heading_level')))
        if level is not None:
            semantic['heading_level'] = level
            if typ in {'text', 'paragraph'} and _number(level) and level > 0:
                semantic['type'] = 'heading'
        if typ not in _KNOWN:
            semantic['issues'] = ['Unknown MinerU block type retained; semantic classification needs review']
            self.issues.extend(semantic['issues'])
        self.blocks.append(semantic)
        content = block.get('content')
        children = block.get('blocks')
        if children is None and isinstance(content, list) and any(isinstance(v, dict) and v.get('type') in _KNOWN - {'text', 'equation_inline', 'inline_equation'} for v in content):
            # Text spans share the text discriminator; container role determines it.
            if typ in {'image', 'table', 'chart', 'code', 'list', 'index'}:
                children = content
        if typ in {'list', 'index'} and isinstance(content, list):
            children = content
        if isinstance(children, list):
            semantic['container'] = True
            semantic['children'] = []
            captions, footnotes, items = [], [], []
            for i, child in enumerate(children):
                record = self.block(child, f'{pointer}/content/{i}' if 'blocks' not in block else f'{pointer}/blocks/{i}', bid, discarded)
                if not record:
                    continue
                semantic['children'].append(record['id'])
                semantic['sources'].extend(record['sources'])
                if record['mineru_type'].endswith('_caption'):
                    captions.extend(record['sources'])
                if record['mineru_type'].endswith('_footnote'):
                    footnotes.extend(record['sources'])
                if typ in {'list', 'index'}:
                    items.append(record['sources'])
                if record.get('asset') and record['mineru_type'].endswith('_body'):
                    semantic['asset'] = record['asset']
                if record.get('table_html'):
                    semantic['table_html'] = record['table_html']
            if captions:
                semantic['caption_sources'] = captions
            if footnotes:
                semantic['footnote_sources'] = footnotes
            if items:
                semantic['items'] = items
        else:
            lines = block.get('lines')
            source_has_lines = isinstance(lines, list)
            if not isinstance(lines, list):
                if typ in {'list', 'index'} and isinstance(block.get('list_items'), list):
                    lines = [{'content': item} for item in block['list_items']]
                else:
                    lines = [block]
            for i, line in enumerate(lines):
                if not isinstance(line, dict):
                    line = {'content': line}
                visual = typ in _BODY or typ in {'image', 'table', 'chart'}
                line_pointer = f'{pointer}/lines/{i}' if source_has_lines else pointer
                raw_line = self.line(line, block, bid, bbox, typ, line_pointer, force_asset=visual and 'spans' not in line)
                raw_line['discard_candidate'] = discarded or typ in _AUX
                if 'heading_level' in semantic:
                    raw_line['heading_level'] = semantic['heading_level']
                semantic['sources'].append(raw_line['id'])
                for candidate in raw_line.get('mineru_inline', []):
                    if 'asset' in candidate and visual:
                        semantic.setdefault('asset', candidate['asset'])
            if typ in {'list', 'index'}:
                semantic['items'] = [[lid] for lid in semantic['sources']]
        if typ == 'table_body' or typ == 'table':
            html = block.get('html', block.get('table_body', block.get('content')))
            if isinstance(html, str):
                semantic['table_html'] = html
            if not semantic.get('table_html'):
                for original_line in block.get('lines', []):
                    for span in original_line.get('spans', []):
                        if span.get('html'):
                            semantic['table_html'] = span['html']
        if not precise:
            semantic.setdefault('issues', []).append('Block bbox missing/invalid; region fallback requires manual geometry evidence')
        return semantic


def _content_block(item, v2=False):
    """Adapt the documented flattened consumer formats without parsing Markdown."""
    block = dict(item)
    typ = block.get('type', 'unknown')
    payload = block.get('content') if v2 else block
    payload = payload if isinstance(payload, dict) else {}
    if v2:
        keys = [typ + '_content', 'title_content', 'paragraph_content']
        for key in keys:
            if isinstance(payload.get(key), (str, list)):
                block['content'] = payload[key]
                break
        if 'level' in payload:
            block['level'] = payload['level']
        for key in ['list_items', 'attribute', 'list_type']:
            if key in payload:
                block[key] = payload[key]
    if typ in {'image', 'table', 'chart', 'code'}:
        children = []
        body = payload.get(typ + '_body', payload.get('content', payload.get('html', '')))
        if isinstance(body, dict):
            body_record = dict(body)
        else:
            body_record = {'content': body if isinstance(body, str) else ''}
        body_record.update({'type': typ + '_body', 'bbox': item.get('bbox')})
        for key in ['img_path', 'image_path', 'html']:
            if key in payload:
                body_record[key] = payload[key]
            elif key in item:
                body_record[key] = item[key]
        children.append(body_record)
        for role in ['caption', 'footnote']:
            values = payload.get(typ + '_' + role, item.get(typ + '_' + role, []))
            if isinstance(values, str):
                values = [values]
            for value in values or []:
                children.append({'type': typ + '_' + role, 'content': value})
        block['blocks'] = children
    elif typ == 'equation':
        block['content'] = payload.get('equation_content', item.get('text', payload.get('content', '')))
    elif typ in {'list', 'index'}:
        block['list_items'] = [v.get('item_content', '') if isinstance(v, dict) else v for v in payload.get('list_items', [])]
        block.pop('content', None)
    elif 'content' not in block:
        block['content'] = item.get('text', '')
    return block


def read_bundle(result_path, work, source_pdf, page_map=None, source_boxes=None):
    """Return pdf-raw/1; preserve originals under WORK/mineru/imports/<hash>/.

    page_map maps zero-based pages of an explicitly created derivative PDF to
    one-based physical pages of source_pdf. source_boxes, when supplied, are
    matching source-PDF crop rectangles. No offset or selected-page guess occurs.
    This function does not write raw.json, state.json, or a review plan.
    """
    try:
        import pymupdf
    except ImportError as exc:
        raise ValueError('PyMuPDF is required to verify source page geometry') from exc
    work = Path(work).resolve()
    work.mkdir(parents=True, exist_ok=True)
    source_pdf = Path(source_pdf).resolve()
    with pymupdf.open(source_pdf) as source:
        dimensions = [(p.rect.width, p.rect.height) for p in source]
    count = len(dimensions)
    if not count:
        raise ValueError('Source PDF has no pages')
    if page_map is not None:
        if not isinstance(page_map, (list, tuple)) or not page_map or any(not isinstance(p, int) or isinstance(p, bool) or not 1 <= p <= count for p in page_map):
            raise ValueError('page_map must explicitly list valid one-based source PDF pages')
        page_map = list(page_map)
        if len(set(page_map)) != len(page_map) and source_boxes is None:
            raise ValueError('Repeated source pages require explicit source_boxes')
    if source_boxes is not None and (page_map is None or len(source_boxes) != len(page_map)):
        raise ValueError('source_boxes requires a matching explicit page_map')
    root, manifest = _preserve(result_path, work)
    (_, document_path, data, fmt), formats = _read_formats(root)
    content_format = fmt.startswith('content-list')
    if content_format:
        indexes = list(range(len(page_map) if page_map is not None else count))
        items = {idx: [] for idx in indexes}
        if fmt == 'content-list-v2':
            if len(data) != len(indexes):
                raise ValueError('Content List V2 page count does not match explicit/source pages')
            for idx, group in enumerate(data):
                if not isinstance(group, list):
                    raise ValueError('Content List V2 must contain lists grouped by page')
                items[idx] = group
        else:
            positions = {idx: [] for idx in indexes}
            for position, item in enumerate(data):
                idx = item.get('page_idx') if isinstance(item, dict) else None
                if not isinstance(idx, int) or isinstance(idx, bool) or idx not in items:
                    raise ValueError('Content List item lacks valid explicit zero-based page_idx')
                items[idx].append(item)
                positions[idx].append('/' + str(position))
        page_records = [{'page_idx': idx, 'blocks': items[idx],
                         'block_pointers': [f'/{idx}/{bi}' for bi in range(len(items[idx]))] if fmt == 'content-list-v2' else positions[idx]}
                        for idx in indexes]
    else:
        page_records = data['pdf_info'] if fmt == 'legacy-pdf_info' else data.get('pages')
        if not isinstance(page_records, list) or not page_records:
            raise ValueError('MinerU result has no page records')
        indexes = [p.get('page_idx') if isinstance(p, dict) else None for p in page_records]
        if any(not isinstance(idx, int) or isinstance(idx, bool) or idx < 0 for idx in indexes) or indexes != sorted(set(indexes)):
            raise ValueError('MinerU page_idx must be unique, increasing zero-based physical pages')
        if page_map is not None and indexes != list(range(len(page_map))):
            raise ValueError('MinerU derivative page count/indexes do not match page_map; blank pages cannot be inferred')
        if page_map is None and any(idx >= count for idx in indexes):
            raise ValueError('MinerU page_idx is outside source PDF; supply explicit derivative page_map')
        if page_map is None and data.get('is_full_document') is True and indexes != list(range(count)):
            raise ValueError('Full-document MinerU page count does not match source PDF')
    layout = data.get('extensions', {}).get('docvortex_layout', {}) if isinstance(data, dict) else {}
    layout_pages = layout.get('pages', [])
    geometry = {}
    if layout_pages:
        if layout.get('version') != 1:
            raise ValueError('Unsupported docvortex_layout version')
        for record in layout_pages:
            idx = record.get('page_idx')
            if idx in geometry:
                raise ValueError('Duplicate docvortex_layout page geometry')
            geometry[idx] = record
    raw = {'schema': 'pdf-raw/1', 'backend': 'mineru', 'source_name': source_pdf.name, 'source_sha256': _sha(source_pdf),
           'selected_pages': [], 'pages': [], 'failures': [], 'semantic_blocks': [],
           'mineru': {'format': fmt, 'bundle_sha256': manifest['bundle_sha256'],
                      'originals': root.relative_to(work).as_posix(), 'formats': formats,
                      'page_map': page_map, 'source_boxes': source_boxes,
                      'metadata': data.get('metadata', {}) if isinstance(data, dict) else {},
                      'extensions': data.get('extensions', {}) if isinstance(data, dict) else {},
                      'issues': ['MinerU semantic, text and equation candidates require comparison to the source PDF']}}
    pages_by_number = {}
    for record_position, page_record in enumerate(page_records):
        idx = page_record['page_idx']
        page = page_map[idx] if page_map is not None else idx + 1
        width, height = dimensions[page - 1]
        clip = list(source_boxes[idx]) if source_boxes is not None else [0., 0., width, height]
        if not _box(clip) or clip[0] < 0 or clip[1] < 0 or clip[2] > width or clip[3] > height:
            raise ValueError(f'Invalid source_boxes crop on source page {page}')
        record = pages_by_number.get(page)
        if record is None:
            record = {'page': page, 'width': width, 'height': height, 'regions': []}
            pages_by_number[page] = record
            raw['pages'].append(record)
            raw['selected_pages'].append(page)
        for prior in record['regions']:
            b = prior['bbox']
            if min(b[2], clip[2]) > max(b[0], clip[0]) and min(b[3], clip[3]) > max(b[1], clip[1]):
                raise ValueError('Overlapping derivative crops map to the same source PDF area')
        rid = f'p{page:04d}-r{len(record["regions"]) + 1:02d}'
        region = {'id': rid, 'bbox': clip, 'method': 'mineru', 'status': 'complete', 'lines': [], 'issues': [],
                  'route': {'method': 'mineru', 'source_page_idx': idx, 'format': fmt},
                  'fingerprint': hashlib.sha256(json.dumps([raw['source_sha256'], manifest['bundle_sha256'], fmt, idx, page, clip]).encode()).hexdigest()}
        record['regions'].append(region)
        cw, ch = clip[2] - clip[0], clip[3] - clip[1]
        if content_format:
            size, unit = (1000., 1000.), 'normalized-1000-official-content-list'
            region['issues'].append('Content List has block geometry only; flattened inline markup needs source review')
            if not page_record['blocks']:
                region['issues'].append('Content List has no items for this page; verify blank page against source')
        elif fmt == 'legacy-pdf_info':
            size = page_record.get('page_size')
            if not isinstance(size, (list, tuple)) or len(size) != 2 or not all(_number(v) and v > 0 for v in size):
                size, unit = (cw, ch), 'ambiguous-legacy-missing-page_size'
                region['issues'].append('Legacy layout lacks page_size; coordinates require manual evidence')
            else:
                if abs(size[0] / size[1] - cw / ch) > .01 * cw / ch:
                    raise ValueError(f'MinerU page_size aspect ratio differs from source page/crop {page}')
                unit = 'legacy-page_size'
        else:
            size, unit = (1., 1.), 'normalized-1-docvortex-middle'
            geom = geometry.get(idx)
            if geom:
                gw, gh = geom.get('width_pt'), geom.get('height_pt')
                if not _number(gw) or not _number(gh) or abs(gw - cw) > 1 or abs(gh - ch) > 1:
                    raise ValueError(f'MinerU source geometry differs from source page/crop {page}')
            else:
                region['issues'].append('MinerU source geometry extension missing; normalized bboxes need source verification')
        importer = _PageImporter(root, work, document_path, fmt, page, region, size, unit)
        if fmt == 'legacy-pdf_info':
            primary = 'para_blocks' if 'para_blocks' in page_record else 'preproc_blocks'
            blocks = page_record.get(primary, [])
            if not isinstance(blocks, list) or not isinstance(page_record.get('discarded_blocks', []), list):
                raise ValueError('Malformed legacy MinerU block arrays')
            for bi, block in enumerate(blocks):
                importer.block(block, f'/pdf_info/{record_position}/{primary}/{bi}')
            for bi, block in enumerate(page_record.get('discarded_blocks', [])):
                importer.block(block, f'/pdf_info/{record_position}/discarded_blocks/{bi}', discarded=True)
        else:
            blocks = page_record.get('blocks')
            if not isinstance(blocks, list):
                raise ValueError('MinerU page blocks must be a list')
            for bi, block in enumerate(blocks):
                adapted = _content_block(block, fmt == 'content-list-v2') if content_format else block
                pointer = page_record['block_pointers'][bi] if content_format else f'/pages/{record_position}/blocks/{bi}'
                semantic = importer.block(adapted, pointer)
                if content_format and semantic:
                    semantic['mineru_record']['original_content_list_item'] = block
        raw['semantic_blocks'].extend(importer.blocks)
        region['issues'] = list(dict.fromkeys(region['issues']))
        region['geometry'] = {'coordinate_unit': unit, 'coordinate_size': list(size), 'source_clip': clip,
                              'mineru_page_idx': idx, 'source_page': page,
                              'original_page_geometry': page_record.get('page_size', geometry.get(idx))}
    return raw
