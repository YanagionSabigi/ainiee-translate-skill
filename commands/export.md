---
description: 导出原格式，或把结构 PDF 译文导出为 Markdown/EPUB
argument-hint: <原始输入文件>
allowed-tools: Bash
---
导出当前项目的成品（保留原书结构与标签；已润色的段落自动用润色文本）。

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/skills/ainiee-translate/scripts" \
"${AINIEE_PY:?}" -m ainiee_translate.export --cache work/cache.json --output out/ --input "$1"
```

完成后报告 `out/` 下的成品路径。

新 PDF 默认 EPUB。先读 `references/pdf_workflow.md`，提供当前术语表、提示词和独立对照校对记录；正式导出所有格式共用版本绑定与关系闸门。请求原版式 source 输出会明确报不支持；旧 PDF 缓存需要从源 PDF 建立新项目。

对真正的 EPUB ZIP 运行 `ainiee_translate.book_check`，分别记录本地结构、正式 EPUBCheck 和实际阅读器检查。未运行的检查保持未测状态，报告实际版本/宽度/字体与未解决问题。

需要模板排版时，先读 `references/book_templates.md`。`--format latex --format typst` 生成可编辑源码；`--format pdf` 默认编译两条路线，`--pdf-engine latex|typst` 可选择一路。`--book-settings` 指向 JSON 配置。使用现有目标结构，不重新提取或翻译；工具/字体缺失或编译失败必须报告，不能把残留旧 PDF 当作新成品。
