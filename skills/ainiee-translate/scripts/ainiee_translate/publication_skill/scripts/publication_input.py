"""Validate source-bound publication exclusions before any text extraction.

Page roles and region boundaries come from a locally reviewed plan, never from
keyword classification. Sanitized MinerU PDFs contain rendered allowed pixels
only: PDF clipping alone can leave excluded text/resources inside an XObject.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

SCHEMA = 'pdf-publication-input/1'
SANITIZATION = 'image-only-clipped-derivative/1'
ROLES = {'cover', 'back-cover', 'belly-band', 'copyright', 'publication-info',
         'printed-toc', 'term-index'}
IMAGE_ROLES = {'cover', 'back-cover', 'belly-band'}


def _sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def _page(value, count):
    if not isinstance(value, int) or isinstance(value, bool) or not 1 <= value <= count:
        raise ValueError('Publication input page is outside the source PDF')
    return value


def _evidence(value):
    if not isinstance(value, str) or not value.strip():
        raise ValueError('Publication input requires local role/boundary evidence')
    return value


def _bbox(value, page):
    if (not isinstance(value, (list, tuple)) or len(value) != 4
            or any(not isinstance(v, (int, float)) or isinstance(v, bool)
                   or not math.isfinite(v) for v in value)):
        raise ValueError('Publication input requires a finite four-number rectangle')
    box = [float(v) for v in value]
    bounds = list(page.rect)
    if (box[0] < bounds[0] or box[1] < bounds[1] or box[2] > bounds[2]
            or box[3] > bounds[3] or box[0] >= box[2] or box[1] >= box[3]):
        raise ValueError('Publication input rectangle is empty or outside its source page')
    return box


def _intersection(first, second):
    box = [max(first[0], second[0]), max(first[1], second[1]),
           min(first[2], second[2]), min(first[3], second[3])]
    return box if box[0] < box[2] and box[1] < box[3] else None


def load_plan(args, source, doc, work):
    """Load --publication-plan or WORK/publication-input.json, validate first.

    Return a JSON-safe normalized policy or None. An exclusion with retained
    regions on the same page is mixed-page removal; only those rectangles may
    be inspected/extracted. Packaging image pages may never retain OCR regions.
    """
    explicit = getattr(args, 'publication_plan', None)
    path = Path(explicit) if explicit else Path(work) / 'publication-input.json'
    if not path.exists() and not explicit:
        return None
    if not path.is_file():
        raise ValueError('Publication input plan is unavailable')
    plan = json.loads(path.read_text(encoding='utf-8-sig'))
    if not isinstance(plan, dict) or plan.get('schema') != SCHEMA:
        raise ValueError('Unsupported publication input schema')
    source_hash = _sha(source)
    if plan.get('source_sha256') != source_hash:
        raise ValueError('Publication input source fingerprint mismatch')
    count = len(doc)
    exclusions = plan.get('exclusions', [])
    retained = plan.get('retained_regions', {})
    if not isinstance(exclusions, list) or not isinstance(retained, dict):
        raise ValueError('Malformed publication input exclusion/region lists')
    normalized_exclusions, excluded_roles = [], {}
    for item in exclusions:
        if not isinstance(item, dict):
            raise ValueError('Malformed publication input exclusion')
        page = _page(item.get('page'), count)
        role = item.get('role')
        if not isinstance(role, str) or role not in ROLES:
            raise ValueError('Unsupported publication input exclusion role')
        if page in excluded_roles:
            raise ValueError('Publication input page has duplicate exclusion roles')
        excluded_roles[page] = role
        normalized_exclusions.append({'page': page, 'role': role,
                                      'evidence': _evidence(item.get('evidence'))})
    normalized_regions = {}
    for key, regions in retained.items():
        if not isinstance(key, str) or not key.isdecimal() or str(int(key)) != key:
            raise ValueError('Publication input retained-region keys must be source page numbers')
        page = _page(int(key), count)
        if excluded_roles.get(page) in IMAGE_ROLES:
            raise ValueError('Packaging image pages cannot retain text extraction regions')
        if not isinstance(regions, list) or not regions:
            raise ValueError('Publication input retained page requires nonempty regions')
        boxes, items = [], []
        for item in regions:
            if not isinstance(item, dict):
                raise ValueError('Retained regions require bbox, role and evidence objects')
            role = item.get('role')
            if not isinstance(role, str) or not role.strip():
                raise ValueError('Retained region requires an explicit content role')
            if role in IMAGE_ROLES:
                raise ValueError('Packaging image regions cannot enter text extraction')
            box = _bbox(item.get('bbox'), doc[page - 1])
            if any(_intersection(box, previous) is not None for previous in boxes):
                raise ValueError('Publication input retained rectangles overlap')
            boxes.append(box)
            items.append({'bbox': box, 'role': role,
                          'evidence': _evidence(item.get('evidence'))})
        normalized_regions[key] = items
    excluded_pages = sorted(n for n in excluded_roles if str(n) not in normalized_regions)
    return {'schema': SCHEMA, 'source_sha256': source_hash, 'plan_sha256': _sha(path),
            'plan_path': str(path.resolve()), 'source_page_count': count,
            'exclusions': normalized_exclusions, 'retained_regions': normalized_regions,
            'excluded_pages': excluded_pages,
            'allowed_pages': [n for n in range(1, count + 1) if n not in excluded_pages],
            'sanitization': SANITIZATION}


def metadata(policy):
    """Source/evidence metadata suitable for raw, state and downstream books."""
    return deepcopy(policy) if policy is not None else None


def apply_selection_routes(policy, selection, routes, doc):
    """Intersect selected routes with retained regions; never broaden a route.

    A mixed page may produce several disjoint routes with the original method,
    OCR settings and local region evidence. Completely excluded pages vanish.
    Without a plan the legacy selection and routing values are unchanged.
    """
    if policy is None:
        return selection, routes
    chosen, sanitized = [], deepcopy(routes)
    for number in selection:
        _page(number, len(doc))
        if number in policy['excluded_pages']:
            sanitized.pop(str(number), None)
            continue
        configs = routes.get(str(number), [{}])
        if not isinstance(configs, list) or not configs:
            raise ValueError('Publication input page has an empty/malformed routing list')
        kept = policy['retained_regions'].get(str(number))
        result = []
        for route in configs:
            if not isinstance(route, dict):
                raise ValueError('Publication input route must be an object')
            route_box = _bbox(route.get('bbox', list(doc[number - 1].rect)), doc[number - 1])
            if kept is None:
                result.append(deepcopy(route))
                continue
            for region in kept:
                box = _intersection(route_box, region['bbox'])
                if box:
                    item = deepcopy(route)
                    item['bbox'] = box
                    item['publication_region'] = deepcopy(region)
                    result.append(item)
        if result:
            chosen.append(number)
            sanitized[str(number)] = result
        else:
            sanitized.pop(str(number), None)
    return chosen, sanitized


def reference_tasks(selection, routes, doc):
    """Approved owner/reference source rectangles, preserving route restrictions."""
    result = {}
    for number in selection:
        result[number] = [{'page': number, 'clip': route.get('bbox'),
                           'key': f'reference-p{number:04d}-r{index:02d}',
                           'route': {'method': 'mineru-local', 'reference': True}}
                          for index, route in enumerate(routes.get(str(number), [{}]), 1)]
    return result


def prepared_input(doc, source, tasks, directory, policy, dpi=300):
    """Make deterministic, resource-clean PDF pixels for approved input tasks."""
    if not isinstance(dpi, int) or isinstance(dpi, bool) or not 72 <= dpi <= 1200:
        raise ValueError('Publication sanitization DPI must be an integer in 72..1200')
    if _sha(source) != policy['source_sha256']:
        raise ValueError('Publication input source changed after plan validation')
    payload = {'source': policy['source_sha256'], 'policy': policy['plan_sha256'],
               'tasks': tasks, 'dpi': dpi, 'version': SANITIZATION}
    key = hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()
    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    target = directory / (key + '.pdf')
    receipt = directory / (key + '.json')
    if target.exists() and receipt.exists():
        saved = json.loads(receipt.read_text(encoding='utf-8'))
        if saved.get('input_sha256') == _sha(target) and saved.get('fingerprint') == key:
            return target
    import pdf_to_epub as pipeline
    derivative = pipeline.pdf_module().open()
    try:
        for task in tasks:
            number = _page(task['page'], len(doc))
            if number in policy['excluded_pages']:
                raise ValueError('Excluded publication page entered model input')
            box = _bbox(task.get('clip') or list(doc[number - 1].rect), doc[number - 1])
            kept = policy['retained_regions'].get(str(number))
            if kept and not any(_intersection(box, region['bbox']) == box for region in kept):
                raise ValueError('Publication model input extends outside a retained rectangle')
            rect = pipeline.pdf_module().Rect(box)
            pixmap = doc[number - 1].get_pixmap(clip=rect, dpi=dpi, alpha=False)
            page = derivative.new_page(width=rect.width, height=rect.height)
            page.insert_image(page.rect, stream=pixmap.tobytes('png'))
        if not len(derivative):
            raise ValueError('Publication model input is empty')
        temporary = target.with_suffix('.part.pdf')
        derivative.save(temporary, garbage=4, deflate=True, no_new_id=True)
        temporary.replace(target)
        receipt.write_text(json.dumps({'schema': SANITIZATION, 'fingerprint': key,
                                       'input_sha256': _sha(target), 'source_sha256': policy['source_sha256'],
                                       'plan_sha256': policy['plan_sha256'], 'dpi': dpi,
                                       'page_map': [task['page'] for task in tasks],
                                       'source_boxes': [task.get('clip') or list(doc[task['page'] - 1].rect)
                                                        for task in tasks]}, indent=2), encoding='utf-8')
        return target
    finally:
        derivative.close()
