# 默认术语表实现计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** 将已批准的通用术语表完整接入 module 与既有翻译、审核流程。
**Architecture:** 单份结构化正式词表，独立哈希绑定政策快照；集中式校验与运行时视图兼容旧流程；工作台始终编辑原始字段。
**Tech Stack:** Python 3.12、已有 jsonschema、pytest、现有工作台协议。
**Spec:** ../specs/2026-11-06-default-glossary-design.md（用户于 2026-11-06 明确接受并要求执行）。

## Global Constraints

- 不预置领域分类或词条，只在 Markdown 推荐提前生成分类。
- A/B/C/D 保留，默认 D；缺资料保留源文并报告问题。
- 旧 module、profile、冻结审核包和未知旧字段兼容。
- 工作区内开发，保留原 template checkout；无 PR、推送、发布或已安装技能改动。
- 词表与 policy 配套复制，丢失／哈希不符拒读；模板与固定译文互斥。

## Review Focus

- 多义姓名／缩写不应产生多个互相矛盾的强制译文。
- 表移到另一个目录／改名后政策不能回退。
- 手改政策或审核期间更改政策不能静默应用旧决定。
- 工作台改译名不能扁平化正式词表或破坏引用。
- 不完整候选与未知姓名体系必须保持可见。

## Task 1：完整接入（同一变更的契约、消费者与审核必须一起可用）

**Files:** 新增 src/ainiee_translate/glossary_document.py、schemas/glossary.schema.json、schemas/glossary-policy.schema.json；修改 glossary.py、module.py、verify.py、scan.py、review.py、precedents.py、workbench_glossary.py；新增 测试/单元/test_glossary_document.py、test_glossary_module.py、test_glossary_workbench_v1.py；按需增加内部辅助文件。

**Interfaces:** `empty_document() -> dict`；`validate_document(data: dict) -> None`；`read_document(path) -> dict`；`read_policy(path, document=None) -> dict`；`write_document(path, document, policy=None) -> None`；`runtime_view(data, policy=None) -> dict`；`load_runtime(path) -> dict`。runtime_view 使用现有 characters/terms/non_translate 字段并附带 _issues 和 _structured 标识，稳定 ID 保留在视图条目。read_document 对旧表原样返回；load_runtime 对旧表不改变语义。

- [ ] 先写有行为断言的失败测试，证明默认新 module 使用空新契约、四模式输出、未知体系报警、无预置分类、非法引用／树、模板互斥、政策丢失／不符及跨目录过滤不会丢政策；运行观察失败。
- [ ] 实现上述契约、原始读写、政策文件、运行视图及必要内部辅助。默认 Schema 与可选项目 Schema 都校验原始文档。
- [ ] 新 module create/show/list/load 接口保留旧参数，增加 name_mode/categories/category_ids；CLI 提供 --name-mode、--categories、--category。重复创建冲突报错，旧模块不转换。
- [ ] 将 glossary CLI 的 lint/filter/merge-newterms 与消费者接通原始文档或运行视图；新格式 verify 根据源形式识别再检查目标，多义返回待辨义。
- [ ] 写失败测试验证工作台新格式的真实提交／比较／回写、ID 绑定、其他字段保留、政策漂移冲突与模板保存；实现后验证转绿，保留旧工作台行为。
- [ ] 使用 ../ainiee-translate-skill/.venv/Scripts/python.exe，pytest --basetemp=local/glossary-implementation --tb=short 运行新测试及相关旧回归；记录 RED/GREEN 证据，然后运行全量 pytest。
- [ ] 独立审核任务变更，修复重大问题，保存实际测试结果并本地提交。

## Task 2：文档、技能包与交付验证

**Files:** commands/module.md、commands/glossary.md、skills/ainiee-translate/references/glossary_schema.md、skills/ainiee-translate/SKILL.md、README.md、pyproject.toml（必要时）；同步技能脚本副本；docs/superpowers/reviews/2026-11-06-default-glossary-verification.md。

**Interfaces:** 使用 Task 1 的实际 CLI 和 Schema；文档明确字段、政策快照配套携带、四种姓名模式与生成分类的建议，不增加学科默认值。

- [ ] 更新使用说明、Schema 参考与 module／术语整理入口，并清楚说明旧表不迁移。
- [ ] 将 src 的新增／修改文件同步到技能副本，验证字节一致；不要使用会引入其他 checkout 出版工具修改的无关同步。
- [ ] 验证打包包含两个 Schema，运行相关前端测试、全量 Python 回归、git diff --check。
- [ ] 独立全分支复审并修复重要问题；更新设计状态、验收记录，保留本地分支交付。

## 执行记录

用户已接受具体设计并要求开始执行，继续在现有分支执行，不另设计划确认关卡。实现交由一个执行者连续完成 Task 1；主控并行处理只涉及文档和打包说明的 Task 2 准备，最终统一审核。
