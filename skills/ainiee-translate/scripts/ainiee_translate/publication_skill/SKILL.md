---
name: pdf-to-epub
description: Convert digital, scanned, mixed, or unreliable-OCR PDFs into faithful, reflowable EPUB 3 in the original language. Use local MinerU structured extraction by default, with verified chapters, endnotes, formulas and styles, for PDF-to-EPUB conversion or repair.
---

# PDF to EPUB

Preserve the supplied content, language and reading order, applying the publication policy below. Never overwrite the PDF. Scripts handle extraction, provenance, assets, packaging and checks; you judge paragraph boundaries, structure, note associations and source fidelity. Command success is not proof of fidelity.

## 目录、包装信息、术语索引与注释

在正文提取前识别并记录页面或区域角色，执行以下默认要求。先读 [publication.md](references/publication.md) 设置源文件绑定的排除计划和书签映射；已有计划会被 `inspect`/`extract` 自动读取，角色识别和源核验仍需完成。

1. **书签替代原书目录。** 用原 PDF 的书签生成可见目录，放在原书目录的位置；原本位于目录前的序言、导言、译者序等仍在目录前。章为一级，节在相应章下为次一级；可见目录按层级排布，不使用有序列表，不显示自动列表序号。可见目录与 EPUB 导航同源，全部项目保留跳转。原目录文字省略，不依赖 OCR 重制；书签缺失或目标不可靠时记录问题，不编造。
2. **封面与封底置于最前。** 实际存在的封面、封底以完整图像依次放在整个文件最开头，其余保留内容按原书顺序排列；缺失图像不补造。封面、封底、腰封上的文字不扫描、不转录，也不生成 OCR 图注；图像中原有印刷字保留。
3. **排除包装与版权信息。** 版权页及版权、出版、CIP、印刷、版次、ISBN、包装/版权信息中的作者译者信息等不进入成品。混合页仅排除已确认区域，保留正文；正文与参考文献中的作者、译者及引文归属保留。排除内容也不得进入文字提取、批次参考页或 Advanced 重提。
4. **删除书末术语索引，保留参考文献。** 按已确认的内容边界删除术语索引；与参考文献相邻或同页时分别处理，不能按关键词盲删。
5. **逐章编号的章末注释。** 正文用小号数字上标跳转到本章末注释，按正文首次出现顺序从 1 递增，每章重新从 1 开始。重复引用同一注释使用同一编号，各引用都有回跳链接；保留原标签与源对应关系，疑难配对记录问题。

原 PDF、原始提取和本地溯源记录保持不变。`publication-input.json` 控制提取排除，`review.json` 的 `structure_rules.publication` 控制目录、开头图像和注释；脚本验证并执行已确认的计划，不自动判断页角色、书签语义或注释配对。

## Inspect and extract

Locate this skill directory and run `python scripts/pdf_to_epub.py probe`. Select a Python with PyMuPDF; the bundled Python may differ. **Local MinerU Standard structured extraction is the default**, including digital PDFs. Keep PDFs, page images, OCR content and inference on the local machine; show only status, page numbers, counts and check conclusions in AI conversations. Read [mineru.md](references/mineru.md) for local setup, checkpoints, quality escalation and return schemas; use [backends.md](references/backends.md) when changing backends. PyMuPDF supplies inspection, selection and resource recovery. A local failure retains its logs and state without cloud submission or automatic backend downgrade.

Run `inspect INPUT --out WORK --pages 1-12` (omit pages for all). Review inspection JSON, fonts, bookmarks, image coverage, hidden text and representative images. Determine language from the source. Selectable text may be wrong. Compare representative native and OCR regions, including columns, notes and formulas, before trusting a layer.

Run `extract INPUT --out WORK --language ch` (use the source language for other books). The local CLI retains structured ZIP/JSON/resources, logs and source page/region mappings. Each batch owns 50 pages and includes up to two available reference pages on each side; merge only owned pages, once and in source order. Local quality rules trigger one Advanced retry of suspect pages with adjacent references. Preserve both tiers and unresolved issues; Advanced completion does not prove fidelity. Repeating the same command reuses verified completed results and resumes unfinished work. Import an existing ZIP/directory using `import-mineru INPUT --result RESULT --out WORK`, supplying `--page-map` only for an explicitly known derivative.

Use `--pages 1-12` and optionally `--routes routes.json` for a selection or ordered nonoverlapping regions. A route's `mineru`/`auto` uses the selected MinerU backend; `native` or `ocr` selects the existing PyMuPDF/Tesseract routes. `--backend local` retains that engine and its provisional native/Tesseract heuristic. `--backend mineru` explicitly selects the existing cloud API and requires upload authorization before using `--allow-upload`. Accept one source per area and document the reason for a fallback. See the backend reference for deskew and unrouted regions.

## Recover and review

Run `draft --work WORK` to create an **unreviewed** plan. MinerU headings, lists, captions, table cells, formula placeholders and auxiliary blocks become review candidates; they do not establish correct chapters, notes or mathematical content. Read [recovery.md](references/recovery.md) and [intermediate.md](references/intermediate.md) when editing `review.json`. Inspect source images to recover paragraphs, columns, headings, notes, figures and styles. Account for every line and MinerU semantic block as content or an evidenced resolution/omission; explicitly resolve failed and unrouted regions. Record uncertainty without inventing missing text.

Map PDF bookmarks to source-verified chapter/section targets and record the original contents position using the publication reference. Account for bookmarks outside the selection or excluded content with explicit evidence. Use independent chapter XHTML and deeper headings in content. Record part/volume mappings and printed page offsets. For an incomplete chapter, use a document chapter with notes at its end.

Move verified footnotes, endnotes and marginal notes to their chapter ends. Assign unique IDs and retain original labels in the mapping; publication mode generates chapter-reset numeric superscripts and return targets. Report ambiguous associations and missing counterparts. Use original-language `labels` for editorial navigation and note headings.

Extract native images when suitable; crop vectors/composite figures or formulas from precise regions. Verified TeX can use the optional MathJax renderer, with source cropping on failure. Compare symbols even after compilation. Calibrate inline height/baseline and display `width_em` against source text; a 300-dpi PNG's natural pixel size is not its reading size. Preserve meaningful native span styles and visually verified scan styles; do not infer italics from content.

After source comparison, set `reviewed: true`, record `review_evidence`, and bind the plan to `raw_sha256`. Run `normalize --work WORK` to create `book.json`. The schema reference explains source slices, explicit cross-page joins, formulas, semantic tables and corrections. Recheck the plan whenever raw extraction changes.

## 标点符号规范

可读正文、章/节标题、引文、注释、图注和表格文字均按以下规范审校，保留原文语义：

1. **模式。** 只有全角标点模式和半角标点模式，**默认使用全角标点模式**。在 `review.json` 的 `structure_rules.punctuation_mode` 中记录 `full` 或 `half`；未指定时取 `full`，用户明确选择半角时取 `half`。

2. **常用标点。** 按所选模式使用以下形式：

   | 标点 | 半角模式 | 全角模式 |
   | --- | --- | --- |
   | 逗号 | `,` | `，` |
   | 分号 | `;` | `；` |
   | 句号 | `.` | `。` |
   | 感叹号 | `!` | `！` |
   | 问号 | `?` | `？` |
   | 圆括号 | `(…)` | `（…）` |
   | 冒号 | `:` | `：` |

3. **固定形式。** 两种模式下，顿号均使用 `、`，破折号均使用 `——`（两个 U+2014）。人名之间使用短横线 `–`（U+2013），而非连字符 `-`（U+002D）。

4. **引号。** 非 TeX 环境中，全角双引号为 `“…”`，半角双引号为 `"…"`；全角单引号为 `‘…’`，半角单引号为 `'…'`。TeX 环境中，全角引号形式相同；半角单引号使用一个反引号开头、一个撇号结尾，即 `` `…' ``；半角双引号使用两个反引号开头、两个撇号结尾，即 ``` ``…'' ```。按实际输出环境选择形式，并核验开闭、配对和嵌套。

5. **空格。** 空格也属于标点符号。应主动在中文与英文单词之间加一个空格。使用半角标点时，结尾标点（如逗号 `,`、句号 `.`、冒号 `:`）与后续文字之间加一个空格。中文或英文与公式之间也应加一个空格。边界空格使用实际的 U+0020 字符，不只依靠 CSS 留白。

6. **公式环境。** 公式环境内的标点固定使用半角，无论正文采用全角还是半角标点模式。

同时读取 [recovery.md](references/recovery.md) 的语境、标点连用及公式边界处理规则。OCR 标点语义不明确时回看源区域并记录问题，不猜写或补造；保留原始提取结果，在 `review.json` 中记录规范化修订及依据。小数、网址、代码和 TeX 语法须按其实际作用处理。

## 翻译项目

需要 PDF 翻译、源文修订、局部恢复或独立译书发布时，先读 [translation.md](references/translation.md)。最低结构使用 prepare，得到 epub-book/2 后交给 AiNiee 缓存。初翻前暂缓全面 OCR 校勘；后续独立上下文对照 PDF 校对，所有正式译书由绑定清单和当前证据放行。原文 epub-book/1 命令保持可用。

## Build and verify

Run `build --work WORK --output OUTPUT.epub`, then `check OUTPUT.epub --epubcheck /path/to/epubcheck.jar` when available. Build rejects invalid relationships and unreviewed plans, and writes JSON/Markdown conversion reports. `--allow-unreviewed` is only for a labelled diagnostic draft.

Read [validation.md](references/validation.md). Compare source content and check chapter starts, resized text, directory placement, navigation, all note returns, formula baselines, captions and styles in an actual reader. Full nested navigation stays in `nav.xhtml`; the visible contents uses hierarchical links at its reviewed source position. Sidebar expansion is reader-controlled.

For long books, review incrementally using the same cache/plan. Preserve inspection, raw/TSV, corrections, assets, book JSON and state. Deliver EPUB plus a report listing methods, fallbacks, unresolved issues and exact tested reader/backend scope.

Example (PowerShell; quote Chinese paths and spaces):

```powershell
python "<skill>/scripts/pdf_to_epub.py" inspect "D:/书籍/原书.pdf" --out "D:/转换结果/原书"
python "<skill>/scripts/pdf_to_epub.py" extract "D:/书籍/原书.pdf" --out "D:/转换结果/原书" --language ch
python "<skill>/scripts/pdf_to_epub.py" draft --work "D:/转换结果/原书"
# Codex reviews the plan against source images.
python "<skill>/scripts/pdf_to_epub.py" normalize --work "D:/转换结果/原书"
python "<skill>/scripts/pdf_to_epub.py" build --work "D:/转换结果/原书" --output "D:/转换结果/原书.epub"
```
