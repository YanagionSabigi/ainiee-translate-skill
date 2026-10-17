# Source records and reviewed book schema

## Files and continuation

`inspection.json` describes source SHA-256, selected physical pages, fonts, hidden text, image placement/xrefs, PDF metadata and bookmarks. `pages/` holds representative renders. `raw.json` (`pdf-raw/1`) stores page dimensions and ordered regions. Region `fingerprint` binds PDF hash, page, settings, executable identity and pipeline version; `cache/` stores complete or failed region records. Raw lines retain stable IDs, block grouping, spans (text/font/size/styles/bbox/origin), OCR confidence and source page/bbox/method. `ocr/` stores processed raster, exact TSV and stderr. Raw text is never overwritten during review.

`state.json` holds local source path, hashes, selection, stage and cache reuse; the absolute source path remains outside the EPUB. Changing route settings invalidates only affected regions. Failed regions retry. Resume uses identical command arguments, without a special flag. Changing selection can remove pages from assembled raw while retaining caches; this invalidates the old review hash and must trigger review.

MinerU transport checkpoints and complete original archives are under `mineru/jobs/`; immutable returned files and manifests are under `mineru/imports/`. See [mineru.md](mineru.md) for exact schemas, coordinate units and continuation. `raw.semantic_blocks` retains visual and auxiliary content, parent/child relations, `sources`, `caption_sources`, `footnote_sources`, HTML/TeX candidates and original JSON pointers. Automatic extraction keeps per-batch metadata in `mineru_result`; local import uses `mineru`. These records survive normalization. Checkpoints may temporarily contain private signed upload URLs and must not be distributed.

`draft` writes a plan only if it does not already exist. MinerU semantic blocks produce unreviewed heading/list/table/visual candidates; unknown and discarded text remain visible. Local output groups within native blocks/OCR paragraphs. Neither path infers verified chapters/notes. Preserve work files; review incrementally and normalize after complete coverage.

## Review plan (`pdf-review/1`)

Required keys: `raw_sha256`, `source_sha256`, `metadata` (`title`, BCP47 `language`, optional `creator`), `labels` (`contents`, `notes`, `return`), `reviewed`, `review_evidence`, `chapters`, `notes`, `omissions`, `region_resolutions`, `issues`, `structure_rules`.

Use `structure_rules` to record fragment status, higher hierarchy mapping, print-to-physical offsets, and any numbering policy. An offset is evidence for source location, never an EPUB page number. Preserve observations/uncertainties as structured issue objects upstream or strings in this plan. A reviewed flag means you actually compared content, not merely that JSON validated.

Record `structure_rules.punctuation_mode` as `full` (default) or `half` after applying SKILL.md's punctuation/spacing policy. This field survives normalization and appears in the conversion report; it records the review decision, not an automatic character-replacement engine. Formula punctuation remains half-width in either mode. Textual quote syntax depends on the actual output environment (XHTML prose versus TeX source).

Chapter: `id`, `title`, `heading_sources` (raw line IDs), `blocks`. A fragment/editorial title may instead have `heading_evidence`. IDs use `[A-Za-z][A-Za-z0-9_.-]*` and are globally unique. Title text needs source comparison; heading evidence does not verify wording automatically. Each chapter becomes `ID.xhtml`. In publication mode, [publication.md](publication.md) maps PDF bookmarks to chapter/heading IDs and places the visible contents at its original position; chapter and section are the two navigation levels. Levels 3–6 stay in content. Notes heading is not added to the TOC. Without publication configuration, legacy heading-derived navigation remains available for existing plans.

Every source line must be used as content/heading or explicitly omitted with reason and image evidence. Every MinerU semantic ID, including visual blocks with no text, must appear in a block/omission `mineru_blocks` list or an evidence-bearing `semantic_resolutions` entry `{"block":"ID","evidence":"source handling"}`. Preserve these IDs when moving notes/chapter titles; a chapter heading semantic ID can have a resolution referring to its heading_sources. A line can supply multiple **disjoint** source slices; line accounting cannot prove complete characters/order. Never reuse a whole line twice. Failed regions and unrouted complements need evidence-bearing resolutions.

### Blocks and source text

```json
{"id":"p-cross","kind":"paragraph",
 "sources":["p0002-r01-l0005","p0002-r01-l0006","p0003-r01-l0003"],
 "joins":[" "," "]}
```

Default source text retains native span emphasis. `joins` has one explicit separator per adjacent line; use `"\n"` for verse. Do not apply universal terminal-punctuation merging. For a verified split word, use one exact `edits` match with `old`, `new`, `evidence`; styled edits also need `style_resolution`. True printed hyphens remain. Edits do not silently guess words.

An `inline` array replaces automatic source concatenation and supports source slicing (zero-based Unicode character indexes in the raw line), corrections, notes, formula images and ordinary internal references:

```json
{"id":"p-ref","kind":"paragraph","sources":["p0002-r01-l0007"],
 "inline":[
   {"line":"p0002-r01-l0007","start":0,"end":26},
   {"note":"note-c1-p1-1","id":"ref-c1-a","label":"1"},
   {"line":"p0002-r01-l0007","start":27}
 ]}
```

Every inline source must appear in `sources`. Literal `text` requires `evidence`; retain the original record, don't use literals to bypass extraction. Text item `styles` supports bold, italic, underline, emphasis-dot, sup, sub. Whole-block styles require `style_evidence`; prefer source slices or styled correction text for partial emphasis. Do not style an entire paragraph when only a word was emphasized. Internal reference text uses `{"link":"equation-1","text":"(1)","evidence":"source reference"}`.

Kinds: `paragraph`, `quote` (no automatic italics), `verse`, `heading` (`level` 2–6), `figure`, `formula`, `table-image`, `table`, `list`, `ordered-list`. Lists use `items` arrays of inline items. Tables use `rows` with cells as strings, inline arrays, or `{"inline":[...],"header":true,"rowspan":2,"colspan":1}`. Spans must be positive integers. Nested line selectors, styles, note links and assets are recursively resolved; selectors must be listed in block sources and literals need evidence. Keep `table_evidence`, optional `header_rows` and caption `inline`. Complex/unsafe HTML stays a table-image candidate. Images/formulas may use `source_region` (`page`, `bbox`, evidence) when no text lines exist.

### Assets

Block `asset` or inline `asset` is an object:

```json
{"id":"formula-1","page":3,"bbox":[174,296,265,335],"dpi":300,
 "alt":"E = mc²","tex":"E = mc^{2}","tex_verified":true}
```

`page`/`bbox` supply the crop/fallback. Optional `xref` extracts native images (soft mask retained); `path` imports PNG/JPEG/SVG relative to WORK, with optional exact `sha256` verification. Missing/changed hashed resources fail. Different definitions cannot share an ID. MinerU inline formulas become one U+FFFC placeholder plus an exact source interval/asset; its `candidate_tex` is not rendered until copied to `tex` after verification. `crop_geometry_verified: false` prevents an imprecise paragraph crop without an actual returned image/xref. Rendering fallback is returned image, then precise source crop. Precise crops exclude captions/numbers. Figure caption `inline` renders below the image. Display formulas allow equation_label/internal links; inline assets support height/baseline calibration. Keep source locations, not whole-page prose images.

For source crops with unusual whitespace or depth, set optional inline `height_em` and `baseline_em` after reader verification. An initial source-based calibration is crop height / surrounding printed font size, with vertical alignment = -(crop bottom - surrounding baseline) / printed font size. These are relative CSS dimensions, not fixed pixels. Tighten the crop without cutting off glyphs; a loose crop scaled to a generic 1.15em can make the actual formula too small.

For a display formula crop, set optional asset `width_em` after source/reader comparison, e.g. a 91-point formula beside 12-point printed prose starts near 7.58em. A 300-dpi PNG's natural pixel dimensions are not its intended reading size. Retain `size_evidence`; use a positive finite numeric value (up to 100em) and let max-width constrain narrow screens. Do not infer a universal source font size or force every equation to the same width.

### Notes

```json
{"id":"note-c1-p1-1","chapter":"chapter-1","label":"1","original_label":"1 (print page 1)",
 "association_evidence":"matching mark at this page's footnote; continuation verified on physical page 3",
 "blocks":[{"id":"note-body-1","kind":"paragraph","sources":["..."],"inline":["..."]}]}
```

Each reference needs its own unique `id`. Multiple references to a note create multiple return links. Page-reset and chapter-reset numbering use separate note IDs. Original labels remain in book JSON and the conversion report. Note blocks allow the same text/figure/formula structures as body content. Missing body is a build error; keep the unresolved source mark as plain text with a reported issue until body is available. A note without a verified reference remains readable and is reported. Do not create a reference to an unnumbered marginal note until its placement/context is verified; a new editorial marker must be documented in the mapping.

Publication mode assigns numeric labels by first body reference within each chapter, resets each chapter to 1, orders chapter-end note bodies accordingly, and renders all note references as small superscripts. `original_label` preserves the print label; unique reference IDs retain every backlink. Missing or cross-chapter associations require resolution rather than guessed renumbering. Existing plans without publication configuration retain their original marker labels and explicit `placement: "baseline"` compatibility.

## Normalized result (`epub-book/1`)

`normalize` writes `book.json` with resolved inline spans, per-block provenance, notes, extraction summary and plan evidence. Build reads this data without further language inference. Preserve `review.json` for editing; edit it rather than bypassing source checks in `book.json`. Re-normalize after revisions. EPUB contains only publication resources and original-language reading text, never cache paths, tokens or source-machine absolute paths.
