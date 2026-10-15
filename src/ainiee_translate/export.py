"""Export a translated CacheProject to output files.

Self-contained by default (vendored writers via io_dispatch). For formats not
shipped natively (e.g. PDF / Office), set AINIEE_REPO to fall back to AiNiee."""
import argparse
import os
import copy
import json
from pathlib import Path
from . import cache_io, io_dispatch

DEFAULT_CONFIG = {
    "translated_suffix": "_translated",
    "bilingual_suffix": "_bilingual",
    "bilingual_order": "translation_first",
}


def export_project(project, output_path: str, input_path: str, config: dict | None = None, *,
                   formats=None, allow_partial=False, cache_root: Path | None = None) -> None:
    config = config or DEFAULT_CONFIG
    formats = list(dict.fromkeys(formats or ['source']))
    if any(f not in ('source', 'md', 'epub') for f in formats):
        raise ValueError('Unknown export format')
    structured = {sp: cf for sp, cf in project.files.items() if cf.extra.get('ainiee_pdf', {}).get('backend') == 'mineru'}
    ordinary = {sp: cf for sp, cf in project.files.items() if sp not in structured}
    if ordinary and any(fmt != 'source' for fmt in formats):
        raise ValueError('Cross-format export requires reviewed PDF book structure; use --format source for legacy projects')
    for storage, cf in structured.items():
        from .pdf_cache import apply_cache_to_book
        from .book_markdown import export_markdown
        from .mineru_local import safe_relative
        book_path = Path(cache_root or Path.cwd()) / cf.extra['ainiee_pdf']['book_source']
        book = json.loads(book_path.read_text(encoding='utf8'))
        target = apply_cache_to_book(book, cf, allow_partial=allow_partial)
        target['provenance']['work'] = str(book_path.resolve().parent)
        relative = Path(safe_relative(storage.replace('\\', '/'))).with_suffix('')
        out = Path(output_path) / relative
        wanted = list(dict.fromkeys('md' if f == 'source' else f for f in formats))
        if 'source' in formats:
            print(f'{storage}: MinerU source format is Markdown')
        for fmt in wanted:
            if fmt == 'md':
                export_markdown(target, out)
            else:
                from .book_epub import export_epub
                export_epub(target, out / ('book.draft.epub' if target.get('diagnostic_draft') else 'book.epub'))
        if target.get('diagnostic_draft'):
            from .mineru_local import write_json
            write_json(out / 'missing-units.json', target['missing_units'])
    if not ordinary:
        return
    project = copy.copy(project)
    project.files = ordinary
    exts = {Path(sp).suffix.lstrip(".").lower() for sp in project.files}
    if not exts <= set(io_dispatch.EXT_CANDIDATES) and os.environ.get("AINIEE_REPO"):
        _export_via_ainiee(project, output_path, input_path, config)   # PDF/Office/etc.
    else:
        io_dispatch.export_project(project, output_path, input_path, config)


def _export_via_ainiee(project, output_path, input_path, config) -> None:
    """Fallback for formats not shipped natively (requires AINIEE_REPO)."""
    import sys
    from .ainiee_lib import load, repo_path
    repo = repo_path()
    if repo not in sys.path:
        sys.path.insert(0, repo)
    try:
        from ModuleFolders.Domain.FileOutputer import WriterUtil
        cfg = WriterUtil.get_ainiee_config()
        if getattr(cfg, "keep_original_encoding", None) is None:
            cfg.keep_original_encoding = False
    except Exception:
        pass
    load().FileOutputer().output_translated_content(project, output_path, input_path, config)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Export cache.json -> output files")
    ap.add_argument("--cache", required=True)
    ap.add_argument("--output", required=True)
    ap.add_argument("--input", required=True)
    ap.add_argument('--format', dest='formats', action='append', choices=['source', 'md', 'epub'])
    ap.add_argument('--allow-partial', action='store_true')
    a = ap.parse_args(argv)
    proj = cache_io.load_cache(a.cache)
    export_project(proj, a.output, a.input, formats=a.formats, allow_partial=a.allow_partial,
                   cache_root=Path(a.cache).resolve().parent)
    print(f"exported -> {a.output}")


if __name__ == "__main__":
    main()
