# Judgment during source recovery

## Publication roles and source boundaries

Apply [publication.md](publication.md) before text extraction and when mapping bookmarks and notes. Record page/region roles from local layout evidence, with source hash and precise mixed-page retained regions. The original contents position is a source location, not necessarily the beginning of the book. Preserve preceding prefaces and introductions; only actual cover/back-cover images move to the front.

The role record controls exclusion; a page number or matching word alone is insufficient evidence. Keep bibliography even beside a terminal term index, and preserve body attribution even when similar author/translator metadata is excluded from packaging. Package images retain their printing without OCR prose or captions. For already imported results, account for discarded raw lines/semantic blocks with evidenced omissions/resolutions before normalization. Pre-extraction exclusions retain source positions instead of invented raw IDs.

## Pilot comparison and reading order

Choose representative pages across text/native fonts, scan quality, dense notes, equations, columns, tables and chapter transitions. Record native/OCR accuracy, order, paragraph boundaries, missing resources, note and style fidelity. Image-heavy pages can have reliable native captions and bad hidden OCR at once. Select by region, not by a book-wide label. Prefer high-quality native content when source comparison supports it; force OCR only in doubtful regions. Crop and inspect problematic areas instead of re-OCRing the book.

Use columns, indentation, baseline/line spacing, bounding boxes and continuation context together. Raw PDF object order or OCR block order can cross columns. Include floating figures at their actual associated location, distinguish side notes and footnotes, and verify continuation around them. Don't sort all text only by y then x. Page headers/folios are omission candidates only with repeated position/content or direct page evidence; do not delete any line matching a generic pattern alone.

## Paragraphs and language fidelity

Printed lines are not paragraphs. A first-line indent, vertical gap, line ending, syntax and neighboring paragraphs jointly support a boundary. A sentence ending can occur mid-paragraph; an unfinished sentence can end a quote/list item. Cross-page joining needs compatible indentation/style and actual continuation, after removing verified header/footer/note regions. Preserve poetry line breaks, quote structure, list items, table cells, captions and display equations separately.

Latin split-word hyphens require word/context evidence; preserve lexical hyphens such as “well-known”. Remove source-verified artificial spaces inside CJK words, while applying the punctuation policy's required spaces at Chinese/English-word and prose/formula boundaries. Ligatures may be normalized when clearly equivalent for search/copy, with a recorded correction. Don't turn an apparent OCR error into a guess. Compare the source crop; report unreadable or uncertain glyphs without silently rewriting the original.

## 标点与空格审校

执行 [SKILL.md 的标点符号规范](../SKILL.md#标点符号规范)。仅有 `full`/`half` 两种模式，默认 `full`，在 `structure_rules.punctuation_mode` 记录选择；用户明确选择半角时采用 `half`。范围包括可读正文、标题、引文、注释、图注、表格文字。扫描字形不一定等同于数字字符；修复排印形式须保留标点的语义作用、引文边界及对应关系，不改写句子来使标点“通顺”。

先区分普通文字、数学内容和机器语法。常用语义标点按当前模式处理；公式内部的语义标点一律半角。数字 `3.14` 的点、公式减号/负号、网址 `https://`、代码字符串、英语词内撇号、真实词汇连字符不是句号、破折号或引用引号，不能按外观机械替换或插入空格。顿号 `、`、破折号 `——`、人名连接符 `–` 在两种模式中固定；不能把所有 `-` 归入同一类。

OCR 的点、逗号和短线只能作为候选。检查源图的位置、长度和形状，结合原句区分句号/小数点、逗号/顿号、分号及人名连接符/破折号；上下文辅助判断，不能替代源证据。引号先确定开闭和嵌套，再按模式及输出环境使用规范形式，不以交替替换跨段猜测或补造缺失引号。TeX 文本引号使用 SKILL.md 的 TeX 写法；数学导数的撇号、反引号的代码含义和 TeX 命令语法须保留。TeX 源中的引号记法不是 XHTML 正文应显示的字符序列；EPUB 文本按非 TeX 规则呈现。

主动在中文与英文单词、中文/英文与行内公式之间保留恰好一个 U+0020 空格；这包括跨文字样式片段、链接或公式图片元素的边界。半角结尾标点后接普通文字时加一个空格；相邻的结尾标点、闭引号或闭括号组成一个标点组，空格放在整个组与后续文字之间，例如 `他说: "好." 随后离开.`。不在词内部、数值内部或标点组中乱加空格；段末、行末无后续文字时不补尾随空格。固定顿号/破折号不因选择半角模式而另换字符。

行内公式与相邻中英文文字之间的空格是正文文本节点的一部分，不只设置图片 margin；公式紧接标点时不额外插空格，例如 `[公式], 后文` 或 `[公式]，后文`。公式内部仍按半角标点和数学结构处理，不把边界空格扩展为破坏 TeX 标记或运算结构。独立公式保留独立块及前后段落间距，不在块首尾制造空白段落或尾随空格。源公式裁图含有不符合规则的标点时，核验并使用可靠 TeX/资源修复；无法可靠处理则记录限制，不把仅修改 alt 文本视为已修复公式图像。

原始 raw/TSV 保持不变。形式归一化、边界空格和 OCR 更正记录为 review.json 中带依据的 edits/inline 修订；用户的模式/空格规范是排印修订依据，OCR 语义补正仍需源证据。输出 XHTML 的实际文字字符及公式可见资源须符合规则；XHTML 属性、JSON、CSS 和 TeX 命令的语法符号不得当作正文替换。

## Chapters and notes

Triangulate printed TOC, bookmark page/title and actual heading. A large font alone does not establish a chapter. Record printed Roman/Arabic labels and physical page evidence; test multiple anchors when offsets differ across frontmatter/insertions. Higher “part/volume” hierarchy may be chapter metadata or a separate included division if source warrants it; record the chosen mapping. Don't fabricate chapters omitted by an excerpt.

Identify body superscript/inline note marks and their source notes by page, chapter, number and context. Join continued notes across pages only with boundary/content evidence. Page resetting numbers need distinct internal IDs even within a chapter. A global endnote section must be assigned using verified chapter heading and number correspondences; ambiguous notes remain unassigned/reportable. Marginal notes without marks need source/context evidence and an explicit policy for any added marker. Note paragraphs/resources/styles remain content, not popup-only data.

## Images, equations, tables and styles

Inspect native image placement, masks and original pixels. Crop vectors/composites when extraction would omit labels or layers. Keep figcaption separate from caption OCR so it appears once. Formula crops preserve real notation; TeX recognition needs symbol-by-symbol comparison (sub/superscripts, matrices, alignment, signs, labels). Successful rendering is only a syntax/asset check. Long formulas/images must shrink within the reading area, never stretch. Preserve inline/display distinction and explicit equation-reference links.

Rebuild a table semantically only when row/column/cell content and ordering are trustworthy. Otherwise use a precise sharp table image, retain its caption and report image-table search limitations. Surrounding prose remains searchable and reflowable.

Native span flags can establish bold/italic and some superscripts, but drawn underlines/dots and baseline shifts need drawing/coordinate or image evidence. Scan OCR usually loses font/style information. Restore only the supported ranges, especially existing italic quotations. Quote classification alone adds no italics. Dot emphasis uses CSS and underline fallback, never inserted punctuation in searchable text. Keep all sizes relative and allow reader font overrides.
