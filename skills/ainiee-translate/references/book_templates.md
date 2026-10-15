# Optional book templates

Use only after the [PDF workflow](pdf_workflow.md) has produced a reviewed source
book and completed translation cache. These exporters preserve the same target
structure used by Markdown/EPUB. They never reparse a PDF or change the cache.
Legacy flat PDF caches require a separate reviewed structured project first.

## Local tools

- LaTeX: XeLaTeX with ctexbook, fontspec/xeCJK, geometry, amsmath, longtable,
  hyperref/bookmark, titlesec/titletoc, fancyhdr, TikZ, needspace and the packages
  used by the bundled MIT Rosé Pine theme, plus fvextra for literal code blocks.
  Tested with TeX Live 2024.
- Typst: tested with 0.15.1. Verified TeX math requires Pandoc's JSON-to-Typst
  writer (tested with 3.12.1); conversion warnings fail rather than substituting
  incorrect mathematics. Image fallback is allowed only when evidenced in review.
- Both defaults use Latin Modern Roman, STZhongsong and DejaVu Sans Mono.
  Install local licensed fonts or override the font settings. Fonts are not
  shipped. LaTeX explicitly uses synthetic bold/italic for the CJK font.
  Typst may need `TYPST_FONT_PATHS` pointing at a TeX font directory; verify it
  with `typst fonts`. A compiler executable alone does not prove font readiness.

Set `AINIEE_XELATEX`, `AINIEE_TYPST` and `AINIEE_PANDOC` to executable paths if
they are outside PATH. Commands use argument arrays; paths with spaces are
supported. Tools are never downloaded automatically. TeX shell escape is disabled;
Typst compiles within the generated source directory. No online Typst packages
are imported. Reviewed mathematics and editable sources must still be trusted
before compiling them manually with different settings.

## Export

```bash
# Editable sources only (LaTeX does not require its compiler at this step).
python -m ainiee_translate.export --cache work/cache.json --input book.pdf \
  --output out --format latex --format typst --book-settings book.settings.json

# Compile both routes, retaining the editable sources, relative assets and logs.
python -m ainiee_translate.export --cache work/cache.json --input book.pdf \
  --output out --format pdf --book-settings book.settings.json

# Or compile only one route.
python -m ainiee_translate.export --cache work/cache.json --input book.pdf \
  --output out --format pdf --pdf-engine latex
```

Each source gets its own `out/<source-name>/latex/` or `typst/` directory.
Results include `book.tex`/`book.typ`, `book.pdf` when compilation passes,
`book.settings.json`, `source-manifest.json`, `assets/`, and compile log/report.
LaTeX also includes the theme, license and any literal `code/` files. Move the
whole directory together.
The compile report uses `passed`, `failed` or `unavailable`. Missing glyph,
overflow, unresolved-reference and compiler warnings block formal publication.
A failed compile preserves an old PDF but reports failure; that old file is not
evidence for the new source. `--allow-partial` produces `book.draft.*` and a
missing-unit list, visibly labeled as a diagnostic draft.

## Settings and publication policy

`--book-settings` reads a UTF-8 JSON object. Omitted values use book metadata and
the bundled `templates/book/book.defaults.yaml` (JSON is a YAML subset):

```json
{
  "title": "书名", "author": "作者", "translator": "译者", "language": "zh",
  "page_size": "a4", "margin_mm": 20, "font_size": 12,
  "font_latin": "Latin Modern Roman", "font_cjk": "STZhongsong",
  "font_mono": "DejaVu Sans Mono", "toc": true, "page_numbers": true
}
```

Supported page sizes: `a4`, `a5`, `letter`; margins 10–40 mm; body size 8–18 pt.
Unknown keys, invalid types and out-of-range settings fail. Chapter headings,
captions and chapter-end notes follow fixed template policy. Contents entries
and PDF bookmarks use the reviewed source mapping; contents remains at its
reviewed position, with live page references. Notes reset per chapter and every
occurrence has its own return link. Source cover/back-cover images stay first;
the Dawn title page is generated only when there is no source cover.

Language settings support a two/three-letter language with an optional four-letter
script and two-letter region, such as `zh-Hans-CN` or `en-US`. Typst receives the
primary language and region separately. Other BCP 47 variants fail with an explicit
setting error. Titles render protected mathematics in contents; internal translation
markers never become printed headings or bookmarks. Formula crops remain inline
when their source node is inline, respecting the reviewed relative image width.
Tables normally repeat the first row on continuation pages; a header containing
note references is shown only once to keep its source anchors unique.

The LaTeX theme is fixed to rosepine-latex commit
`c717041d54b5eb5f5f153b97a3a606c147e37402`, MIT © 2026 yfff.
Typst independently uses the same palette; pagination and font metrics can differ.
Review the compiled PDF: open contents links and every note return, examine
chapter boundaries, table continuation, formulas, captions and glyphs. Compiler
success does not establish source fidelity or correct mathematical translation.
