# Local MinerU PDF migration: implementation and validation

Core status: [upstream draft PR #3](https://github.com/xuanji86/ainiee-translate-skill/pull/3); not released. LaTeX/Typst template work is a separate follow-up; see [template design](book-template-design.md) and its validation report.

## Behavior

New PDFs default to an isolated local MinerU process. A source-bound publication plan precedes extraction; reviewed semantic structure precedes translation-cache creation. Stable unit IDs distinguish repeated sentences independently of `text_index`. Translation and polish share an immutable-token gate, including when force is requested. Markdown and EPUB 3 use the same reviewed publication mapping, portable resources, chapter note numbering and complete repeated-reference returns.

Legacy PDF caches keep the original writer, and explicit `--pdf-backend babeldoc` remains available. Unsupported cross-format requests fail explicitly. Native EPUB/TXT and the original Office fallback remain in place. Existing installed skills and private runtime configurations are not replaced by this branch.

See [the PDF workflow](../skills/ainiee-translate/references/pdf_workflow.md) for preparation, review fields, recovery, translation and export commands.

## Evidence collected on 2026-10-15

| Layer | Observed result | Scope |
| --- | --- | --- |
| Upstream baseline | 106 tests passed | Original upstream commit `a0a27819791cc2e2c2491b9a9d95c904f39bfd5a` |
| Final regression suite | 198 tests passed, no skips | Python 3.12.10; official EPUBCheck optional test enabled |
| Local parser | Passed | MinerU 4.0.10, DocVortex 0.5.8, Standard; effective local config checked |
| Real source fixture | Passed | Self-authored four-page PDF: front/back images, digital two-column content, formula, figure/caption, repeated sentences/references, raster continuation and bibliography |
| Translation workflow | Passed | Source review → 14 translation units → project glossary Schema validation → batch write → polish → verify/audit → MD/EPUB; source/translation states remain independent |
| Actual resume | Passed | Same fingerprint reused validated raw results; existing translated cache bytes unchanged |
| EPUB conformance | Passed | Official EPUBCheck 5.4.0: zero errors and warnings on the real sample; local structure check reported independently |
| Reader | Passed for sample | Locally served EPUB.js engine shipped with MinerU 4.0.10; actual ZIP opened; engine/ZIP hashes retained locally |
| Reader dimensions | Checked | 830×1005 at 16px, 420×700 at 22px, and restored 830×1005 at 22px |
| Reader interactions | Checked | Contents navigation, chapter/section reflow, relative formula/image sizes, caption, both repeated note references and their separate returns |
| Generated skill bundle | Passed | `python build.py --check`; bundled parse → batch write → MD/EPUB export on the actual fixture |
| Wheel | Passed | Built, contents audited, installed offline in a separate environment; PDF help and actual MD/EPUB export ran from installed wheel |
| Private-file boundary | Passed | `local/`, runtime/output/config examples ignored; no private runtime files tracked; wheel includes package resources and required attribution only |

The final full-suite command was `python -m pytest --basetemp local/pytest-final` with `EPUBCHECK_JAR` configured: **198 passed in 90.39s**. A sandbox restriction prevented the upstream local HTTP test from opening a socket, so the baseline and final full suites were run on the host. This was an execution-environment restriction, not a skipped assertion.

## Review findings addressed

Each issue had a reproducing failure before its fix:

- Partial/empty MiddleJson or mismatched expected page coverage cannot become a completed source book.
- Textual semantic blocks need nonempty source text and translation units; raw IDs alone cannot hide omitted prose.
- Table note numbers follow rendered cell order rather than the flat order of cell definitions.
- Unreferenced registry assets stay outside publication outputs.
- EPUB-only partial export writes its missing-unit report.
- Unsupported legacy format combinations are rejected instead of dropping a requested output.
- Nested semantic image/caption nodes enter the review inventory individually.
- The note ARIA role was corrected after an official EPUBCheck failure.
- Wheel inspection found and corrected missing vendored attribution data.

A separate reviewer checked the whole canonical implementation and five documentation scenarios. Fixes were verified by reproducing tests and the final green suite. The reviewer did not independently certify the local model, reader or legacy application runtime; the model/reader observations above were performed separately.

## Limits and remaining release work

- Actual inference cancellation/resumption after interruption was not exercised on the GPU runtime. Cancellation/error/config/input invalidation have isolated adapter and workflow tests; real same-fingerprint resume was exercised.
- Live BabelDOC and Office parse/export were not exercised with the original application runtime. Their dispatch compatibility is covered by regression tests, which is narrower evidence.
- The mathematical reader check covers the self-authored formula. Complex mathematical notation and other reader engines need their own source comparison and rendering acceptance.
- Original-source paragraph joins and difficult cross-page note associations still require human source evidence; the sample does not certify every such case.
- A project's own glossary Schema/style must be supplied and reviewed for that project. The sample used a self-authored test Schema/style, not a private schema promoted into the package.
- No fork push, GitHub PR, installed-skill replacement or template release was performed. Keep release acceptance and publication as explicit subsequent work.

Version numbers remain at the upstream release values on this unreleased branch; plugin descriptions were updated. Build the generated bundle with `python build.py` on Windows (same file/deletion/exclusion semantics as `build.sh`), and check with `python build.py --check`.

The wheel's initial import emits an existing vendored `AssReader` docstring escape `SyntaxWarning`; export still completed. That unrelated upstream warning was not changed here.

## Sources and licenses

EPUB packaging follows [W3C EPUB 3.3](https://www.w3.org/TR/epub-33/); official checking follows [EPUBCheck CLI documentation](https://www.w3.org/publishing/epubcheck/docs/cli/). The wire Schema was generated from MIT-licensed DocVortex 0.5.8 with its notice retained. Existing AGPL and AiNiee attribution are preserved, including in the wheel. Publication CSS is an original implementation; personal pdf-to-epub scripts/CSS are not distributed.
