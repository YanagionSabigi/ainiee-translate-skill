# Template validation

This follows the independently delivered [core draft PR](https://github.com/xuanji86/ainiee-translate-skill/pull/3).
The implementation and visual target are in [book-template-design.md](book-template-design.md).
No books, translations, compiler binaries, fonts, personal configuration or local
absolute paths are included in the public repository.

## Exercised tools and sources

- XeLaTeX / TeX Live 2024, with its actual ctexbook/longtable/theme dependencies.
- Typst 0.15.1 (`9dfd3a08`), official portable Windows build.
- Pandoc 3.12.1, official portable Windows build; its real JSON AST Typst writer
  converted inline powers, a Gaussian integral/fraction/root and matrix products.
- Installed STZhongsong and DejaVu Sans Mono; Latin Modern Roman from the local
  TeX font tree, explicitly exposed to Typst. Font files are not redistributed.
- Rosé Pine reference commit `c717041d54b5eb5f5f153b97a3a606c147e37402`, MIT.
  The reference Chinese starter and preview were examined before implementation.

Both engines consumed the same translated structured book. The core's self-authored
mixed digital/scanned PDF produced five LaTeX pages and four Typst pages. A separate
self-authored stress book produced six pages in each engine: Chinese and
Latin text, bold/italic, literal metacharacters, inline/display math, integral and
matrices, a figure/caption, a 75-row table, two chapters, a repeated note and a
second chapter whose note numbering starts at 1.

## Results

- All four real compilations passed with no final compiler warnings, missing
  glyphs, reported overflow or undefined references. Compiler logs/status and
  source/output SHA-256 records are retained in the private acceptance directory.
- PDF inspection found the expected chapter/section outline targets and resolved
  internal links. The repeated note has two distinct return destinations. Source
  cover/back-cover precede the reviewed contents; both engines calculate their
  own contents page references rather than copying source pagination.
- Poppler rendered every page. Visual inspection covered original cover/back-cover,
  the Dawn title page, contents, chapter openings, caption, inline/display math,
  integral/matrices, table continuation and notes at both chapter ends. The first
  TeX render exposed an orphan note heading; it was fixed and rendered again.
- The final full source suite passed 223 tests, including 25 template tests and official
  EPUBCheck. `build.py --check` passed. The canonical source and skill bundle share
  the same template files.
- A wheel built and installed offline into the separate acceptance environment.
  Its real CLI generated both editable sources and a Typst PDF. The bundled skill
  import path independently generated both sources. Both distributions contained
  defaults, the theme, MIT LICENSE and NOTICE.

## Independent review and regression evidence

An independent review reproduced five issues: note anchors repeated in continuation
headers; protected math markers printed in contents; inline formula crops enlarged
as block images; locale tags passed unsplit to Typst; and LaTeX code blocks losing
indentation/blank lines. Eight new tests reproduced these before correction. All
25 template tests then passed. A combined regression book compiled in both real
engines with a math title, 100-row table containing a header note, an exact 2 em
inline image fallback, `zh-Hans-CN`, and literal code with indentation, empty lines
and an apparent environment terminator. Each regression PDF has six pages; all
internal links resolve, the note has three distinct returns, the printed formula
title contains no internal marker, and the 2 em crop measures about 25.11 PDF points
in the scaled LaTeX font and 24 points in Typst. The final regression pages were
rendered and inspected, including contents and literal code. Code is read verbatim from relative files;
headers with notes do not repeat their semantic anchors. No theme files were altered.

These results cover the specified tools, fixtures and default A4 typography, not
every TeX command, font, language, page size or arbitrary book. Different engines
produce different spacing and pagination. Compiler success and resolved links do
not establish linguistic quality, source fidelity or universal PDF accessibility.
Core runtime limitations (including unmeasured live inference cancellation and
legacy BabelDOC/Office export) remain recorded in the core validation report.
