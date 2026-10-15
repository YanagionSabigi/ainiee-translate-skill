---
description: 端到端翻译 EPUB/TXT 或经结构审阅的本地 MinerU PDF
argument-hint: <输入文件> [模块名]
allowed-tools: Bash, Read, Edit, Task
context: fork
---
用 **ainiee-translate 技能** 把 `$1` 端到端翻译完。

前置：确认环境变量 `AINIEE_PY` 已设（脚本路径 `${CLAUDE_PLUGIN_ROOT}/skills/ainiee-translate/scripts`，作为 `PYTHONPATH`）。输入含 PDF 时先读技能 `references/pdf_workflow.md` 并配置独立 MinerU 环境；`AINIEE_REPO` 仅用于显式 BabelDOC / Office 回退。

步骤：
1. 准备项目工作目录（如 `~/<书名>-translate/{work,out}`）。
2. 若提供了模块名 `$2`：先 `python -m ainiee_translate.module load $2 --work <项目>`（把该模块的提示词+词汇表载入项目）。否则提示用户用 `/ainiee-translate:import-profile` 或 `/ainiee-translate:module create` 准备一个模块，或直接用 AiNiee 配置走默认流程。
3. 普通 EPUB/TXT 按 SKILL.md 的 parse → scope → glossary → 翻译/润色 → export → verify/audit 执行。新 PDF 先 inspect、审阅 publication-input、extract、draft、核验结构与完整资源、normalize，再 parse；范围由出版计划确定。失败保留诊断并修复，不自动回退。旧 PDF 缓存按原后端导出，转换 MD/EPUB 须另建经核验结构项目。
4. 翻译规则遵循原生原则、模块/用户提示词、项目 style.md 与锁定词汇表。项目提供 glossary Schema 时，验证成功后才加载/翻译。PDF 结构标记、公式、代码及注释链接由结构层管理；即使 force 也不可破坏。批次参考只读，主控统一写回。

完成后报告进度与产物路径。
