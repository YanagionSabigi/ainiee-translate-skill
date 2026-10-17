# PDF/EPUB 统一流程交付记录

完成日期：2026-10-17。设计依据：工作区 `docs/superpowers/specs/2026-10-16-pdf-epub-first-design.md`。

PDF 检查、提取、规范书与 EPUB 写包统一调用 pdf-to-epub。AiNiee 维护稳定单元到 CacheProject 的适配、修订历史、独立校对与人工问题账本；正式 EPUB、Markdown、TeX、Typst 使用同一译书和出版闸门。旧 PDF 缓存明确拒绝，需从原 PDF 新建项目；BabelDOC 参数、重复提取器和旧 EPUB 写包器已删除。

本地自动化验收：AiNiee 165 项通过，publisher 9 项通过。命令：

```powershell
.venv/Scripts/python.exe -m pytest -q -o addopts='' --basetemp local/final-delivery
.venv/Scripts/python.exe build.py --check
# 在 ../pdf-to-epub-skill 中：
../ainiee-translate-skill/.venv/Scripts/python.exe -m pytest -q -o addopts='' --basetemp local/final-delivery
../ainiee-translate-skill/.venv/Scripts/python.exe build.py --check
```

实际新样本为自制六页数字/扫描/双栏 PDF。采用本地 MinerU 4.0.10 的结构化 ZIP，处理正文四页、25 块；两个排除页保留封面/目录政策。48 个单元（46 个翻译、2 个书目保留原文）完成独立原 PDF 对照。初翻后修正刻意设置的 OCR 错误，1 项重译、47 项保留；公式资源属性修订只重审相关 1 项。随后实际恢复已完成 MinerU 任务，没有新增推理，也没有改写缓存或源/校对文件。

真实 EPUB 经 EPUBCheck 5.4.0：0 fatal/error/warning。EPUB.js 浏览器中验证了常规宽度和 420px/22px 字号、章/节/图/表/公式链接、跨章同一注释与三个引用处回跳、作者年份和多目标书目引文。XeLaTeX 与 Typst 均生成四页最终 PDF，逐页查看无缺字、溢出或重复公式编号。另用明确标记为 synthetic 的 120 行表格测试续页，两种表头、两个引擎均生成七页 PDF；这些合成证据只验证排版，不计入真实源文校对。

独立代码审查最初七项重要问题已修复并定向复审。完整原始记录、逐项校对、成品、哈希和截图保存在工作区 `测试/验收报告/`；总报告为 `pdf-epub-first-delivery.md`，机器证据为同名 JSON。实际书籍和运行资料不进入工具仓库或分发包。

分发物：`dist/ainiee_translate-0.2.0-py3-none-any.whl`、兄弟仓库 `dist/pdf-to-epub-2.0.0.zip`。wheel 与 skill bundle 均携带 publisher 原样副本，逐文件与源代码比较；在独立 PYTHONPATH 下，两个包均用相同定稿缓存实际生成 EPUB。与开发源码版相比，所有解包内容仅 OPF 构建时间不同，两包的 EPUBCheck 也均为零错误/警告。

部署由用户另行决定：可先将 ZIP 解压到独立测试目录，通过 `AINIEE_PDF_TO_EPUB` 显式选择；或在独立虚拟环境安装 wheel。Python 依赖参见 pyproject 的 pdf extra 与 publisher requirements；提取需要预先配置好的本地 MinerU，正式 EPUB 检查需要 Java/EPUBCheck。模板需要本地 XeLaTeX 或 Typst、已安装字体；可编辑 TeX 数学转 Typst 还需 Pandoc。全部工具和模型需独立准备，分发包不附模型/字体，也不自动下载。全局技能尚未替换。

范围：实际交互仅验证上述 EPUB.js 阅读器；未运行真实 Office 应用自动化，原有 Office 兼容边界由回归验证。TeX/Typst 合并单元格需审阅过的表格图像回退；强调点样式采用下划线回退。无待决定的样本问题。只保留本地分支与提交，没有推送或 PR。
