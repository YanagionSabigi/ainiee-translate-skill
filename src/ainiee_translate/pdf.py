"""Explicit PDF preparation stages; no translation cache is modified here."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from .mineru_local import extract_bundle, import_bundle, sha256, digest, write_json, MinerUError
from .pdf_publication import inspect_pdf, prepare_extraction_inputs


def read_json(path: Path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def extract_work(work: Path, *, python: Path | None = None, env=None):
    work = Path(work)
    inspection = read_json(work / 'inspection.json')
    source = Path(inspection['source_path'])
    if sha256(source) != inspection['source_sha256']:
        raise ValueError('Source changed after inspection; use a new work directory')
    plan = read_json(work / 'publication-input.json')
    inputs = prepare_extraction_inputs(source, plan, work)
    python = python or (Path(os.environ['AINIEE_MINERU_PYTHON']) if os.environ.get('AINIEE_MINERU_PYTHON') else None)
    if python is None:
        raise MinerUError('Set AINIEE_MINERU_PYTHON to the isolated MinerU Python interpreter')
    imports = []
    for entry in inputs:
        bundle = extract_bundle(Path(entry['input_path']), work / 'runs', python=python, env=env or {})
        imported = work / 'imports' / sha256(bundle)
        manifest = import_bundle(bundle, imported)
        imports.append({**entry, 'bundle': str(bundle.relative_to(work)),
                        'root': str(imported.relative_to(work)), 'manifest': manifest})
    extraction = dict(schema='ainiee-pdf-extraction/1', source_sha256=inspection['source_sha256'],
                      publication_input_sha256=digest(plan), imports=imports, status='completed')
    write_json(work / 'extraction.json', extraction)
    return extraction


def draft_work(work: Path):
    work = Path(work)
    path = work / 'publication.review.json'
    if path.exists():
        return read_json(path)
    extraction = read_json(work / 'extraction.json')
    if extraction.get('status') != 'completed':
        raise ValueError('Complete extraction before drafting structure')
    candidates = []
    for imp in extraction['imports']:
        middle = read_json(work / imp['root'] / imp['manifest']['middle_json'])
        page_map = {row['input_page_idx']: row for row in imp['page_map']}
        for page in middle['pages']:
            if page['page_idx'] not in page_map:
                raise ValueError('Missing original page/region mapping')
            for block in page['blocks']:
                candidates.append(dict(raw_id=f"{imp['manifest']['bundle_sha256']}/p{page['page_idx']}/b{block['index']}",
                                       source_ref=page_map[page['page_idx']], block=block))
    review = dict(schema='ainiee-pdf-review/1', source_sha256=extraction['source_sha256'],
                  extraction_sha256=digest(extraction), reviewed=False, evidence='', candidates=candidates,
                  resolutions=[], chapters=[], blocks=[], notes=[], assets=[], toc={}, issues=[])
    write_json(path, review)
    return review


def main(argv=None):
    parser = argparse.ArgumentParser(description='Prepare a reviewed local MinerU PDF project')
    sub = parser.add_subparsers(dest='command', required=True)
    for name in ('inspect', 'extract', 'draft', 'normalize'):
        command = sub.add_parser(name)
        command.add_argument('--work', type=Path, required=True)
        if name == 'inspect':
            command.add_argument('--input', type=Path, required=True)
    args = parser.parse_args(argv)
    if args.command == 'inspect':
        inspect_pdf(args.input, args.work)
    elif args.command == 'extract':
        extract_work(args.work)
    elif args.command == 'draft':
        draft_work(args.work)
    else:
        from .book_model import normalize_book
        normalize_book(args.work)
    print(f'{args.command}: {args.work}')


if __name__ == '__main__':
    main()
