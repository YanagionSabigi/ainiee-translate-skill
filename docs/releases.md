# 发布包与 CC Switch

`v2.0.0-rc.1` 是 PDF/EPUB 重构的测试版。实际 skill 名称及安装目录继续为 `ainiee-translate`，保留既有缓存工具的调用名。

GitHub Release 提供完整 skill ZIP、Python wheel、逐文件 manifest 和 `SHA256SUMS`。ZIP 解压后只有一个 `ainiee-translate/`，含 SKILL、脚本、共享 publisher、模板、引用资料及许可证；无需另行安装 publisher skill。用户 PDF、译文、模型、运行配置、API 凭据及日志均不在发布包中。

CC Switch 的来源仓库配置：

| 字段 | 值 |
| --- | --- |
| 仓库 | `YanagionSabigi/ainiee-translate-skill` |
| 分支 | `release` |
| 技能路径 | `skills/ainiee-translate` |

`release` 指向最近发布的版本提交。CC Switch 从分支归档获取并检查更新，不把标签名直接当分支；固定版本请使用 Release ZIP。`main` 仍保留上游基线。更新时先备份中央主副本，再同步已启用的应用目录，保留原有应用开关。不要只覆盖某一个客户端副本，否则中央主副本重新分发会恢复旧版。

原 PDF 缓存不能自动迁移，需要保留旧缓存并从原 PDF 新建项目。MinerU 安装路径仅在本机通过 `AINIEE_MINERU_ROOT` 或 `--mineru-local-root` 配置。测试步骤见 [fork-testing.md](fork-testing.md)，完整流程见 skill 的 PDF 工作流。

维护者构建：

```powershell
python build.py --check
python -m pip wheel --no-deps --no-build-isolation --wheel-dir dist .
python build_release.py
python build_release.py --check
```

打包只选 Git 跟踪的 skill 文件；生成 ZIP 可重复，manifest/checksums 与源文件逐项校验。全量测试和发布前隐私扫描仍需独立运行。
