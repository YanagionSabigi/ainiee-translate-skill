# 发布包与 CC Switch

`v2.1.1` 同步新版工作台，精简交给他人的审核包，提供 export/import-results 入口。审核端不再携带 SKILL、示例、Git 仓库或普通文本不需要的公式资源。验证与启动计时见 [精简审核包验收](portable-review-validation.md)。`v2.1.0` 引入的术语表与微信读书交互校对、草稿恢复、正式提交和受控写回继续保留。此前的 `v2.0.0` 正式版与 `v2.0.0-rc.1` 预发布继续保留。实际 skill 名称及安装目录继续为 `ainiee-translate`，保留既有缓存工具的调用名。

GitHub Release 提供完整 skill ZIP、Python wheel、逐文件 manifest 和 `SHA256SUMS`。ZIP 解压后只有一个 `ainiee-translate/`，含 SKILL、脚本、共享 publisher、工作台离线资源、模板、引用资料及许可证；无需另行安装 publisher 或工作台 skill。工作台需要 Git 和 jsonschema，公式决定还需 Node.js。用户 PDF、译文、笔记、审核项目、模型、运行配置、API 凭据及日志均不在发布包中。

CC Switch 的来源仓库配置：

| 字段 | 值 |
| --- | --- |
| 仓库 | `YanagionSabigi/ainiee-translate-skill` |
| 分支 | `release` |
| 技能路径 | `skills/ainiee-translate` |

`main` 和 `release` 同步到当前正式版本，仓库首页显示对应用户指南。CC Switch 从 `release` 分支归档获取并检查更新，不把标签名直接当分支；固定版本请使用 Release ZIP。更新时先备份中央主副本，再同步已启用的应用目录，保留原有应用开关。不要只覆盖某一个客户端副本，否则中央主副本重新分发会恢复旧版。

原 PDF 缓存不能自动迁移，需要保留旧缓存并从原 PDF 新建项目。MinerU 安装路径仅在本机通过 `AINIEE_MINERU_ROOT` 或 `--mineru-local-root` 配置。测试步骤见 [fork-testing.md](fork-testing.md)，完整流程见 skill 的 PDF 工作流。

维护者构建：

```powershell
python build.py --check
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
python build_release.py
python build_release.py --check
```

打包只选 Git 跟踪的 skill 文件；生成 ZIP 可重复，manifest/checksums 与源文件逐项校验。全量测试和发布前隐私扫描仍需独立运行。

## v2.1.0 发布验证

- 发布副本完整回归：280 passed（421.86s）。工作台开发阶段的行为、视觉与审查回归见 [接入验收](review-workbench-validation.md)。
- 源码与技能 bundle 一致；技能 ZIP 含 256 个跟踪文件，wheel 包含工作台离线网页、Schema、KaTeX、字体和许可证。
- ZIP 与 wheel 均从中立目录实际运行，完成准备材料、保存、提交、受控写回及重复执行无修改的合成测试。
- `build_release.py --check` 对照源码、manifest 与 SHA256SUMS 核验；发布附件不含书籍、阅读笔记、审核项目、凭据或本机日志。
- 此次发布未重新执行实时账号同步、整本交付、MinerU 提取、模板 PDF 编译或正式 EPUBCheck。
