# 校对工作台接入验收 · 2026-10-30

## 交付内容

本地分支 `feat/review-workbench-integration`。采用用户确认的路线 A：附带 Review Workbench 本体及两个 AiNiee 适配器。上游固定为 `1b800d28025846edffc404402e08ebb7ba95a90f`；保留 MIT、KaTeX 及字体资源许可证。原生 HTML/CSS/JS，无 npm 构建；jsonschema 明确加入 Python 依赖。

术语表按人物、术语、禁翻项分组，保留未知字段，支持建议对照、保留、逐字段编辑和留言。微信反馈保留原 WR 编号、报告/评估/意见版本、现译、推荐、阅读想法、原文与候选依据；逐段映射，段内换行不拆段。无真实建议或未辨析项不伪造推荐。

自动保存仍是草稿；用户正式提交并回到聊天明确继续，agent 才比较当前稿、核验并写回。留言进入待辨析队列。词表备份后原子写入；正文使用既有 reading 决定及 CAS 事务。相互矛盾的提交、过期业务版本、身份变化和冻结材料篡改都拒绝覆盖。

## 自动验证

- 首轮相关基线：27 passed。
- 首轮完整回归：271 passed；独立审查修正后完整回归：279 passed。
- 最终完整回归：**280 passed（337.89s）**，输出 `local/workbench-accepted-tests.log`（最后一项临时文件修正后执行）。
- 工作台上游测试：33 passed；实际附带运行资源兼容测试：33 passed。前端纯函数测试：7 passed。
- 8 个审查回归先复现失败，修正后与原决定测试共 19 passed；新增“差异临时文字留在私有审核项目”回归先失败、后通过。
- `build.py --check`、技能 quick_validate 均通过；最终 wheel 实际构建、解包，并核对 schemas、网页、字体和许可证齐全，无 pycache。
- 已安装技能和 wheel 解包版本均从中立目录实际运行 `workbench --help`，并比较真实阅读项目与合成项目，均返回成功。

## 独立审查与处理

审阅者提出的有效问题已逐项验证并修正，没有用复审意见替代回归证据。

| 问题 | 修正 | 回归 |
|---|---|---|
| 本地提交文件未重新校验包身份或 accept 全文 | 按导入结果的同等边界校验 Schema、包/基准、目标、完整决定和 resolves 图 | `test_tampered_submission_is_rejected` 三种参数 |
| 重复原词换序可能命中另一个词条 | 冻结不可编辑身份字段的哈希；身份不符保持当前稿 | `test_duplicate_source_rows_cannot_be_swapped` |
| 比较后新提交可能使旧结果过期 | 消费前核对历史指纹，消费期间持有 Store 锁 | `test_new_submission_between_comparison_and_write_aborts` |
| 空别名/说明阻止手动修改 | 冻结材料明确声明可空字段，前后端一致校验；正文仍要求非空 | `test_optional_fields_can_stay_empty_or_be_cleared` |
| 决定文件落盘后、状态投影前中断 | 以相同完整决定恢复登记，保留原出处与稳定决定 ID | `test_interrupted_decision_registration_recovers_projection` 两种动作 |
| Windows 受限系统临时目录使比较失败 | 适配器将差异临时文字放在私有审核包内；保持上游默认接口兼容 | `test_comparison_keeps_temporary_book_text_inside_review` |

## 真实材料与界面

使用本机 2026-10-18 的《氧气》微信读书历史快照及既有辨析，未调用实时账号接口。工作副本包含 8 条手机反馈和 1 条独立扩展发现；术语表包含 218 条术语与 6 条禁翻项。工作台数据、快照、原页、Git 基准、截图和备份均留在忽略的 `local/`，不加入开发仓库历史。

实际浏览器检查两种页面的 1280px 桌面与 375px 手机布局。修正手机页头换行拥挤、词表字段缺标签和成功提示颜色；保留可折叠目录、单项/连续阅读、搜索、差异标记和清晰焦点。九组主要文字配色的对比度均超过 4.5:1，最低 5.21:1。

| 层面 | 实际检查结果 | 规则 |
|---|---|---|
| 层级 | 当前稿与建议双栏；手机想法默认可见，源文和版本细节可展开；主操作为提交本轮 | §2.1、§2.8 |
| 间距 | 沿用上游 4/8/12/16/24/32/48px 系统；分组间距大于组内 | §3.2、§3.6 |
| 文字 | 正文沿用 18px 阅读字体、宽度约束与较高行距，手机改为单栏 | §4.3、§4.5 |
| 颜色 | 保留纸色、绿、墨色变量；状态同时使用文字与标记；成功提示使用绿色语义 | §5.6、§5.7 |
| 深度与细节 | 沿用上游边框、背景与圆角，不叠加装饰性阴影；无建议时接受按钮禁用 | §6.4、§8.4 |

截图：`local/workbench-validation/oxygen-final-1280.png`、`oxygen-reading-375.png`、`oxygen-glossary-1280.png`、`oxygen-glossary-375.png`。合成界面演练实际完成：编辑包含 emoji 的译名，空别名/说明保留，自动保存，刷新恢复，正式提交，再由业务适配器写回；重跑为无修改。成功截图为 `synthetic-final-submitted.png`，结果为 `synthetic-final/apply-result.json`。

《氧气》真实页面保持零人工提交，本次未对原书项目执行写回，也未生成阶段 EPUB。原 PDF 核验材料沿用既有记录，不声称本轮重新审阅全书原页或完成整本交付。

## 本机安装与保留的决定

已更新 `C:/Users/10166/.codex/skills/ainiee-translate`，仅更新本次涉及的 105 个文件，逐项校验 SHA256。原有其他文件保留。备份在 `local/workbench-validation/installed-skill-backup`，清单与核验回执分别为 `install-manifest.json`、`installed-receipt.json`。

- 在现有工作区的独立功能分支实施，未建立可能位于工作区外的原生 worktree；代价是开发共用现有 checkout，当前修改均已核对归属。
- 用户确认设计并要求继续后，实施计划作为内部执行安排，不再重复请求流程批准；未扩大产品范围。
- 暂存和验收均保持在工作区，保留本地分支与备份；不 push、不 PR、不部署。用户可后续决定如何合并。
- 现阶段网页不增删术语实体，缺失的候选保持缺失；选择其他候选可逐段编辑，留言需要再辨析。此为已批准设计范围。

没有已知需要延期处理的重要审查项。
