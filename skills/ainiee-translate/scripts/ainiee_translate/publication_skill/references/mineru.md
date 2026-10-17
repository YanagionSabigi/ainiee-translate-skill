# MinerU setup, return formats and continuation

## Local default

`--backend mineru-local` runs the installed `mineru-kit parse` CLI in a dedicated process tree. Configure the installation with the local-only `AINIEE_MINERU_ROOT` environment variable or `--mineru-local-root`; no machine-specific installation path is embedded. Its environment script, config and CLI are discovered there. Override discovery using `--mineru-local-cli`, `--mineru-local-config` and `--mineru-local-env`. The caller needs PyMuPDF; model dependencies stay in the installation's own environment. Keep real paths, credentials and runtime configuration outside tracked files.

Before extraction, check the effective configuration including environment overrides: local model source and existing model paths, empty remote VLM URL, disabled optional LLM processing. Each run uses a task-local configuration and environment; global deployment files stay unchanged. Unsafe or unavailable local settings produce a saved failure. PDFs, images, OCR output and inference stay local. Keep detailed artifacts and logs on disk; report only status, page numbers, counts and check conclusions to an AI conversation.

Before assigning extraction batches, apply [publication.md](publication.md). A source-bound `publication-input.json` excludes packaging/copyright information, printed contents and term-index pages or regions. The local adapter uses only permitted owner/reference/Advanced regions in explicitly mapped sanitized inputs. Without this plan, `--pages` alone does not exclude automatically attached references. Page roles and boundaries require local evidence; the runner does not classify them automatically.

```powershell
python "<skill>/scripts/pdf_to_epub.py" probe
python "<skill>/scripts/pdf_to_epub.py" extract "D:/书籍/原书.pdf" --out "D:/转换/原书" --language ch
# Same source and settings reuse completed results and resume unfinished batches.
python "<skill>/scripts/pdf_to_epub.py" extract "D:/书籍/原书.pdf" --out "D:/转换/原书" --language ch
```

Standard is the default tier. `--mineru-batch-pages` defaults to 50 owned pages; `--mineru-reference-pages` defaults to two reference pages before and after each batch, clipped at document edges. Reference pages support boundary checks after extraction. They do not add cross-page inference context: the model's execution/memory window is a separate mechanism. Keep each full batch result; adopt only the requested owned pages, once and in source order. Region crops use explicit derivative page maps and source boxes. Original-PDF `--pages` results use their actual original `page_idx`; never apply the selection offset a second time.

MinerU 4.0.10's local CLI has no language-selection flag. `--language` is retained as a recorded hint for the local MinerU request; explicit Tesseract routes and the cloud API retain their existing language handling.

Local quality checks record structural suspicions and trigger one Advanced retry for the affected pages with adjacent references. Keep Standard and Advanced originals and the issue record even when the retry completes. Structural checks cannot establish character accuracy, reading order or correct formulas. Remaining issues require source review; an Advanced failure does not cause a downgrade or a cloud submission.

Checkpoints bind source bytes, selected pages, tier, effective local configuration and runtime identity. Verified completed bundles are reused. Incomplete, failed or interrupted batches retain attempt logs and are resumed without discarding successful batches. Success, failure, timeout and cancellation close the task's owned process tree; independently started MinerU instances are outside it. Detailed failure output belongs in the local log, not terminal summaries.

Local request checkpoints and complete attempt bundles live in `WORK/mineru/local/jobs/requests/<fingerprint>/`; preparation history is in `jobs/preflight.json`. Full imported batch candidates are retained under `WORK/mineru/local/batches/`, and versioned issue snapshots under `WORK/mineru/local/quality/`. `WORK/raw.json` and `WORK/state.json` describe the latest adopted selection. The model fingerprint uses paths, sizes and modification times plus small configuration/tokenizer file hashes; it does not reread all large model weights for each batch.

The reusable entry point is `scripts/mineru_local.py` and its `ensure_bundle(pdf_path, job_dir, options, cancel_event=None)` function. It has no dependency on EPUB packaging. The PDF flow in `scripts/mineru_local_flow.py` adds batching, quality escalation, structured import and deduplication; other skills can reuse the runner without adopting EPUB conversion. Consult its docstring for the options and return contract. This integration's first acceptance scope is finite local extraction and structured import; full-book EPUB production and content proofreading remain separate work.

## Explicit cloud setup and authorization

`--backend mineru` preserves the existing Python standard-library HTTPS transport plus PyMuPDF. It detects `MINERU_TOKEN` or the existing `token:` scalar in `~/.mineru/config.yaml`; probe reveals presence/source, never the credential. Use `--allow-upload` only within the user's authorized document scope. A credential alone is not authorization. Existing result import stays local.

The official `mineru-open-api` CLI is an optional diagnostic. Discovery checks explicit path, PATH and `~/.mineru/bin/mineru-open-api.exe`. Version 0.5.9 is installed in that location in the Windows validation environment, with an existing credential detected. The portable skill bundles neither the binary nor credentials/machine paths. Another machine may install the official platform package; the API transport does not require it. Local model installation is not required for cloud extraction.

```powershell
python "<skill>/scripts/pdf_to_epub.py" probe
python "<skill>/scripts/pdf_to_epub.py" extract "D:/书籍/原书.pdf" --backend mineru --pages 1-20 --out "D:/转换/原书" --language ch --allow-upload
# Same settings resume the saved task without another submission.
python "<skill>/scripts/pdf_to_epub.py" extract "D:/书籍/原书.pdf" --backend mineru --pages 1-20 --out "D:/转换/原书" --language ch --mineru-wait 30
```

`ch` is the Chinese default; choose the source language otherwise. `--mineru-model vlm|pipeline` selects a precision model. OCR defaults on unless `--mineru-no-ocr`. Flash Markdown alone is insufficient.

## Official v4 transport

POST `/api/v4/file-urls/batch` requests signed URLs with filename, stable data_id, is_ocr, model_version, language, enable_formula and enable_table. Save the batch ID before PUT of exact fingerprinted bytes. The signed PUT sends Content-Length and **neither Bearer nor Content-Type**; urllib's implicit form header is removed, matching the official client. API Bearer never follows redirects or goes to storage. GET `/api/v4/extract-results/batch/{batch_id}` observes pending/running/waiting-file/done/failed; download full_zip_url on done without Bearer.

Derivatives include only selected pages/regions. At most 100 pages and 190,000,000 bytes are submitted per batch (within documented precision limits of 200 pages/200 MB). Oversized batches split to pages; a single oversized page is rejected. `--mineru-api-base` intentionally selects another API endpoint; never replace it with an unverified service.

`WORK/mineru/jobs/<fingerprint>/checkpoint.json` binds PDF bytes, settings, API base and adapter version. Bytes are hash-checked again before upload. Completed ZIPs are reused; pending jobs only poll. Failed tasks stay failed for diagnosis rather than spending another submission. An uncertain POST is `submission_unknown`; obtain its existing batch ID instead of blindly repeating. `--mineru-batch-id ID` adopts exactly one matching selection; verify the original model/source externally. Signed upload URLs are temporary private checkpoint data, removed after upload; do not publish checkpoints. Tokens are never saved. Timeouts keep resumable state.

## Structured import

```powershell
python "<skill>/scripts/pdf_to_epub.py" import-mineru "D:/书籍/原书.pdf" --result "D:/MinerU/result.zip" --out "D:/转换/原书"
# Known derivative: source pages 3,1 in that order (mapping is not sorted).
python "<skill>/scripts/pdf_to_epub.py" import-mineru "D:/书籍/原书.pdf" --result "D:/MinerU/result.zip" --out "D:/转换/选页" --page-map 3,1
```

ZIP/directory originals are preserved in `WORK/mineru/imports/<bundle hash>/originals` with a SHA manifest. Replay checks immutability. Archive traversal, Windows aliases, symlinks and expanded-size limits are checked. Returned remote image URLs stay evidence and are not fetched. EPUB assets use relative paths.

Recognized keys determine schema:

- **docvortex.middle, schema_version 2.0:** zero-based pages[].page_idx, normalized 0..1 geometry; extensions.docvortex_layout version 1 width_pt/height_pt maps to source page/clip. Preserve nested blocks, typed inline formulas, text styles, lists, tables, captions and auxiliary blocks.
- **Legacy pdf_info layout:** page_size/point geometry, para_blocks/lines/spans, child/discarded_blocks. Headers and footnotes in discarded_blocks remain reviewable.
- **Content List / V2 page groups:** zero-based page_idx or explicit groups, normalized 0..1000 boxes. Preserve unknown types and flattened Markdown/TeX; inline math in flattened Markdown is not automatically guessed from dollar signs. Prefer richer layout JSON.

Unknown schemas/versions, model JSON, mismatched geometry/mappings fail explicitly. A CLI/API task envelope is not a document: download its ZIP first. Blank pages are accepted from actual page records or explicit Content List/source mapping; never infer an offset. Region import needs programmatic source_boxes; automatic routes supply them.

Raw keeps semantic_blocks, exact mineru_record pointers/records, span confidence/styles, resource hashes and source points. Region-specific namespaces prevent asset/semantic ID collisions; parent/child, caption/footnote and line mappings stay consistent. Draft retains unknown/auxiliary text, supports a conservative semantic HTML table subset and preserves table captions. Complex tables retain an image candidate.

## Source review

Verify paragraphs/order, print TOC, chapter membership, note binding and TeX; MinerU labels are candidates. Auxiliary classification alone never justifies omission. Notes are not automatically attached or relocated. Current inline formulas often have only paragraph geometry: locate a precise formula box or use a returned image. Set crop_geometry_verified only after checking the source. Restore styles only with evidence and apply SKILL.md's punctuation/spacing policy: default full-width prose, optional half-width prose, always half-width punctuation inside formulas.

Normalization requires line and semantic-block coverage. Put handled IDs in `mineru_blocks`; use evidence-bearing `semantic_resolutions` for consciously handled originals. This does not prove complete character coverage or correct order; review slices visually. Returned asset SHA verification checks integrity, not mathematical truth.

Contract fixtures and live service results are tested/reported separately. See the dated workspace validation report for observed completion, actual return schema and reader scope; a fabricated fixture is never described as a real service result.

Sources: [API](https://mineru.net/apiManage/docs), [output schemas](https://opendatalab.github.io/MinerU/reference/output_files/), [4.0 migration](https://opendatalab.github.io/MinerU/reference/migration_4/), [cloud CLI](https://github.com/opendatalab/MinerU-Ecosystem/tree/main/cli/mineru-open-api), [Go signed upload](https://github.com/opendatalab/MinerU-Ecosystem/blob/main/sdk/go/api.go).
