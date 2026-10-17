# Backends, routing and dependency scope

## Default: local MinerU Standard

`--backend mineru-local` is the default. It runs the local CLI with Standard extraction, preserves the complete structured archive and resources, and retries structurally suspect pages once with Advanced. See [mineru.md](mineru.md) for local constraints, continuation, batch ownership and return schemas. Extraction output remains a review candidate. Detailed content stays in local artifacts; conversation feedback contains only status, page numbers, counts and conclusions.

`--backend mineru` preserves the explicit cloud v4 batch API, subject to upload authorization. Its `vlm` default and `--mineru-model pipeline` option apply to that cloud backend. `--backend local` preserves the existing PyMuPDF/Tesseract engine. PyMuPDF is also required for source inspection, page/region derivatives, geometry and resource recovery; Tesseract is optional.

## Routes and local fallback

Route pages are one-based physical PDF pages. Boxes are points from top left in the displayed source page's coordinate space. Regions cannot overlap; their list order specifies candidate reading order. Verify columns visually.

```json
{
  "1": [{"method":"mineru"}],
  "2": [{"method":"native","fallback":"ocr"}],
  "3": [
    {"bbox":[0,0,300,720],"method":"mineru"},
    {"bbox":[300,0,600,720],"method":"ocr","psm":6,"rotation":1.5}
  ]
}
```

With either MinerU backend, `auto` and absent page routes mean the selected MinerU engine. Local full-page batches own 50 pages and include up to two available reference pages on either side; cloud batches retain their existing limit of 100 selected pages. Clipped regions use separate derivative PDFs with source boxes. Local references are retained for boundary comparison but are adopted only when they belong to the requested selection. Accept one source per area, keeping source hashes, originals and mappings.

`--backend local` selects the previous local engine. Its `auto` provisionally chooses native when enough nonreplacement text exists, otherwise OCR; plausible wrong text layers can fool it. Force `ocr` after source comparison. Native extraction uses `Page.get_text('dict')`, retaining span fonts, flags, sizes, origins and coordinates. Inspection exposes images/xrefs, drawing counts, hidden text and bookmarks. Drawn underline/dots and scan emphasis need image verification.

The real Tesseract call is `tesseract REGION.png stdout -l chi_sim+eng --dpi 300 --psm 3 tsv`. `ch` maps to `chi_sim+eng` locally, `en` to `eng`, `chinese_cht` to `chi_tra+eng`. Explicit invalid `--tesseract` paths are not silently replaced. TSV retains words, boxes and confidence, not reliable structure/styles/formulas. Small `rotation` is an explicit counterclockwise raster correction inverse-mapped to source points, on a fixed canvas; verify clipping. MinerU region rotation is rejected instead of silently changing geometry. Keep a verified derivative for other deskew/orientation cases.

Native failure falls back to OCR only with `fallback: "ocr"`. Missing tools, OCR or service failures yield failed records/nonzero exit, never a silent switch to known-untrustworthy text. Unprocessed page complements require evidenced `region_resolutions`, e.g. `p0003-unrouted`. Successful local regions are cached; their version 1.0.0 cache semantics are preserved. MinerU jobs use separate fingerprints/checkpoints.

## Interfaces and validation scope

| Candidate | Real interface/output | Scope |
|---|---|---|
| MinerU cloud | v4 batch upload/status/ZIP; official `extract -f json` is a stdout task envelope | Explicit `mineru` backend; existing transport retained |
| MinerU 4 local | `mineru-kit parse --tier standard\|advanced --format zip --pages ...`; MiddleJson and resources | Default `mineru-local` backend; finite extraction/structure acceptance is reported separately from content proofreading |
| MinerU legacy | pdf_info, content_list, images | Schema-aware import tested; prefer richer layout |
| MinerU flash | Markdown; OCR off unless --ocr | Not the default: Markdown loses required structure/provenance |
| PyMuPDF | Native spans, images, rendering | Inspection, derivatives/resources, explicit local route |
| Tesseract | CLI TSV/hOCR/text/searchable PDF | Tested optional local TSV fallback |
| pdfplumber/pypdf | PDF/native layout inspection | Possible cross-checks, not implemented OCR/routes |
| BabelDOC | PDF translation/reconstruction | Excluded; parse-only PDF reconstruction is not an established original-language EPUB extraction path |

Probe installed help; current library/cloud/local interfaces differ. Do not infer schema from a product name/version or paste obsolete flags. Preserve originals; CLI JSON envelopes are not MiddleJson.

## Formula rendering

Returned images or precise source crops are defaults. `candidate_tex` stays untrusted. After symbol comparison set `tex`, `tex_verified: true` and optionally `--formula-renderer <skill>/scripts/render_math.cjs`. This requires Node and isolated `mathjax-full@3.2.2` (`NODE_PATH` points to its node_modules). It handles MathJax TeX, not full LaTeX. Render failure falls back to a hash-checked returned image, then to an accurate source crop. An inline formula without a precise bbox/image must be located before normalization; do not crop its paragraph. Verify symbols, equation numbers and baselines even after successful compilation.

Sources: [MinerU API](https://mineru.net/apiManage/docs), [output files](https://opendatalab.github.io/MinerU/reference/output_files/), [cloud CLI](https://github.com/opendatalab/MinerU-Ecosystem/tree/main/cli/mineru-open-api), [PyMuPDF](https://pymupdf.readthedocs.io/en/latest/recipes-text.html), [Tesseract](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html), [BabelDOC](https://github.com/funstory-ai/BabelDOC).
