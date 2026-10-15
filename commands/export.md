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

新 MinerU PDF 使用 `--format md --format epub`；默认 `source` 会明确解释为 Markdown。先读技能 `references/pdf_workflow.md`，确认源结构已核验、应译单元完成、公式与资源可定位，再导出。`--allow-partial` 仅输出标明用途的诊断草稿及缺失单元清单。旧 BabelDOC PDF 缓存保持原 writer；请求新的 MD/EPUB 转换时另建结构项目，不按 parse 新默认值改变旧缓存来源。

对真正的 EPUB ZIP 运行 `ainiee_translate.book_check`，分别记录本地结构、正式 EPUBCheck 和实际阅读器检查。未运行的检查保持未测状态，报告实际版本/宽度/字体与未解决问题。
