# 目录、排除内容与章末注释

本参考用于执行 SKILL.md 的成品政策。页角色、目录位置、书签目标和注释配对在本机核实；源 PDF、页面图像及识别文本不加载到对话模型或远程服务。公开反馈仅给状态、页码、计数和检查结论。

## 提取前排除计划

在 WORK 保存 `publication-input.json`，或给 `inspect`/`extract` 传 `--publication-plan PATH`。计划必须绑定原 PDF 的 SHA256。没有计划的既有命令保留原行为，因此不能仅凭选页断言参考页已排除包装信息。页面角色不由关键词或页序自动推断。

```json
{
  "schema": "pdf-publication-input/1",
  "source_sha256": "<原 PDF 的 64 位十六进制 SHA256>",
  "exclusions": [
    {"page": 1, "role": "cover", "evidence": "本地确认完整封面"},
    {"page": 2, "role": "copyright", "evidence": "本地确认版权页"},
    {"page": 6, "role": "printed-toc", "evidence": "序言后原目录页"},
    {"page": 90, "role": "term-index", "evidence": "本地确认末尾术语索引"},
    {"page": 91, "role": "back-cover", "evidence": "本地确认完整封底"}
  ],
  "retained_regions": {
    "90": [{"bbox": [30, 30, 550, 260], "role": "bibliography", "evidence": "此上半页仍是参考文献，索引从下半页开始"}]
  }
}
```

物理页码从 1 开始。角色为 `cover`、`back-cover`、`belly-band`、`copyright`、`publication-info`、`printed-toc`、`term-index`。`publication-info` 用于版权、ISBN、包装中的作者译者等信息；正文 attribution 与参考文献不属于此角色。`retained_regions` 为混合页保留区域，使用原页 PDF point 坐标、明确角色和边界证据；其余区域排除。包装整页与混合保留区域不能同时指定。示例页码和坐标必须换成实际值。

本机 MinerU 适配器对已确认计划使用仅含允许区域的图像衍生输入，Standard 负责页、参考页与 Advanced 邻页都遵守排除规则。裁剪以实际渲染去除隐含页资源，不仅隐藏版面；衍生输入保存显式原页映射和源框，避免二次换算索引。多个保留区域分别处理。PyMuPDF/Tesseract 显式本地后端也遵守计划；带计划的云端后端拒绝执行。失败保留日志，不切换后端。

源绑定计划和排除依据进入 raw/state。先前已导入的结果通过带证据的 `omissions`/`semantic_resolutions` 排除对应行和语义块，覆盖核验照常执行；提取前排除的内容只记录原页/区域，不编造 raw ID。原 PDF 与原始提取保持不变。

## 书签目录与原位置

`inspect` 将本地原 PDF 书签保存到 `inspection.json.bookmarks`。编辑 `review.json.structure_rules.publication`，将书签索引映射到已有、源核实的章/节 ID；标题从书签读取，不能用 OCR 目录文字替代。以下是结构示例：

```json
{
  "toc": {
    "source": "pdf-bookmarks",
    "original_pages": [6],
    "evidence": "原目录在译者序之后、第一章之前",
    "placement": {"after": "translator-preface"},
    "entries": [
      {"bookmark_index": 0, "target": "chapter-1", "level": 1},
      {"bookmark_index": 1, "target": "section-1-1", "level": 2}
    ],
    "omissions": [
      {"bookmark_index": 2, "reason": "原书签指向已排除术语索引", "evidence": "本地核对目标页及页角色"}
    ]
  },
  "images": [
    {"role": "cover", "evidence": "源封面页已确认", "asset": {"id": "cover-image", "page": 1}},
    {"role": "back-cover", "evidence": "源封底页已确认", "asset": {"id": "back-cover-image", "page": 91}}
  ]
}
```

`bookmark_index` 是 `inspection.json.bookmarks` 中从 0 开始的索引。每个书签须有一个映射或有理由和证据的排除记录；选区外的书签也要解释。一级目标是章 ID，二级目标是相应章中的标题块 ID。源页须对应；卷/部等层级需收敛为章—节时，记录 `mapping_evidence`。需要按全角标点规则规范化显示标题时，可在该 entry 设置 `display_title` 和 `title_evidence`；原书签标题保留为 `source_title`，可见目录和导航共同使用有证据的显示标题。书签缺失、目标错误或未核实的映射会阻止此模式构建，先保存问题及本地核验结果。

`original_pages` 对应提取计划中的 `printed-toc` 原页。位置可以是 `{"before":"chapter-1"}`、`{"after":"translator-preface"}`，或目录与保留内容同页时 `{"chapter":"frontmatter","before_block":"following-block"}`。先按原书阅读顺序排列 `chapters`，将序言、导言、译者序等作为实际独立内容保留，再给目录指定相应位置；位置证据须能与相邻源页对应。原目录内容作为排除记录，不生成重复正文目录。

`build` 从同一映射生成两层导航及可见目录。可见目录使用可点击的分层块，含章与下属节，没有 `ol` 或自动序号。`nav.xhtml` 使用 EPUB 3 要求的嵌套导航列表，作为阅读器导航数据，不重复加入正文阅读顺序；参见 [EPUB 3.3 导航规范](https://www.w3.org/TR/epub-33/#sec-nav-def-model)。实际书签折叠方式由阅读器决定。

## 开头图像与删去内容

`images` 只接受实际存在的封面、封底，源页须对应排除计划中的角色。输出顺序固定为封面、封底，然后原顺序中的其余保留内容。图像可使用已核实的 WORK 相对 `path` 和 `sha256`，或由原源页完整本地渲染；图像替代文本仅使用角色，不识别书名、ISBN、广告或作者译者文字。只有封面资源标记为 EPUB cover-image，封底角色独立。

版权/包装信息和书末术语索引从成品中省略；独立腰封的文字不提取，封面/封底图像上已有的腰封外观保留。参考文献继续作为正文内容纳入。图像资源不得作为绕过排除的正文插图。源区域、排除依据和原始资源留在本地溯源文件中。

## 注释编号与校验

先完成既有 `notes` 的源配对和 `association_evidence`；每个正文引用具有独立 ID，同一注释可被本章重复引用。在 publication 模式，规范化/构建按本章正文首次出现顺序产生从 1 开始的标签，注释正文按同序放在本章末。所有引用强制使用小号数字上标，保留每处回跳；原标签保存为 `original_label`。跨章归属、没有正文引用或缺正文的注释须先解决，不能猜配。既有未配置 publication 的计划仍保留原标签及 baseline 兼容行为。

`normalize` 保留源证据并验证映射；`build` 再验证资源、目标及关系。校验须覆盖：原目录位置与前置序言顺序、章—节归属、全部跳转和回跳、每章从 1 开始的注释序列、封面/封底首位、索引删除及参考文献保留、混合页的保留边界。结构检查不代替全文终校或实际阅读器核验。
