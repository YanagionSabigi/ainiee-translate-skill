# Validation and truthful delivery

Run skill-creator `scripts/quick_validate.py` on the skill folder; this checks discovery metadata, not conversion correctness. Execute each added helper on actual fixtures. The shipped validation directory is a separate development deliverable, not a runtime dependency of the skill.

On Windows, invoke that external development validator with `python -X utf8 .../quick_validate.py SKILL_DIR`: its default-locale read can fail on UTF-8 text under GBK. The conversion scripts explicitly read/write UTF-8 and configure their own console streams.

## Structural checks

`check` validates ZIP entry safety/duplicates, exact first uncompressed mimetype, XML, IDs, OPF metadata/manifest/spine, local links/resources, two navigation levels and every note return. It rejects remote resource/link URLs for an offline publication. The checker is not the complete EPUB specification: run [EPUBCheck](https://github.com/w3c/epubcheck) with Java when available:

```text
python scripts/pdf_to_epub.py check OUTPUT.epub --epubcheck TOOLS/epubcheck.jar --output WORK/checks.json
```

Keep all JAR dependencies from the official release beside its main JAR. `not-run` or `unavailable` is never a pass. Fix EPUBCheck errors and record warnings. The build report deliberately says reader/EPUBCheck verification is separate; link actual check evidence in the delivery report.

## Fidelity and reader verification

Use independent expected text for synthetic native/scan/mixed samples; the expected answer must not be the conversion input. Source-linked review plans can use known layout annotations to select real extracted lines, but corrections require actual source comparison. Check complete paragraphs, chapter order, columns, notes, captions, style ranges, formulas and omissions. Record OCR differences and local corrections. Test an incomplete-chapter selection and state note text that is cut off in the supplied PDF.

Open the actual ZIP EPUB in an available reader, not only its extracted XHTML. Record reader/version, OS/browser, pagination mode and font sizes. Verify:

- Apply [publication.md](publication.md): actual cover and back cover appear first as full images, in that order; remaining content follows source order. Excluded package/copyright/ISBN/author-translator metadata is absent from OCR prose and duplicate captions, while printing in retained images remains visible. Terminal term-index content is absent and bibliography remains, including mixed pages. Check evidence, source hashes, clipped derivative pixels/resources, maps, references and Advanced neighbors as well as the final spine.
- Each chapter starts independently; section headings do not force a page break.
- Body text reflows at narrow width and larger font; no prose facsimile or horizontal overflow.
- PDF-bookmark titles/targets and chapter–section hierarchy match the reviewed map; every bookmark is mapped or explicitly accounted as omitted. The visible contents occurs once at the original position after any preceding prefaces, uses hierarchical links without an ordered list, and matches reader navigation. Deeper headings remain in body; sidebar expansion is reader policy.
- Each chapter's note numbers begin at 1 and follow body-first-reference order. All markers are small numeric superscripts; each opens its correctly ordered chapter-end note and returns to every separate reference. Original print labels and association evidence survive in the mapping.
- Source formulas match notation, inline baseline/size and display proportions; captions are below figures and smaller than prose.
- Bold, original italics, underline, dot emphasis/fallback, quote, sub/sup, verse and semantic table are visible as supported.
- Review actual XHTML text against the selected `full`/`half` punctuation mode (default `full`), including headings, notes, captions and table text. Check all seven common punctuation forms including colon, mode-specific paired/nested quotes, fixed U+2013 name separators/顿号/two-U+2014 dash. TeX prose quotes use TeX opening/closing forms; XHTML uses non-TeX forms. Check one actual U+0020 space at Chinese/English-word and prose/inline-formula boundaries and after half-width ending punctuation before following text, including boundaries across style/link/image nodes. Preserve decimals, mathematical primes/operators, URL/code/TeX syntax and punctuation groups. Formula punctuation stays half-width in both modes: inspect the visible image/SVG, not only alt text. Source-check ambiguous OCR marks and retain unresolved issues. ZIP/link validation alone does not verify punctuation/spacing.

epub.js is a real browser EPUB renderer suitable for a recorded test; it is not evidence for Calibre, Thorium, Apple Books, Kindle or e-ink compatibility. A browser checker can measure computed styles/reflow and take screenshots, but inspect the screenshots and source images before asserting visual QA.

## 独立 subagent 终校（交付门槛）

最终构建和执行者的阅读器检查完成后，必须派未参与本次转换的 subagent 独立审核。提供原 PDF、inspection、原始提取与素材、review.json、book.json、最终 EPUB 和构建/阅读器记录的路径。审核者自行读取源页与最终成品，不以执行者的报告替代对照。

审核报告保存为 WORK/independent-review.md，必须包含：审核者、日期、源文件 SHA256、最终 EPUB SHA256、审核范围与所用阅读器、逐项证据、问题、结论（通过／待修复／未完成）。

1. **全部素材对账。** 从源页独立清点有意义的图片、表格、公式、封面和封底；对每项记录源页/区域 → 原始资源或提取块 → book asset/block ID → EPUB 资源与 XHTML 位置 → 实际可见性。已确认排除项记录理由。既查已登记资源是否存在，也查源页是否有未登记资源，不能只比较构建报告中的数量。素材少时逐一核对全部，不以抽样替代。
2. **完整段落与图位。** 回看每张图前后源页，先确认跨页/跨栏的同一自然段已接成一个完整 paragraph/quote，再检查图片及图注位于首次明确提及的完整段落后、下一自然段前。after_block 只指向一个 block，不能证明该 block 已是完整自然段。逐项排查 inline asset，正文插图应作为 figure；仅实际行内公式采用行内资源。图注随图且只出现一次。
3. **全部注释。** 从源页逐一核对脚注、尾注、旁注及 visual-footnote-candidate 等候选，确保每项已归入所属章末或有依据的处理记录，正文不残留误作普通段落的脚注。核对每条注释的源标签、归属章、首次引用顺序、每章从 1 编号、注释正文在本章最后，以及每处跳转与“返回原文”。计划和成品一致不能单独证明与源文一致。
4. **阅读器与关系检查。** 在实际 EPUB 阅读器打开最终 ZIP EPUB，检查目录、章/节标题层级、引文字体/颜色/字号、表格、所有素材可见性，并在窄屏与放大字号下核对图文关系。记录实际测试范围；未验证的阅读器保持未验证。

执行者修复问题、重建后，将新 EPUB 与新哈希交给原独立审核者复查，报告更新到最终版本。存在素材遗漏、错误图位/拆段、注释遗漏或错章、断链等阻断问题时不能通过。subagent 工具不可用或源文件缺失时记录“未完成”，明确交付待校对草稿，不以自审冒充独立终校。

## Failure and resume tests

For the local MinerU default, distinguish synthetic contract fixtures from actual local Standard/Advanced execution. Exercise source-bound exclusion plans, safe cropped references/Advanced neighbors, model-free input sanitization, cache reuse, changed policy/source bytes, cancellation/resume, and dedicated process cleanup. Record formats/archive hashes and state; structural success is not content accuracy. The explicit legacy cloud backend has separate credential/upload/submission/polling tests when authorized; those do not validate local extraction. Test multi-region IDs, ordered page maps, blank pages, semantic coverage and resources. Do not label synthetic structures or historical real runs as new live acceptance.

Exercise unavailable OCR executable/language, native extraction failure with explicit OCR fallback, cache reuse, changed settings/hash, overlap/unrouted areas, unreviewed publication refusal, missing note/resources, duplicate IDs, corrupted links and invalid TeX. Formula failure must yield an actual source crop and report its cause; extraction failure must remain recorded and block unresolved publication. Test paths with spaces and Chinese names, input SHA preservation and absence of local absolute paths in ZIP text.

Deliver a short report with commands/tool versions, sample outputs, inspected source pages/screenshots, exact verified capabilities, corrected defects and remaining limits. Unknown backend or reader behavior stays unverified. Keep large development dependencies outside the portable skill.

Specification: [EPUB 3.3](https://www.w3.org/TR/epub-33/) and [structural semantics vocabulary](https://www.w3.org/TR/epub-ssv-11/).
