"""Local-only MinerU batching, source mapping, structural checks and adoption.

The reusable process/configuration boundary is mineru_local.ensure_bundle. This
module is the pdf-to-epub adapter: all candidate text, resources, detailed errors
and raw attempts stay in WORK. Console reporting contains numeric results only.
"""
from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from pathlib import Path
import traceback
import uuid

import pdf_to_epub as p
from mineru_flow import mineru_language, prepared_input, remap_page
from mineru_import import read_bundle
import publication_input

FLOW_VERSION = 'mineru-local-flow/1'
QUALITY_VERSION = 'mineru-local-quality/1'


def _reference_pages(owners, count, overlap):
    chosen = {task['page'] for task in owners}
    first, last = min(chosen), max(chosen)
    chosen.update(range(max(1, first - overlap), first))
    chosen.update(range(last + 1, min(count, last + overlap) + 1))
    return sorted(chosen)


def _retry_reference_pages(owners, count, overlap):
    """Every disjoint suspect run receives its own adjacent reference pages."""
    return sorted({n for task in owners
                   for n in range(max(1, task['page'] - overlap), min(count, task['page'] + overlap) + 1)})


def plan_batches(tasks, page_count, batch_pages=50, reference_pages=2):
    """Partition owners, attach actual edge references, isolate region crops.

    Owners are tasks with page/clip/key/route. References are source pages, not
    semantic context. Noncontiguous selections do not implicitly select gaps.
    Every task is owned exactly once; no reference is adopted during merging.
    """
    if not isinstance(batch_pages, int) or isinstance(batch_pages, bool) or batch_pages < 1:
        raise ValueError('MinerU batch owner count must be positive')
    if not isinstance(reference_pages, int) or isinstance(reference_pages, bool) or reference_pages < 0:
        raise ValueError('MinerU reference page count must be nonnegative')
    if any(not 1 <= task['page'] <= page_count for task in tasks):
        raise ValueError('MinerU owner page is outside the source PDF')
    if len({task['key'] for task in tasks}) != len(tasks):
        raise ValueError('MinerU owner keys must be unique')
    batches, pending = [], []

    def add(owners):
        batches.append({'id': f'b{len(batches) + 1:04d}', 'owners': deepcopy(owners),
                        'pages': _reference_pages(owners, page_count, reference_pages),
                        'derivative': any(task.get('clip') for task in owners)})

    for task in tasks:
        if task.get('clip'):
            if pending:
                add(pending)
                pending = []
            add([task])
        else:
            pending.append(task)
            if len(pending) == batch_pages:
                add(pending)
                pending = []
    if pending:
        add(pending)
    return batches


def _input_plan(doc, source, batch, directory):
    """Keep original page_idx unless this adapter actually creates a crop PDF."""
    if batch.get('publication_input') is not None:
        tasks = batch['input_tasks']
        target = publication_input.prepared_input(doc, source, tasks, directory,
                                                  batch['publication_input'], batch['sanitization_dpi'])
        mapping = [task['page'] for task in tasks]
        boxes = [task.get('clip') or list(doc[task['page'] - 1].rect) for task in tasks]
        return target, list(range(1, len(tasks) + 1)), mapping, boxes
    if not batch['derivative']:
        return source, batch['pages'], None, None
    owners = {task['page']: task for task in batch['owners']}
    tasks = [owners.get(n, {'page': n, 'clip': None, 'key': f'reference-p{n:04d}',
                           'route': {'method': 'mineru-local', 'reference': True}})
             for n in batch['pages']]
    target = prepared_input(doc, source, tasks, directory)
    boxes = [task.get('clip') or list(doc[task['page'] - 1].rect) for task in tasks]
    return target, list(range(1, len(tasks) + 1)), batch['pages'], boxes


def _publication_batch(batch, references, policy, dpi):
    """References obey the same reviewed page/region limits as owners."""
    if policy is None:
        return batch
    owners = defaultdict(list)
    for task in batch['owners']:
        owners[task['page']].append(task)
    pages = [number for number in batch['pages'] if number in references]
    tasks = [deepcopy(task) for number in pages
             for task in owners.get(number, references[number])]
    return dict(batch, pages=pages, derivative=True, input_tasks=tasks,
                publication_input=publication_input.metadata(policy), sanitization_dpi=dpi)


def _issue(page, code, fatal=False, **counts):
    return {'page': page, 'code': code, 'fatal': fatal, **counts}


def _source_counts(doc, task):
    """Local numeric hints only; source/OCR text is never returned or printed."""
    rect = p.rect_check(doc[task['page'] - 1], task.get('clip'))
    page = doc[task['page'] - 1]
    text_chars = len(page.get_text('text', clip=rect).strip())
    image_count = sum(1 for image in page.get_image_info() if (p.pdf_module().Rect(image['bbox']) & rect).get_area() > .1)
    drawing_count = sum(1 for drawing in page.get_drawings() if (p.pdf_module().Rect(drawing['rect']) & rect).get_area() > .1)
    return {'native_chars': text_chars, 'images': image_count, 'drawings': drawing_count}


def page_summary(raw):
    """Text-free signatures used to check repeated boundary pages locally."""
    result = {}
    blocks = defaultdict(list)
    for item in raw.get('semantic_blocks', []):
        blocks[item['page']].append(item)
    for page in raw['pages']:
        lines = [line for region in page['regions'] for line in region['lines']]
        result[page['page']] = {'regions': len(page['regions']), 'lines': len(lines),
                               'blocks': len(blocks[page['page']]),
                               'characters': sum(len(span.get('text', '')) for line in lines for span in line.get('spans', [])),
                               'assets': sum(bool(item.get('asset')) for item in blocks[page['page']])}
    return result


def quality_issues(raw, owners, source_counts):
    """Deterministic structural/count checks, never a content-correctness claim."""
    issues = []
    page_records = {page['page']: page for page in raw['pages']}
    block_groups = defaultdict(list)
    for block in raw.get('semantic_blocks', []):
        block_groups[block['page']].append(block)
    for task in owners:
        n = task['page']
        page = page_records.get(n)
        if not page or len(page.get('regions', [])) != 1:
            issues.append(_issue(n, 'missing-or-ambiguous-page-region', True))
            continue
        region = page['regions'][0]
        lines = region.get('lines', [])
        counts = source_counts[task['key']]
        if not lines and any(counts.values()):
            issues.append(_issue(n, 'empty-result-on-source-content', True, lines=0))
        identifiers = [line.get('id') for line in lines]
        if len(identifiers) != len(set(identifiers)) or any(not value for value in identifiers):
            issues.append(_issue(n, 'duplicate-or-missing-line-id', True, lines=len(lines)))
        chars, bad = 0, 0
        repeated = set()
        seen = set()
        for line in lines:
            text = ''.join(span.get('text', '') for span in line.get('spans', []))
            chars += len(text)
            bad += text.count('\ufffd') + sum(ord(c) < 32 and c not in '\n\r\t' for c in text)
            signature = (tuple(line.get('bbox', [])), text)
            if text.strip() and signature in seen:
                repeated.add(signature)
            seen.add(signature)
            if line.get('issues'):
                issues.append(_issue(n, 'unparsed-span-content', True))
        if bad:
            issues.append(_issue(n, 'invalid-text-characters', count=bad))
        if repeated:
            issues.append(_issue(n, 'duplicate-content-and-geometry', count=len(repeated)))
        if counts['native_chars'] >= 40 and (chars < counts['native_chars'] * .2 or chars > counts['native_chars'] * 5):
            issues.append(_issue(n, 'source-result-character-count-anomaly', source_characters=counts['native_chars'], result_characters=chars))
        for message in region.get('issues', []):
            if 'Nonobject MinerU block' in message:
                issues.append(_issue(n, 'malformed-block', True))
            elif 'Unknown MinerU span' in message:
                issues.append(_issue(n, 'unparsed-span-content', True))
            elif 'bbox outside' in message:
                issues.append(_issue(n, 'geometry-outside-declared-space', True))
            elif 'asset missing' in message:
                issues.append(_issue(n, 'missing-resource-candidate'))
            elif 'source geometry extension missing' in message or 'Unsupported MinerU text style' in message:
                issues.append(_issue(n, 'incomplete-geometry-or-style-evidence'))
        for block in block_groups[n]:
            if block.get('issues'):
                issues.append(_issue(n, 'unverified-block-type-or-geometry'))
    # One rule/page entry is sufficient; counts remain numeric in quality logs.
    unique = {}
    for issue in issues:
        key = (issue['page'], issue['code'])
        unique[key] = issue
    return list(unique.values())


def boundary_issues(attempts):
    """Find count disagreements and attach them only to the owning batch."""
    signatures, result = defaultdict(list), defaultdict(list)
    owner_by_page = defaultdict(list)
    for batch, attempt in attempts:
        if batch['derivative'] or attempt.get('raw') is None:
            continue
        for n, signature in attempt['summary'].items():
            signatures[n].append(signature)
        for task in batch['owners']:
            owner_by_page[task['page']].append(batch['id'])
    for n, values in signatures.items():
        if len(values) > 1 and any(value != values[0] for value in values[1:]):
            for batch_id in owner_by_page[n]:
                result[batch_id].append(_issue(n, 'boundary-count-disagreement', observations=len(values)))
    return dict(result)


def _options(args, tier, pages):
    return {'install_root': getattr(args, 'mineru_local_root', None),
            'cli': getattr(args, 'mineru_local_cli', None),
            'config': getattr(args, 'mineru_local_config', None),
            'environment_script': getattr(args, 'mineru_local_env', None),
            'timeout': getattr(args, 'mineru_local_timeout', 3600),
            'tier': tier, 'pages': pages, 'format': 'zip',
            'language': mineru_language(args.language)}


def _attempt(batch, tier, doc, source, work, args, runner, cancel_event):
    target, selected, mapping, boxes = _input_plan(doc, source, batch, work / 'mineru/local/inputs')
    attempt = {'batch': batch['id'], 'tier': tier, 'owner_pages': [task['page'] for task in batch['owners']],
               'reference_pages': [n for n in batch['pages'] if n not in {task['page'] for task in batch['owners']}],
               'input_pages': selected, 'page_map': mapping, 'source_boxes': boxes, 'status': 'failed',
               'raw': None, 'summary': {}, 'issues': [], 'cached': False}
    try:
        result = runner(target, work / 'mineru/local/jobs', _options(args, tier, selected), cancel_event=cancel_event)
        attempt.update({key: result[key] for key in ('status', 'cached', 'error_code', 'progress') if key in result})
        attempt['fingerprint'] = result.get('request_fingerprint', result.get('fingerprint'))
        for key in ('bundle', 'checkpoint'):
            if result.get(key):
                attempt[key] = str(result[key])
        if result['status'] != 'done':
            structural_codes = {'structured_bundle_missing_or_large', 'duplicate_bundle_paths',
                                'unsafe_bundle_paths', 'middle_json_missing_or_ambiguous',
                                'unsupported_middle_schema', 'invalid_source_page_indices',
                                'source_page_mapping_mismatch', 'structured_bundle_invalid'}
            if (result.get('error_code') in structural_codes
                    and result.get('process', {}).get('status') == 'done'):
                # CLI success with an unusable structure is a quality failure,
                # eligible for the same single Advanced retry as import defects.
                # Acquisition/configuration failures remain stop conditions.
                attempt['status'] = 'structure-failed'
            attempt['issues'] = [_issue(task['page'], 'local-acquisition-' + result['status'], True) for task in batch['owners']]
            return attempt
        imported = read_bundle(result['bundle'], work, source, page_map=mapping, source_boxes=boxes)
        if batch.get('publication_input') is not None:
            imported['publication_input'] = publication_input.metadata(batch['publication_input'])
            attempt['publication_input'] = publication_input.metadata(batch['publication_input'])
        preserved = work / 'mineru/local/batches' / (attempt['fingerprint'] or p.digest([p.sha(target), tier, selected])) / imported['mineru']['bundle_sha256'] / (batch['id'] + '-' + tier + '.raw.json')
        p.save(preserved, imported)
        attempt['imported_raw'] = str(preserved)
        # Original --pages must retain ORIGINAL zero-based indexes. Derivatives
        # must return all sequential indexes and use exactly one explicit map.
        if imported['selected_pages'] != batch['pages']:
            attempt['issues'] = [_issue(task['page'], 'selected-page-index-mismatch', True,
                                       expected_pages=len(batch['pages']), returned_pages=len(imported['selected_pages']))
                                 for task in batch['owners']]
            attempt['status'] = 'structure-failed'
            return attempt
        attempt['raw'] = imported
        attempt['summary'] = page_summary(imported)
        counts = {task['key']: _source_counts(doc, task) for task in batch['owners']}
        attempt['issues'] = quality_issues(imported, batch['owners'], counts)
        attempt['source_counts'] = counts
        return attempt
    except KeyboardInterrupt:
        attempt['status'] = 'cancelled'
        attempt['issues'] = [_issue(task['page'], 'local-acquisition-cancelled', True) for task in batch['owners']]
        return attempt
    except Exception as exc:
        # Detailed exception messages may contain model-generated values. Keep
        # them local; public/checkpoint output uses exception classes only.
        logs = work / 'mineru/local/errors'
        logs.mkdir(parents=True, exist_ok=True)
        log = logs / (batch['id'] + '-' + tier + '-' + uuid.uuid4().hex + '.txt')
        log.write_text(traceback.format_exc(), encoding='utf-8')
        interrupted = getattr(exc, 'code', '') in {'environment_setup_cancelled', 'config_probe_cancelled', 'local_preflight_cancelled'}
        attempt.update(status='cancelled' if interrupted else 'structure-failed', error_code=type(exc).__name__, error_log=str(log))
        attempt['issues'] = [_issue(task['page'], 'local-configuration-or-import-failure', True) for task in batch['owners']]
        return attempt


def _public_attempt(attempt):
    return {key: value for key, value in attempt.items() if key != 'raw'}


def _native_region(args, task, doc, source_hash, work):
    n, key, route = task['page'], task['key'], task['route']
    method = route['method']
    rect = p.rect_check(doc[n - 1], route.get('bbox'))
    language = {'ch': 'chi_sim+eng', 'en': 'eng', 'chinese_cht': 'chi_tra+eng'}.get(args.language, args.language)
    tess = p.tesseract_path(args.tesseract)
    tess_identity = [tess, Path(tess).stat().st_mtime_ns] if tess else None
    fingerprint = p.digest({'version': '1.0.0', 'pdf': source_hash, 'page': n, 'route': route, 'language': language,
                            'dpi': args.dpi, 'psm': args.psm, 'tesseract': tess_identity})
    legacy_mixed_fingerprint = p.digest({'local': '1.0.0', 'pdf': source_hash, 'page': n, 'route': route, 'language': language,
                                        'dpi': args.dpi, 'psm': args.psm, 'tesseract': tess})
    cache = work / 'cache' / (key + '.json')
    old = p.load(cache) if cache.exists() else {}
    if old.get('fingerprint') in {fingerprint, legacy_mixed_fingerprint} and old.get('status') == 'complete':
        return old, True
    region = {'id': key, 'bbox': list(rect), 'route': route, 'method': method, 'status': 'failed',
              'lines': [], 'issues': [], 'fingerprint': fingerprint}
    try:
        try:
            lines = p.native(doc[n - 1], rect) if method == 'native' else p.ocr(doc[n - 1], rect, work, key, tess, language, args.dpi, route.get('psm', args.psm), route.get('rotation', 0))
            if not lines:
                raise ValueError('Explicit route returned no text')
        except Exception:
            if method != 'native' or route.get('fallback') != 'ocr':
                raise
            method = 'ocr'
            region['issues'].append('Explicit native failure used the configured local OCR fallback')
            lines = p.ocr(doc[n - 1], rect, work, key, tess, language, args.dpi, route.get('psm', args.psm), route.get('rotation', 0))
            if not lines:
                raise ValueError('Explicit OCR fallback returned no text')
        for li, line in enumerate(lines, 1):
            line.update(id=f'{key}-l{li:04d}', source={'page': n, 'bbox': line['bbox'], 'method': method})
        region.update(method=method, status='complete', lines=lines)
    except Exception as exc:
        logs = work / 'mineru/local/errors'
        logs.mkdir(parents=True, exist_ok=True)
        (logs / (key + '-' + uuid.uuid4().hex + '.txt')).write_text(traceback.format_exc(), encoding='utf-8')
        region['error'] = 'explicit-local-route-' + type(exc).__name__
    p.save(cache, region)
    return region, False


def extract(args, runner=None, cancel_event=None):
    """Run local extraction only, with durable raw attempts and owner adoption."""
    if runner is None:
        from mineru_local import ensure_bundle
        runner = ensure_bundle
    source = Path(args.input).resolve()
    work = Path(args.out).resolve()
    work.mkdir(parents=True, exist_ok=True)
    source_hash = p.sha(source)
    doc = p.pdf_module().open(source)
    try:
        selection = p.pages(args.pages, len(doc))
        routes = p.load(args.routes) if args.routes else {}
        policy = publication_input.load_plan(args, source, doc, work)
        if policy is not None:
            reference_selection, reference_routes = publication_input.apply_selection_routes(
                policy, policy['allowed_pages'], routes, doc)
            references = publication_input.reference_tasks(reference_selection, reference_routes, doc)
        else:
            references = None
        selection, routes = publication_input.apply_selection_routes(policy, selection, routes, doc)
        records = {n: {'page': n, 'width': doc[n - 1].rect.width, 'height': doc[n - 1].rect.height, 'regions': []} for n in selection}
        tasks, native_tasks, reused = [], [], 0
        for n in selection:
            configs = routes.get(str(n), [{'method': 'mineru-local'}])
            if not configs:
                raise ValueError(f'Page {n}: empty routing list')
            rectangles = []
            for ri, route in enumerate(configs, 1):
                rect = p.rect_check(doc[n - 1], route.get('bbox'))
                if any((rect & previous).get_area() > .1 for previous in rectangles):
                    raise ValueError(f'Page {n}: overlapping extraction regions')
                rectangles.append(rect)
                task = {'page': n, 'clip': list(rect) if route.get('bbox') else None, 'key': f'p{n:04d}-r{ri:02d}', 'route': route}
                method = route.get('method', 'mineru-local')
                if method in {'mineru-local', 'mineru', 'auto'}:
                    if route.get('rotation'):
                        raise ValueError('MinerU rotation requires a verified derivative')
                    tasks.append(task)
                elif method in {'native', 'ocr'}:
                    native_tasks.append(task)
                else:
                    raise ValueError('Unknown extraction route')
        batch_pages = getattr(args, 'mineru_batch_pages', 50)
        reference_pages = getattr(args, 'mineru_reference_pages', 2)
        tier = getattr(args, 'mineru_tier', 'standard')
        batches = plan_batches(tasks, len(doc), batch_pages, reference_pages)
        batches = [_publication_batch(batch, references, policy, args.dpi) for batch in batches]
        signature = p.digest({'flow': FLOW_VERSION, 'quality': QUALITY_VERSION, 'source': source_hash,
                              'selection': selection, 'tasks': tasks, 'native_tasks': native_tasks,
                              'batch_pages': batch_pages, 'reference_pages': reference_pages,
                              'options': _options(args, tier, [])})
        if policy is not None:
            signature = p.digest({'local_flow': signature, 'publication_input': policy,
                                  'sanitization_dpi': args.dpi})
        directory = work / 'mineru/local'
        directory.mkdir(parents=True, exist_ok=True)
        state = {'schema': FLOW_VERSION, 'fingerprint': signature, 'source_sha256': source_hash,
                 'selected_pages': selection, 'batch_pages': batch_pages, 'reference_pages': reference_pages,
                 'tier': tier, 'stage': 'extracting', 'batches': batches, 'attempts': [],
                 'quality_version': QUALITY_VERSION, 'content_verified': False}
        if policy is not None:
            state['publication_input'] = publication_input.metadata(policy)

        def checkpoint(stage):
            state['stage'] = stage
            p.save(directory / (signature + '.json'), state)
            p.save(directory / 'state.json', state)

        checkpoint('extracting')
        attempts, cancelled, stopped = [], False, False
        for task in native_tasks:
            region, cached = _native_region(args, task, doc, source_hash, work)
            records[task['page']]['regions'].append(region)
            reused += int(cached)
        for batch in batches:
            if cancel_event is not None and cancel_event.is_set():
                cancelled = True
                break
            attempt = _attempt(batch, tier, doc, source, work, args, runner, cancel_event)
            attempts.append((batch, attempt))
            state['attempts'].append(_public_attempt(attempt))
            checkpoint('extracting')
            if attempt['status'] == 'cancelled':
                cancelled = True
                break
            # Configuration/acquisition failures stop later work. Imported
            # structural defects are eligible for one Advanced attempt below.
            if attempt['status'] in {'failed', 'timeout'} or (attempt.get('error_code') == 'LocalMinerUError'):
                stopped = True
                break
        boundaries = boundary_issues(attempts)
        semantic, result_metadata, jobs, quality_records = [], [], [], []
        adopted_keys = set()
        for batch, initial in attempts:
            initial['issues'].extend(boundaries.get(batch['id'], []))
            advanced = None
            suspect = {issue['page'] for issue in initial['issues']}
            if tier == 'standard' and suspect and not cancelled and not stopped:
                owners = [task for task in batch['owners'] if task['page'] in suspect]
                retry = dict(batch, owners=owners, pages=_retry_reference_pages(owners, len(doc), reference_pages))
                retry = _publication_batch(retry, references, policy, args.dpi)
                advanced = _attempt(retry, 'advanced', doc, source, work, args, runner, cancel_event)
                state['attempts'].append(_public_attempt(advanced))
                checkpoint('advanced-checking')
                if advanced['status'] == 'cancelled':
                    cancelled = True
            quality = {'schema': QUALITY_VERSION, 'batch': batch['id'], 'owner_pages': [t['page'] for t in batch['owners']],
                       'initial': _public_attempt(initial), 'advanced': _public_attempt(advanced) if advanced else None,
                       'advanced_attempted': advanced is not None, 'content_verified': False,
                       'conclusion': 'structural checks only; source-content proofreading is pending'}
            quality_key = p.digest(quality)[:16]
            quality_path = directory / 'quality' / (signature[:16] + '-' + batch['id'] + '-' + quality_key + '.json')
            p.save(quality_path, quality)
            quality_records.append(str(quality_path))
            for attempt in [initial] + ([advanced] if advanced else []):
                jobs.append(_public_attempt(attempt))
                if attempt.get('raw'):
                    metadata = deepcopy(attempt['raw']['mineru'])
                    metadata.update(batch=batch['id'], tier=attempt['tier'], adopted_regions=[])
                    result_metadata.append(metadata)
            for task in batch['owners']:
                n = task['page']
                chosen = advanced if advanced is not None and n in suspect else initial
                fatal = [issue for issue in chosen['issues'] if issue['page'] == n and issue['fatal']]
                pg = next((page for page in (chosen.get('raw') or {}).get('pages', []) if page['page'] == n), None)
                if chosen['status'] == 'done' and pg is not None and not fatal:
                    region, blocks, line_map = remap_page(dict(chosen['raw'], pages=[pg]), task)
                    region.update(method='mineru-local', mineru_tier=chosen['tier'], content_verified=False,
                                  local_quality_issues=[issue for issue in chosen['issues'] if issue['page'] == n],
                                  local_quality_initial_issues=[issue for issue in initial['issues'] if issue['page'] == n],
                                  local_quality_retry_attempted=advanced is not None and n in suspect)
                    for line in region['lines']:
                        line['source']['method'] = 'mineru-local'
                    records[n]['regions'].append(region)
                    semantic.extend(blocks)
                    reused += int(chosen.get('cached', False))
                    for metadata in result_metadata:
                        if metadata['batch'] == batch['id'] and metadata['tier'] == chosen['tier']:
                            metadata['adopted_regions'].append({'region': task['key'], 'page': n, 'line_map': line_map})
                else:
                    records[n]['regions'].append({'id': task['key'], 'bbox': task.get('clip') or list(doc[n - 1].rect),
                                                  'route': task['route'], 'method': 'mineru-local', 'status': 'failed',
                                                  'lines': [], 'issues': chosen['issues'],
                                                  'error': 'unresolved-local-structural-or-acquisition-failure'})
                adopted_keys.add(task['key'])
        for task in tasks:
            if task['key'] not in adopted_keys:
                records[task['page']]['regions'].append({'id': task['key'], 'bbox': task.get('clip') or list(doc[task['page'] - 1].rect),
                                                         'route': task['route'], 'method': 'mineru-local', 'status': 'failed',
                                                         'lines': [], 'issues': [], 'error': 'cancelled-or-not-yet-completed'})
        failures = []
        for record in records.values():
            record['regions'].sort(key=lambda region: region['id'])
            for region in record['regions']:
                if region['status'] == 'failed':
                    failures.append({'region': region['id'], 'error': region['error']})
        raw = {'schema': 'pdf-raw/1', 'source_name': source.name, 'source_sha256': source_hash, 'selected_pages': selection,
               'pages': [records[n] for n in selection], 'failures': failures, 'semantic_blocks': semantic,
               'backend': 'mineru-local', 'mineru_jobs': jobs, 'mineru_result': result_metadata,
               'local_flow_fingerprint': signature, 'local_quality_records': quality_records, 'content_verified': False}
        if policy is not None:
            raw['publication_input'] = publication_input.metadata(policy)
        stage = 'extraction-cancelled' if cancelled else ('extraction-failed' if failures else 'extracted')
        p.save(work / 'raw.json', raw)
        overall_state = {'source_path': str(source), 'source_sha256': source_hash,
                                    'selected_pages': selection, 'stage': stage, 'cached_regions_reused': reused,
                                    'failures': failures, 'mineru_jobs': jobs, 'default_backend': 'mineru-local',
                                    'local_flow_fingerprint': signature, 'content_verified': False}
        if policy is not None:
            overall_state['publication_input'] = publication_input.metadata(policy)
        p.save(work / 'state.json', overall_state)
        state['attempts'] = jobs
        state['quality_records'] = quality_records
        checkpoint(stage)
        print(f'Local MinerU: pages={len(selection)} batches={len(batches)} reused={reused} blocks={len(semantic)} failures={len(failures)} status={stage}')
        return 130 if cancelled else (2 if failures else 0)
    finally:
        doc.close()
