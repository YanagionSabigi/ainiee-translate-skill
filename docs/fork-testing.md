# Fork 测试入口

此分支为 YanagionSabigi 的 PDF/EPUB 重构测试分支，不代表上游发布。保留上游作者及许可证归属；暂不创建 PR。

```powershell
git clone --branch refactor/pdf-epub-first https://github.com/YanagionSabigi/ainiee-translate-skill.git
cd ainiee-translate-skill
python -m venv .venv
.venv/Scripts/python.exe -m pip install -e ".[pdf]" pytest
New-Item -ItemType Directory -Path local -Force | Out-Null
.venv/Scripts/python.exe -m pytest --basetemp local/pytest
.venv/Scripts/python.exe build.py --check
```

独立克隆已携带 `publication_skill`，安装和运行不要求另行克隆 publisher、不依赖原作者电脑路径。若工作区存在兄弟目录 `pdf-to-epub-skill`，开发构建优先使用那个开发副本；否则使用仓库随附版本。

本地 MinerU 没有内置安装地址。请仅在本机环境设置 `AINIEE_MINERU_ROOT`，或在调用 publisher 时传 `--mineru-local-root`；安装中的 CLI、配置和环境脚本也可分别显式指定。完整操作见 [PDF 工作流](../skills/ainiee-translate/references/pdf_workflow.md) 与 [MinerU 配置](../skills/ainiee-translate/scripts/ainiee_translate/publication_skill/references/mineru.md)。PDF 格式依赖、本地模型、Java/EPUBCheck、模板字体及编译器需由测试环境准备。

不要提交 `.env`、API token/key、私人 PDF/译文、运行缓存、绝对安装地址或详细运行日志。这些资料只保存在忽略的本地目录；真实凭据通过本机环境或秘密管理器传入。`.env.example` 仅为无凭据占位示例。提交请使用 GitHub 的 `users.noreply.github.com` 隐私邮箱。

人工测试建议覆盖：中文及空格路径、数字/扫描/双栏 PDF、初翻后的局部 OCR 修订、独立原页校对、跨章注释与书目回跳、正式 EPUBCheck 和实际阅读器、同一译书的 TeX/Typst 输出。原始提取与源书历史必须保留；旧 PDF 缓存需要从原 PDF 新建，不能绕过正式闸门自动迁移。
