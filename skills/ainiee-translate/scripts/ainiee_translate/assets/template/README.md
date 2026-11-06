# 出版模板

`epub/` 保存当前 EPUB 样式的副本；`typst/` 预留给后续制作。
`tex/` 中有 Rosé Pine 和数译风格的 book、article 四个示例，使用 XeLaTeX
编译两次。请进入对应示例目录运行 `xelatex main.tex`。article 使用
`ctexrep`：它具有章级结构，同时采用单面、连续的文章版式。

`tex/reference/` 保留所参考的原始文件及其来源；项目原有导出模板仍由
现有出版代码使用，故没有移除。示例中的文字和图形均可替换。

四个示例是根据参考模板的配色、页面和字体习惯重新组织的独立文件，
并非原模板的完整功能移植。数译参考文件来自本机 MathTranslations
技能的 `assets/`；Rosé Pine 的来源、版本和许可见其 `NOTICE` 和
`LICENSE`。这些独立素材已随 v2.3.0 技能 ZIP 和 wheel 分发，包含可编辑 TeX 与 PDF 预览；尚未接入自动导出程序。
