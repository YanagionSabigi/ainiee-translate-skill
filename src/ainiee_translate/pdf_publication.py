"""Source-bound publication input. Roles and evidence are reviewed, never guessed."""
from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from .mineru_local import digest, sha256, write_json

RETAINED_ROLES = {'content', 'preface', 'bibliography'}
EXCLUDED_ROLES = {'cover', 'back-cover', 'belly-band', 'copyright', 'publication-info', 'printed-toc', 'term-index'}


def _fitz():
    try:
        import pymupdf
    except ImportError as exc:
        raise RuntimeError('Install ainiee-translate[pdf] to prepare PDFs.') from exc
    return pymupdf


def inspect_pdf(input_pdf: Path, work: Path) -> dict[str, Any]:
    fitz = _fitz()
    input_pdf, work = Path(input_pdf).resolve(), Path(work)
    source_hash = sha256(input_pdf)
    work.mkdir(parents=True, exist_ok=True)
    existing = work / 'inspection.json'
    if existing.exists() and json.loads(existing.read_text(encoding='utf8'))['source_sha256'] != source_hash:
        raise ValueError('Work directory is bound to a different source; use a new --work directory.')
    pages, bookmarks = [], []
    with fitz.open(input_pdf) as doc:
        for page in doc:
            preview = f'inspection/page-{page.number + 1}.png'
            (work / preview).parent.mkdir(exist_ok=True)
            page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False).save(work / preview)
            pages.append({'page': page.number + 1, 'width': page.rect.width,
                          'height': page.rect.height, 'preview': preview})
        for idx, item in enumerate(doc.get_toc(simple=False)):
            dest = item[3]; point = dest.get('to')
            bookmarks.append({'bookmark_index': idx, 'level': item[0], 'source_title': item[1],
                              'source_page_idx': item[2] - 1,
                              'point': [point.x, point.y] if point is not None else None})
    inspection = dict(schema='ainiee-pdf-inspection/1', source_sha256=source_hash,
                      source_path=str(input_pdf), pages=pages, bookmarks=bookmarks)
    write_json(existing, inspection)
    plan = work / 'publication-input.json'
    if not plan.exists():
        write_json(plan, dict(schema='ainiee-publication-input/1', source_sha256=source_hash,
                              reviewed=False, evidence='', pages=[dict(page=p['page'], role='unclassified', evidence='') for p in pages]))
    return inspection


def validate_publication_input(plan: dict[str, Any], source_sha256: str) -> None:
    if plan.get('schema') != 'ainiee-publication-input/1' or plan.get('source_sha256') != source_sha256:
        raise ValueError('Publication input schema/source hash mismatch')
    if plan.get('reviewed') is not True or not str(plan.get('evidence', '')).strip():
        raise ValueError('Publication input must be reviewed with source evidence before extraction')
    pages = plan.get('pages')
    if not isinstance(pages, list) or not pages:
        raise ValueError('Every source page needs a reviewed role')
    numbers = []
    for page in pages:
        number = page.get('page')
        if type(number) is not int or number < 1:
            raise ValueError('Physical page numbers are 1-based positive integers')
        numbers.append(number)
        if page.get('role') not in RETAINED_ROLES | EXCLUDED_ROLES or not page.get('evidence', '').strip():
            raise ValueError('Unresolved page role or missing evidence')
        regions = page.get('regions', [])
        if not isinstance(regions, list):
            raise ValueError('Regions must be a list')
        if regions and page['role'] in EXCLUDED_ROLES:
            raise ValueError('An excluded whole page cannot also have retained regions')
        boxes = []
        for region in regions:
            box = region.get('bbox')
            if (region.get('role') not in RETAINED_ROLES or not region.get('evidence', '').strip()
                    or not isinstance(box, list) or len(box) != 4
                    or any(type(v) not in (int, float) or not math.isfinite(v) for v in box)
                    or box[0] < 0 or box[1] < 0 or box[2] <= box[0] or box[3] <= box[1]):
                raise ValueError('Invalid retained region or missing evidence')
            for other in boxes:
                if max(box[0], other[0]) < min(box[2], other[2]) and max(box[1], other[1]) < min(box[3], other[3]):
                    raise ValueError('Retained regions overlap and would duplicate content')
            boxes.append(box)
    if numbers != list(range(1, len(numbers) + 1)):
        raise ValueError('Pages must appear exactly once in physical order')


def prepare_extraction_inputs(input_pdf: Path, plan: dict[str, Any], work: Path) -> list[dict[str, Any]]:
    fitz = _fitz()
    source_hash = sha256(input_pdf)
    validate_publication_input(plan, source_hash)
    plan_hash = digest(plan)
    root = Path(work) / 'inputs' / plan_hash
    index = root / 'inputs.json'
    with fitz.open(input_pdf) as source:
        if len(source) != len(plan['pages']):
            raise ValueError('Plan must account for every source page')
        routes = []
        for page_plan, page in zip(plan['pages'], source):
            for region in page_plan.get('regions') or ([dict(bbox=list(page.rect), role=page_plan['role'])]
                                                      if page_plan['role'] in RETAINED_ROLES else []):
                box = fitz.Rect(region['bbox'])
                if not page.rect.contains(box):
                    raise ValueError('Region outside original page dimensions')
                routes.append((page.number, list(box), region['role']))
        if not routes:
            raise ValueError('Publication plan contains no retained content')
        if index.exists():
            inputs = json.loads(index.read_text(encoding='utf8'))
            for entry in inputs:
                if sha256(Path(entry['input_path'])) != entry['input_sha256']:
                    raise ValueError('Immutable derivative changed; use a new work directory')
            return inputs
        root.mkdir(parents=True, exist_ok=True)
        target = root / 'retained.pdf'
        page_map = []
        # Render allowed clips into new pages. A PDF clipping rectangle alone
        # would still embed the excluded original page's content/resources.
        with fitz.open() as derivative:
            for source_page, box, role in routes:
                rect = fitz.Rect(box)
                pixmap = source[source_page].get_pixmap(matrix=fitz.Matrix(200 / 72, 200 / 72), clip=rect, alpha=False)
                page = derivative.new_page(width=rect.width, height=rect.height)
                page.insert_image(page.rect, stream=pixmap.tobytes('png'))
                page_map.append(dict(input_page_idx=page.number, source_page_idx=source_page, bbox=box, role=role))
            derivative.save(target, garbage=4, deflate=True)
        inputs = [dict(input_path=str(target.resolve()), source_sha256=source_hash, input_sha256=sha256(target),
                       publication_input_sha256=plan_hash, page_map=page_map)]
        write_json(index, inputs)
        return inputs
