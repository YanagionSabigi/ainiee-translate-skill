"""Parse an input folder/file into a CacheProject.

Self-contained by default (vendored readers via io_dispatch). For formats not
shipped natively (e.g. Office), set AINIEE_REPO to fall back to AiNiee."""
import argparse
import os
import fnmatch
from pathlib import Path
from . import cache_io, io_dispatch


def _needs_ainiee(input_path: str, project_type: str) -> bool:
    """True when the input is a format we don't ship natively (e.g. PDF/Office)."""
    if project_type not in (set(io_dispatch.FORMATS) | {"AutoType"}):
        return True
    p = Path(input_path)
    return p.is_file() and p.suffix.lstrip(".").lower() not in io_dispatch.EXT_CANDIDATES


def _legacy_parse(input_path, project_type, exclude_rule):
    if project_type.upper() == 'PDF' or Path(input_path).suffix.lower() == '.pdf':
        raise ValueError('PDF input requires a new project using pdf-to-epub preparation')
    if _needs_ainiee(input_path, project_type) and os.environ.get("AINIEE_REPO"):
        from .ainiee_lib import load
        return load().FileReader().read_files(project_type, input_path, exclude_rule)
    return io_dispatch.parse_input(input_path, project_type, exclude_rule)


def parse_input(input_path: str, project_type: str = 'AutoType', exclude_rule: str = '', *,
                pdf_backend: str = 'auto', pdf_work: str | None = None, cache_root: Path | None = None,
                target_language: str = 'zh'):
    if pdf_backend not in ('auto', 'mineru'):
        raise ValueError('Unknown PDF backend')
    root = Path(input_path)
    excludes = [r for r in exclude_rule.split(',') if r]
    pdfs = ([root] if root.is_file() and root.suffix.lower() == '.pdf' else
            sorted(p for p in root.rglob('*') if p.is_file() and p.suffix.lower() == '.pdf') if root.is_dir() else [])
    pdfs = [p for p in pdfs if not any(fnmatch.fnmatch(p.name, rule) for rule in excludes)]
    if not pdfs:
        return _legacy_parse(input_path, project_type, exclude_rule)
    if project_type not in ('AutoType', 'Pdf', 'PDF'):
        raise ValueError('PDF input requires a new project using the pdf-to-epub workflow')
    from .artifact_io import sha256
    from .pdf_bridge import contract
    from .pdf_cache import book_to_cache_file
    import json
    project = io_dispatch.parse_input(input_path, 'AutoType', exclude_rule)
    base = root.parent if root.is_file() else root
    cache_root = Path(cache_root or Path.cwd()).resolve()
    next_index = max((i.text_index for i in cache_io.iter_items(project)), default=0) + 1
    for pdf in pdfs:
        storage = str(pdf.relative_to(base))
        work = (Path(pdf_work) / sha256(pdf) if pdf_work and root.is_dir() else Path(pdf_work)
                if pdf_work else cache_root / 'pdf' / sha256(pdf))
        book_path = work / 'book.source.json'
        if not book_path.exists():
            raise ValueError(f'PDF preparation required: inspect "{pdf}" --out "{work}", then extract, draft and prepare --work "{work}" using pdf-to-epub')
        book = json.loads(book_path.read_text(encoding='utf8'))
        contract().validate_v2(book)
        if book['source_sha256'] != sha256(pdf):
            raise ValueError('Prepared book source differs from input PDF')
        cf = book_to_cache_file(book, storage_path=storage,target_language=target_language)
        cf.extra['ainiee_pdf']['book_source'] = os.path.relpath(book_path, cache_root)
        cf.extra['ainiee_pdf']['work'] = os.path.relpath(work, cache_root)
        project.files[storage] = cf
        for item in project.files[storage].items:
            item.text_index = next_index; next_index += 1
    project.input_path = str(root)
    project.project_type = 'Pdf' if root.is_file() else 'AutoType'
    io_dispatch._generate_project_name(project)
    return project


def main(argv=None):
    ap = argparse.ArgumentParser(description="Parse input -> cache.json")
    ap.add_argument("--input", required=True)
    ap.add_argument("--type", default="AutoType")
    ap.add_argument("--exclude", default="")
    ap.add_argument("--out", default="cache.json")
    ap.add_argument('--pdf-backend', choices=['auto', 'mineru'], default='auto')
    ap.add_argument('--pdf-work')
    ap.add_argument('--target-language',default='zh',help='PDF translation target language (BCP47; default zh)')
    a = ap.parse_args(argv)
    if Path(a.out).exists():
        raise FileExistsError('Cache already exists; use a new --out path to avoid overwriting translations')
    proj = parse_input(a.input, a.type, a.exclude, pdf_backend=a.pdf_backend,
                       pdf_work=a.pdf_work, cache_root=Path(a.out).resolve().parent,target_language=a.target_language)
    cache_io.save_cache(proj, a.out)
    print(f"parsed {proj.count_items()} items -> {a.out}")


if __name__ == "__main__":
    main()
