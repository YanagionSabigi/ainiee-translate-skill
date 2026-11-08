# 出版模板

`epub/` 保存当前 EPUB 样式的副本；`typst/` 预留给后续制作。
`tex/` 中有 Rosé Pine 和数译风格的 book、article 六份示例，使用 XeLaTeX
编译三次。请进入对应示例目录运行 `xelatex main.tex`，或运行
`python tex/build_previews.py` 重建全部预览。article 使用 `ctexart`，
层级为 section 至 subsubsection，目录单栏；book 具有 part 至
subsubsection，目录双栏。所有模板均在目录前后分页，目录深度为 1。

Rosé Pine 使用官方 Dawn 调色板：<https://rosepinetheme.com/palette/>。
其 book、article 默认暖米色页面；`white.tex` 生成相同内容的白底版本。
定理与推论在 Dawn 下使用 Overlay 浅米粉色 (`#f2e9e1`)，白底版使用
原有浅蓝灰色；均无外边框。命题、引理、定义、公理和声明使用
留白与轻微缩进。`\termcn{术语}` 用于突出首次出现的定义术语。
证明用 Pine，引用用 Iris，例用 Foam，习题用 Love；均使用较细边线，
无阴影或悬浮题签。`reading-style.tex` 管理这些样式，
`reading-sample.tex` 提供连续阅读样章与可选分页压力测试。
Rosé Pine article 保留上一版样式。

数译 book、article 回退到最初的简洁环境与默认列表样式；book 的
定义、定理、命题、引理、推论、公理和声明仍在题头后换行。
两者证明使用 amsthm 的默认环境与末尾 QED 方框。
各模板的引用使用独立的 `\quoteauthor{作者}{著作名}`，
小一号楷体，署名靠右，无 QED。
六份示例均包含三级嵌套的无序列表，并用第三级长条目检查折行缩进。

`tex/reference/` 保留所参考的原始文件及其来源；项目原有导出模板仍由
现有出版代码使用，故没有移除。示例中的文字和图形均可替换。

六份示例是根据参考模板的配色、页面和字体习惯重新组织的独立文件，
并非原模板的完整功能移植。数译参考文件及许可见
`tex/reference/mathtranslations/`；Rosé Pine 的来源、版本和许可见其
`NOTICE` 和 `LICENSE`。这些素材随技能 ZIP 和 wheel 分发，可独立改编，
尚未替换自动导出程序的模板。

面向使用者的六份源码／PDF 索引和实际截图见[输出模板选择](../docs/输出模板选择.md)。
