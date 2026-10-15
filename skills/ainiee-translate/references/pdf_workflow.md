# Reviewed local PDF translation

Use this workflow for new PDF projects. `auto` selects local MinerU; a configured `AINIEE_REPO` does not change that default. Read the source pages to decide roles, structure, reading order and note associations.

## Prepare the two environments

The lightweight Ainiee environment needs `pymupdf jsonschema latex2mathml` in addition to the normal dependencies (`pip install -e '.[pdf]'` when using the repository). MinerU stays in its own environment. Set `AINIEE_MINERU_PYTHON`, `MINERU_HOME`, and `MINERU_CONFIG`; see the repository `.env.example` for portable placeholders. Environment files are examples, not automatically loaded.

The tested protocol is MinerU 4.0.10 / DocVortex 0.5.8, `docvortex.middle/2.0`. The preflight reads MinerU's effective config, including inherited environment overrides. It requires `model.source=local`, an empty `model.vlm.server_url`, disabled LLM-aided features and an existing model directory. Directory presence does not establish model health; extraction can still fail with a model diagnostic. Configure/download models explicitly in MinerU beforehand. A failure keeps diagnostics and state; retry the same command after resolving it. No upload, automatic model download, backend downgrade or BabelDOC fallback occurs.

## Review before extraction

Commands below assume the selected Ainiee Python and the skill's `scripts` directory on `PYTHONPATH`.

```bash
python -m ainiee_translate.pdf inspect --input /path/to/book.pdf --work work/pdf/book
# Review work/pdf/book/inspection.json and its page previews.
# Edit publication-input.json, then:
python -m ainiee_translate.pdf extract --work work/pdf/book
python -m ainiee_translate.pdf draft --work work/pdf/book
```

`publication-input.json` uses `schema: ainiee-publication-input/1`, the original `source_sha256`, `reviewed: true`, an `evidence` description and one entry in `pages` for every physical page, in order. Physical `page` is 1-based. Each page requires `role` and `evidence`.

- Retained roles: `content`, `preface`, `bibliography`.
- Excluded roles: `cover`, `back-cover`, `belly-band`, `copyright`, `publication-info`, `printed-toc`, `term-index`.
- A retained mixed page may have ordered `regions`, each containing `bbox: [x0,y0,x1,y1]`, a retained `role` and `evidence`. Coordinates are original PDF points; regions cannot overlap. Only these clips enter extraction. Covers remain available as full-page publication images.

The input PDF is preserved. Allowed regions are rendered into new PDF pages so excluded original resources are absent. Original `source_sha256` and derivative `input_sha256` stay distinct. Page maps connect zero-based extracted page indices to original pages and regions.

## Review the extracted structure

`publication.review.json` begins unreviewed. `draft` preserves an existing review. Compare every candidate against source pages, including nested image/table/caption nodes. Keep immutable imports unchanged and make corrections in the review.

The review has `schema: ainiee-pdf-review/1`, source/extraction hashes, `reviewed`, `evidence`, `metadata`, `chapters`, `blocks`, `notes`, `assets`, `toc`, `resolutions`, and `issues`:

- `metadata`: target publication `title` and BCP 47 `language`; optional `identifier`.
- `chapters`: unique `id`, original `source_title`, and either `title_block_id` pointing to its translatable heading or a reviewed target `display_title`. Keep source order, including prefaces before the original contents position.
- `blocks`: unique `id`, `chapter_id`, `kind`, and `raw_ids` from the candidate inventory. A joined paragraph may cite several raw IDs; record its source evidence. Supported kinds: `heading` (with `level`), `paragraph`, `caption`, `note`, `figure` (`asset_id`), `formula`, `table` (`rows` of table-cell IDs), `table-cell`, and literal `code` (`code` text). Translatable blocks carry `source_text`; normalization creates stable `unit_id` and original `source_refs`. Resolve every raw node as content or an evidenced `resolutions` entry (`raw_id`, `action: omitted|resolved`, `evidence`). Unresolved semantic coverage blocks normalization.
- `inlines`: block-local mapping from a unique `⟦AT:kind:id⟧` token to its payload. Supported payload `kind`: `note` (`note_id`), `math` (source-verified `tex`, `verified: true`, or `asset_id` plus `fallback_reason`), `code` (`text`), `image` (`asset_id`), `literal` (`text`). Literal source collisions are escaped and recorded. Preserve `<i>/<b>` source styles. Unsupported structures require an evidenced resolution; they are never silently dropped.
- `assets`: unique `id`, WORK-relative `path`, `sha256`, `media_type`, and a relative `width_em` when appropriate. Formula fallback images must be exact source regions. Front images additionally use `role: cover|back-cover` and `source_page_idx`, bound to the reviewed source role. Only a cover is marked cover-image.
- `notes`: unique `id`, `chapter_id`, body `block_ids`, `original_label` and `association_evidence`. Map every body reference explicitly. Repeated references use distinct tokens pointing to the same note. Publication assigns chapter-reset numbers and a return link for every reference. Resolve cross-chapter or missing associations before formal export.
- `toc`: `source: pdf-bookmarks`, `evidence`, `entries` mapping each `bookmark_index` to `target` and `level` (1 chapter, 2 section heading), and `placement: {before: CHAPTER}` or `{after: CHAPTER}`. For contents inside frontmatter use `{chapter: CHAPTER, before_block: BLOCK}`. Every original bookmark needs a mapping or an evidenced `omissions` entry. Deeper headings stay in the body. Keep original titles distinct from translated display titles. Missing bookmarks block this publication workflow; do not invent them.

```bash
python -m ainiee_translate.pdf normalize --work work/pdf/book
python -m ainiee_translate.parse --input /path/to/book.pdf \
  --pdf-work work/pdf/book --out work/cache.json
```

Without `--pdf-work`, preparation defaults beside the output cache under `pdf/<source-sha256>`. For a directory input and explicit `--pdf-work`, each PDF uses `<WORK>/<source-sha256>`. Existing caches are preserved: choose a new output cache for reparsing. Changed sources, plans, config or raw bytes invalidate the relevant reuse/review. Normalization refuses to replace a different existing source book.

## Translate, polish and verify

`source_structure_reviewed` and `translation_complete` are separate states. Source review creates no completed translations. Read project `style.md` when provided and use the existing locked glossary. If the project supplies `schemas/glossary.locked.schema.json`, validate generated locked JSON before loading or translating:

```bash
export AINIEE_GLOSSARY_SCHEMA=/path/to/project/schemas/glossary.locked.schema.json
python -m ainiee_translate.glossary lint --locked work/glossary.locked.json
```

The project's schema is opt-in and is not imposed on other users. Convert a supplied Markdown terminology table according to that project's schema and review its content before this command. A schema failure stops loading. Translate titles, prose, captions, table cells and note bodies; preserve every structural token exactly once and in order. Both batch and polish writes enforce this even with `--force` or `--allow-tag-mismatch`. Split files include chapter/unit/context metadata; context is read-only, and the controller remains the sole cache writer. New PDF scope is established by the publication-input review; do not apply EPUB-specific scope heuristics to it.

```bash
python -m ainiee_translate.batch split work/cache.json --out-dir work/batches
# Use batch write, polish, verify and audit as usual.
python -m ainiee_translate.export --cache work/cache.json --input /path/to/book.pdf \
  --output out --format md --format epub
python -m ainiee_translate.book_check out/book/book.epub \
  --epubcheck-jar /path/to/epubcheck.jar --report out/book/check.json
```

Use the export path printed/created for the source name. `--format source` means Markdown for MinerU and logs that choice. Normal export rejects unfinished units; `--allow-partial` creates explicitly named diagnostic drafts and a missing-unit list, without substituting source prose. Formal outputs use relative resources and contain publication content only. Official EPUBCheck availability/results are separate from local structural checks. Open the actual EPUB ZIP in a reader and check its exact tested width/font settings, contents position, navigation, chapter starts, formulas, captions and every note return. Neither synthetic tests nor EPUBCheck establish source fidelity or universal reader support.

## Legacy PDF and deferred templates

`parse --pdf-backend babeldoc` explicitly selects the original AiNiee path and requires `AINIEE_REPO`. Export follows cache provenance: a legacy PDF cache stays on its original writer. Converting that flat cache to Markdown/EPUB requires a new reviewed structured project; automatic translation migration is not attempted. Original Office fallback and native EPUB/TXT behavior remain available.

LaTeX, Typst, template PDF output and rosepine-latex integration are deferred; these commands do not claim them.
