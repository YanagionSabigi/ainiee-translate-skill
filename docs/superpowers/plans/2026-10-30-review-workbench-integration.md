# AiNiee 校对工作台实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 让本机 AiNiee 技能通过通用工作台完成术语表和微信读书反馈校对。

**Architecture:** 固定并附带上游运行资源；共享桥接层创建带独立本地 Git 的冻结材料包；词表、阅读两类适配器投影材料与当前稿，只消费正式提交。阅读写回继续调用既有 decisions/apply。

**Tech Stack:** Python 3.12、Git、jsonschema、原生 HTML/CSS/JS；无需 npm 构建。

**Spec:** `docs/superpowers/specs/2026-10-30-review-workbench-integration-design.md`（用户已确认）

## Global Constraints

- 上游固定 `1b800d28025846edffc404402e08ebb7ba95a90f`，保留 MIT 与 KaTeX 许可。
- 代码、分支、材料和验收留在当前工作区；不 push、不 PR、不部署。
- 草稿不是提交；留言不是最终译文批准；聊天继续后才消费正式提交。
- 原阅读报告、版本/CAS/事务/出版闸门保持可用。
- 原生界面沿用上游设计变量；实际检查 1280px、375px。

## Review Focus

- 重复源词、词表排序或未知字段：身份不符拒绝，未涉字段保留（任务 2）。
- 同段多 issue 或跨段重叠：按 segment 检测相互矛盾的决定，不能按顺序覆盖（任务 3）。
- 段内换行、emoji、HTML：逐 block 完整映射，纯文本呈现（任务 3/4）。
- 篡改映射、复制错包、业务版本漂移：Git 冻结绑定与业务检查均拒绝（任务 1/3）。
- 写回中断/重跑：词表原子化；阅读复用稳定 decision_id 与 recover（任务 2/3）。

## Task 1: 固定工作台与共享材料桥接

**Files:** 新增 `src/ainiee_translate/workbench_runtime/`、`workbench_bridge.py`、`workbench.py`；修改 `pyproject.toml`；测试 `测试/单元/test_workbench.py`。

**Interfaces:** `runtime()` 返回上游模块入口；`prepare_project(output, package, binding)` 创建独立审核项目；`load_project(project)` 验证 Git/材料/映射；`compare_project(project, targets)` 返回工作台比较结果。

- [x] 先写测试：包有 Git 基准且不改业务 HEAD；草稿不出现比较结果；篡改 binding 拒绝。
- [x] 运行新测试，确认模块缺失而失败。
- [x] 附带上游运行包、schemas、web 与许可；桥接层用冻结 scope 绑定映射，不修改上游提交语义。
- [x] 运行 `pytest 测试/单元/test_workbench.py`，预期通过；提交本任务。

## Task 2: 术语表材料与受控写回

**Files:** 新增 `workbench_glossary.py`、`测试/单元/test_workbench_glossary.py`；扩展 `workbench.py`。

**Interfaces:** `prepare_glossary(locked, output, proposals=None)`；`glossary_targets(binding, locked)`；`apply_glossary(project, locked, instruction)`。

- [x] 测试先行：接受、保留、编辑、评论；只消费正式提交；保留未知字段和他条变化；身份漂移/冲突/Schema 拒绝；重跑无重复写入；缺建议不伪造 proposal。
- [x] 运行测试观察缺失行为；实现索引+原词身份、字段投影、锁内 compare/备份/原子写入。
- [x] 运行 `pytest 测试/单元/test_workbench*.py`，预期通过；提交本任务。

## Task 3: 微信读书材料与既有事务接通

**Files:** 新增 `workbench_reading.py`、`测试/单元/test_workbench_reading.py`；扩展 CLI。

**Interfaces:** `prepare_reading(round_dir, cache, output, report_revision=None)`；`reading_targets(binding, cache)`；`apply_reading(project, cache, instruction)`。

- [x] 测试先行：推荐转正式决定并用既有 writer 写回；逐段手动编辑保留段内换行；评论不写；过期评估/意见/当前稿拒绝；重跑幂等；重叠 segment 不同结果拒绝；冻结映射篡改拒绝。
- [x] 实现完整 issue/report/edition/segment 绑定、原文想法候选 evidence、逐 block 决定、稳定 decision_id、业务 CAS；评论进入返回的 needs_agent。
- [x] 运行新适配测试与现有 reading 测试，预期通过；提交本任务。

## Task 4: 技能路由、视觉与安装验收

**Files:** 修改 `skills/ainiee-translate/SKILL.md`、`references/weread_proofreading.md`，新增 `references/review_workbench.md`，更新 `commands/glossary.md`、`commands/reading-review.md`；更新 bundle；验收文档 `docs/review-workbench-validation.md`。

- [x] 更新技能前，独立行为检查记录当前文档仍只指向旧静态报告的缺口；更新后用相同场景复核路由与提交边界。
- [x] 用 `local/reading-projects/oxygen-live` 的真实副本创建两类工作台；不虚构或提交真实用户决定。
- [x] 上游界面仅必要局部补丁：AiNiee 标识、业务说明；正文保留上游阅读布局和 tokens，注释记录内容层级与变量约束。
- [x] 启动实际服务，查看 1280/375 截图并操作保存、恢复、提交（正式提交仅隔离合成演练），记录视觉审核和限制。
- [x] 相关回归、全套现有测试、上游运行测试、`build.py --check`、独立打包入口校验；独立全分支代码审阅并修复重要问题。
- [x] 本机技能更新前备份到 local；安装后从中立目录验证 CLI。只保留本地提交与验收资料。
