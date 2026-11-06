# Release template review — 2026-11-06

## Scope and method

Read-only review of the original `development/ainiee-translate-skill` template branch: all changed Python packaging/bridge/publication modules, documentation and tests from `git diff HEAD`, and the new `assets/template` materials. Checked source and bundled paths, dependencies/imports, source/example JSON, PDF metadata/text/attachment inventory, EPUB ZIP resource bytes, and local third-party notices. No original files changed; no TeX executed; no full test suite, publication, push, or PR performed.

The four new TeX/PDF pairs are standalone examples, not templates wired to the current automatic exporter. This is consistent with their implementation; release notes must preserve that boundary.

## Original release findings and resolution

1. **[P1] Preserve the MathTranslations MIT notice with redistributed reference files.** `src/ainiee_translate/assets/template/tex/reference/mathtranslations/` contains the complete reference TeX and `logo.pdf` without a license or copyright notice. The installed source skill has both `LICENSE` and `NOTICE.md`, and explicitly records the copyright holder’s authorization to distribute these files under MIT. Both new files are byte-identical to that licensed source. Copy its `LICENSE` and attribution/authorization notice alongside the reference files, and mirror them into the shipped skill bundle. MIT requires its copyright and permission notice with copies; the project-level AGPL notice does not replace this. This is an omission with a readily available local fix, not a request to seek new permission.

   Licensed-source evidence: `C:/Users/10166/.codex/skills/mathtranslations-skill-main/LICENSE`, `NOTICE.md`.
   TeX SHA-256: `b2cc106209969e77878f3ba6dfe0bf050d4d38da0c68e558a96241350827531e`.
   Logo SHA-256: `8b3839adbf870a8c5e825c9f004125816835bbb321617e619e5f589b672fc8d5`.

2. **[P1] Include the new template tree in package data.** Original `pyproject.toml` includes only specific EPUB template directories, so wheel installs omit `assets/template/README.md`, `tex/**` (four editable TeX/PDF pairs and reference notices) and `typst/README.md`. The integration owner has already planned this repair. Include the complete intended tree, build the wheel, and inspect its ZIP inventory. Run the existing bundle sync/check after copying all untracked materials.

Both required source changes were verified in the integration checkout after the owner’s repair: the MathTranslations `LICENSE` and `NOTICE.md` are present, package-data covers root/typst/three-level TeX resources, and the template README states v2.3.0 distribution while preserving the standalone-export boundary. Built wheel/ZIP verification remains the integration owner’s final check.

## Nonblocking documentation corrections

- The reference EPUB README cites `publication_skill/docs/audit-20261105.md`, which is absent from the shipped publisher. Either include a sanitized corresponding report or describe the validation limits without pointing to an unavailable file.
- `publication_skill/README.md` instructs running `unittest discover -s tests`, but `publication_files()` intentionally ships only scripts/assets/references/docs and there is no publisher tests directory in this source tree. Make the instructions point to available repository tests or label the upstream command as such. The missing tests do not affect runtime imports.

## Checks and findings

- New publication helper imports (`epub_chemistry`, `epub_figures`, `epub_navigation`, `epub_split`, `epub_weread`) resolve inside the bundled publisher scripts; they require only Python standard-library modules. Existing PDF/formula tools remain optional, externally provisioned dependencies. No new undeclared Python runtime dependency found.
- The two example rebuild scripts resolve `HERE.parents[3]/publication_skill/scripts` correctly from the packaged `assets/template/epub/<example>` location. Source and fixture metadata identify authored synthetic examples, not extracted private books.
- New TeX examples use TeX-distribution packages and Fandol fonts; they do not load user-local paths or the reference logo. XeLaTeX/CTeX and the required TeX packages remain prerequisites for manually compiling these independent examples.
- Rosé Pine reference includes MIT `LICENSE` and a `NOTICE` with upstream URL and exact commit. No font files are redistributed as loose template resources.
- Four example PDFs have 4/10 pages as expected (article/book), no embedded attachments, empty author/title/subject fields, and normal LaTeX producer metadata. The reference logo is one page, without attachments or personal author metadata. Text extraction identified example headings/content. No private book PDF is present in the new template tree.
- Scanned text/JSON/TeX/docs and the two EPUB ZIP payloads for personal absolute paths (`Users`, `OneDrive`, account identifier, home directories): no matches in the new public template materials. The publication compatibility document mentions a book title, resource identifiers, counts and validation hashes, but does not include the original book, credentials, account snapshots or personal filesystem paths.
- No further release-blocking runtime defect established from this review. This is source/resource review, not a replacement for the integration owner’s tests and built-artifact checks; no actual reader acceptance or fresh TeX compilation was performed.

## Conclusion

No remaining source/resource release blocker found after the two fixes. Proceed once the integration owner’s built wheel and skill ZIP inventory confirms the complete template tree. The owner separately reports all four templates compiled twice with XeLaTeX and all 28 preview pages visually checked; this review did not rerun those checks. Resolve the small documentation inaccuracies where practical. No PR is required or authorized by this review.
