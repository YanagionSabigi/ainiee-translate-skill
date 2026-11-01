# Review presets implementation plan

> **For agentic workers:** Use superpowers:executing-plans; user approved implementation on 2026-11-01. Execute inline, then fresh whole-branch review.

**Goal:** Integrate Workbench 0.3.0 and provide readable glossary families alongside existing WeRead review.
**Architecture:** Three-way upstream synchronization; optional frozen term metadata; shared review storage and independent targets. A small frontend helper owns term previews and family batch eligibility.
**Tech Stack:** Python, JSON Schema, plain JS/CSS, Node test runner.
**Spec:** docs/superpowers/specs/2026-11-01-review-presets-design.md

## Global constraints

- Local branch only; no push, PR, publication or installed-skill changes.
- Preserve frozen old packages, unknown glossary fields, atomic writeback and WeRead source quote offsets.
- Term preview: source above current provisional translation; never default to unchosen proposal.
- Batch current derived family across pagination; keep before, skip required/touched/submitted items.
- No fabricated context/page; absent evidence requires individual review.

## Review focus

- Missing, duplicate or cyclic family metadata must not silently group wrong targets.
- A proposal must never replace provisional translation through family batch.
- Search/status filters must not expand batch outside visibly scoped family.
- Blank translations and incomplete drafts must not be overwritten or displayed as approved.
- Exported packages and built skills must contain all added modules and preserve historical bindings.

### Task 1: Synchronize runtime and freeze term evidence

**Files:** workbench_runtime/{web,review_workbench,schemas}, workbench_glossary.py, workbench.py, new glossary_review_data.py; tests in 测试/单元/test_workbench_glossary.py and test_workbench_presets.py.
**Interfaces:** prepare_glossary(locked, output, proposals=None, review_data=None); metadata JSON {terms:[{src,category,context,page,base?,requires_human?}]}; frozen item term_info {source,category,context,page,base?} and optional package review_profile enum glossary/reading.

- [x] Write regression tests asserting dst-only blocks, four metadata fields, independent family IDs, required missing evidence, preserved fields, rejected duplicate/unknown/cyclic metadata and 0.3.0 resources.
- [x] Run tests RED with pytest and workspace basetemp.
- [x] Merge upstream changes from 208e5a9 to v0.3.0 preserving local patches; validate optional extension fields and semantic references. Add metadata reader and CLI argument; keep existing identity/CAS bindings.
- [x] Run glossary and reading/portable regression GREEN; commit.

### Task 2: Implement family navigation and minimal term panels

**Files:** web/scripts/{app.js,glossary.js}, web/styles/app.css; 测试/前端/glossary.test.mjs.
**Interfaces:** termPreview(item,draft), familyItems(items,base), familyBatch(items,base,drafts,submittedIds) pure helpers. app.js uses same preview for sidebar and queue, familyBatch yields only eligible family items.

- [x] Write Node tests: source/current preview, explicit accept/edit preview, missing translation, >24 family members, required/touched/comment/submitted exclusions, other family exclusion. Run RED.
- [x] Implement helpers, nested directory, family-only queue, keep batch across pages, open term-info, translation-only panels, preserve WeRead evidence projection.
- [x] Run Node and adapter tests GREEN, exercise component interactions in memory and export synthetic package; commit.
- [ ] Desktop/narrow visual inspection unavailable: browser tooling stopped on Windows URL policy; see validation report. No alternate browser automation attempted.

### Task 3: Document, package and verify

**Files:** references/review_workbench.md, runtime protocol/UPSTREAM.md, docs/review-presets-validation.md; generated skills bundle via build.py.
**Interfaces:** Existing build.py and portable export consume source runtime; no installed files changed.

- [x] Document metadata JSON, AI semantic grouping/context provenance, batch behavior and re-export requirement; update guidance copied into bundle.
- [x] Exercise formal submit/export/import/compare/apply with independent family edits and preserved fields, plus legacy packet regression.
- [x] Run complete Python suite and all Node tests; build and inspect bundled files; record evidence and visual limitations truthfully.
- [x] Fresh whole-branch review against spec; one keyboard finding fixed RED→GREEN and independently verified.
- [x] Final full regression after keyboard fix: 295 Python and 17 frontend pass; bundles rebuilt and verified, local commit retained.
