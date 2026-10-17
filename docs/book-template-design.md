# Book templates

This optional follow-up consumes the same reviewed, translated `ainiee-book/1`
as Markdown and EPUB. It never extracts a PDF or changes a translation cache.
The core MinerU PR is independently usable.

## Reference and visual target

The MIT-licensed [rosepine-latex](https://github.com/Yalyenea/rosepine-latex)
reference is fixed at `c717041d54b5eb5f5f153b97a3a606c147e37402`.
Its actual Chinese book starter uses XeLaTeX, ctexbook, Latin Modern Roman,
STZhongsong, A4 with 20 mm margins, pine chapter headings, rose rules and a
Dawn title page. The shared theme files are redistributed with their license.
The Typst template independently applies the same palette and book structure;
it does not claim identical font metrics or pagination.

Source cover/back-cover images stay first in their reviewed order. A template
title page is generated only when there is no source cover. The visible contents
uses only reviewed bookmark mappings, at its reviewed position, with live page
references. Notes remain at each chapter end, reset from 1, with one return link
per occurrence. Paragraphs, mixed Latin/Chinese text, italic/bold spans, captions,
figures, breakable tables and verified math remain structured.

## Boundary and settings

`book_pdf.export_template_sources` validates publication, writes a standalone
source directory with relative assets, effective settings and provenance.
Templates live inside the canonical Python package so wheels and skill bundles
contain the same files. JSON settings (also valid YAML) cover title, author,
translator, language, A4/A5/letter, margin, font size, Latin/CJK/monospace fonts,
contents and page numbers. Heading style, caption style and chapter-end notes
are fixed template policy. Unknown/invalid settings fail before writing files.

LaTeX emits verified TeX mathematics directly. Typst sends math nodes through
Pandoc's JSON AST and real Typst writer. Pandoc warnings/conversion failure stop
publication; no regex TeX conversion or silent image substitution is used.
Evidenced source-image formula fallbacks remain images in either route.

`compile_book_pdf` uses argument arrays, local compilers, a fixed project root,
no TeX shell escape, bounded execution, and separate logs/status. Missing tools,
compiler failure, missing glyphs, overflow and unresolved links are surfaced;
an old output PDF is never accepted as a new successful build. No package is
downloaded by the exporter. Paths may be configured with `AINIEE_PANDOC`,
`AINIEE_XELATEX`, `AINIEE_TYPST`; these tools are optional for core users.

## Verification

Tests first cover Chinese punctuation/escaping, mixed styles, complex math,
long tables, chapter boundaries, all note returns, relative assets and missing
tools. Real acceptance uses the core self-authored sample plus a long-table/math
stress book, compiles both routes, examines diagnostics, PDF text/link structure,
and renders representative title, contents, chapter, formula, table and note
pages. Tool versions, source/output hashes and the exact visual scope are
recorded separately from unit-test results.
