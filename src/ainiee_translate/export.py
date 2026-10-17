"""Export a translated CacheProject to output files.

Self-contained by default (vendored writers via io_dispatch). For formats not
shipped natively (e.g. Office), set AINIEE_REPO to fall back to AiNiee."""
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
                   formats=None, allow_partial=False, cache_root: Path | None = None,
                   book_settings=None, pdf_engines=None, publication_context=None) -> None:
    config = config or DEFAULT_CONFIG
    formats = list(dict.fromkeys(formats or (['epub'] if any(cf.extra.get('ainiee_pdf') for cf in project.files.values()) else ['source'])))
    if any(f not in ('source', 'md', 'epub', 'latex', 'typst', 'pdf') for f in formats):
        raise ValueError('Unknown export format')
    pdf_engines = list(dict.fromkeys(pdf_engines or ['latex', 'typst']))
    if any(engine not in ('latex', 'typst') for engine in pdf_engines):
        raise ValueError('Unknown PDF engine')
    for storage, cf in project.files.items():
        if (Path(storage).suffix.lower() == '.pdf' or cf.file_project_type in ('Pdf', 'PDF') or cf.extra.get('ainiee_pdf')):
            if cf.extra.get('ainiee_pdf', {}).get('backend') != 'pdf-to-epub':
                raise ValueError('Legacy PDF cache: create a new project from the source PDF; automatic migration is unsupported')
    structured = {sp: cf for sp, cf in project.files.items() if cf.extra.get('ainiee_pdf', {}).get('backend') == 'pdf-to-epub'}
    if structured and 'source' in formats:
        raise ValueError('Original-layout PDF output is unsupported; request EPUB, Markdown or a book template explicitly')
    ordinary = {sp: cf for sp, cf in project.files.items() if sp not in structured}
    if ordinary and any(fmt != 'source' for fmt in formats):
        raise ValueError('Cross-format export requires reviewed PDF book structure; use --format source for legacy projects')
    for storage, cf in structured.items():
        from .pdf_cache import apply_cache_to_book
        from .pdf_review import build_translation_manifest
        from .artifact_io import safe_relative, write_json
        from .pdf_bridge import run_cli, contract
        context = dict(publication_context or {})
        required = ('cache_path', 'glossary_path', 'prompt_path', 'review_path')
        if any(not context.get(key) for key in required):
            raise ValueError('PDF publication requires cache_path, glossary_path, prompt_path and review_path in publication_context')
        book_path = Path(cache_root or Path.cwd()) / cf.extra['ainiee_pdf']['book_source']
        book = json.loads(book_path.read_text(encoding='utf8'))
        target = apply_cache_to_book(book, cf, allow_partial=allow_partial)
        work = book_path.resolve().parent
        relative = Path(safe_relative(storage.replace('\\', '/'))).with_suffix('')
        out = Path(output_path) / relative
        out.mkdir(parents=True, exist_ok=True)
        wanted = formats
        manifest = build_translation_manifest(book, target, cf, work=work, **context)
        contract().validate_translation_binding(target, manifest, work)
        # Immutable run directories keep the source snapshots and previous publications.
        identity = contract().content_digest(target)[:16]
        publication = out / ('publication-' + identity)
        publication.mkdir(exist_ok=True)
        target_path = publication / 'book.translated.json'
        manifest_path = publication / 'translation-manifest.json'
        write_json(target_path, target)
        write_json(manifest_path, manifest)
        if 'epub' in wanted:
            epub = out / 'book.epub'
            run_cli('build', '--work', work, '--book', target_path,
                    '--translation-manifest', manifest_path, '--output', epub,
                    '--report-dir', publication / 'reports')
            run_cli('check', epub, '--output', publication / 'structure-check.json')
        for fmt in wanted:
            if fmt == 'md':
                from .book_markdown import export_markdown
                export_markdown(target, out / 'markdown', manifest=manifest, work=work)
        for engine in ('latex', 'typst'):
            if engine not in wanted and not ('pdf' in wanted and engine in pdf_engines):
                continue
            from .book_pdf import export_template_sources, compile_book_pdf
            source = export_template_sources(target, out / engine, engine=engine,
                                             settings=book_settings or {}, manifest=manifest, work=work)
            if 'pdf' in wanted and engine in pdf_engines:
                result = compile_book_pdf(source, engine=engine, output_path=source.with_suffix('.pdf'))
                if result['status'] != 'passed':
                    raise ValueError(f'{engine} PDF {result["status"]}: {result.get("diagnostic", "see compile log")}')
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
    if any(Path(sp).suffix.lower()=='.pdf' or cf.file_project_type in ('Pdf','PDF') or cf.extra.get('ainiee_pdf')
           for sp,cf in project.files.items()):
        raise ValueError('PDF fallback removed; create a new project from the source PDF')
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
    ap.add_argument('--format', dest='formats', action='append', choices=['source', 'md', 'epub', 'latex', 'typst', 'pdf'])
    ap.add_argument('--book-settings', help='JSON object overriding book template defaults')
    ap.add_argument('--pdf-engine', dest='pdf_engines', action='append', choices=['latex', 'typst'],
                    help='Compiler for --format pdf (repeatable; default: both)')
    ap.add_argument('--allow-partial', action='store_true')
    ap.add_argument('--locked', help='Validated locked glossary JSON')
    ap.add_argument('--prompt', help='Project translation prompt/config')
    ap.add_argument('--proofreading', help='Independent source comparison records')
    ap.add_argument('--decisions', help='Versioned human decisions')
    a = ap.parse_args(argv)
    proj = cache_io.load_cache(a.cache)
    export_project(proj, a.output, a.input, formats=a.formats, allow_partial=a.allow_partial,
                   cache_root=Path(a.cache).resolve().parent, pdf_engines=a.pdf_engines,
                   publication_context=dict(cache_path=a.cache, glossary_path=a.locked, prompt_path=a.prompt, review_path=a.proofreading, decisions_path=a.decisions),
                   book_settings=json.loads(Path(a.book_settings).read_text(encoding='utf8')) if a.book_settings else None)
    print(f"exported -> {a.output}")


if __name__ == "__main__":
    main()
