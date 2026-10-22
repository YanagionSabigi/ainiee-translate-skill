# 微信读书人工校对 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> 本次仅交付计划。用户要求下一个 agent 接手，未选择并行实施方式；接手时按用户当次指令选择执行方式，采用 applicable skills，不能把本交接文件当作用户已授权派发多个 agent、安装全局 skill、访问账号或发布远端内容。

**Goal:** 将微信读书蓝色波浪线及想法接入 AiNiee，形成固定阅读版本、原文辨析、桌面 HTML、聊天批复、受控写回和整本最终交付的闭环。

**Architecture:** 官方 WeRead skill 提供能力契约，AiNiee 的可选只读适配器保存接口快照；本地 round 将微信记录绑定冻结 EPUB 与原译单元。agent 产出辨析和人工批复的结构化文件，确定性脚本负责校验、静态 HTML、幂等写回和发布检查，复用既有 PDF 证据及出版管线。

**Tech Stack:** Python >=3.12、标准库 urllib/json/hashlib、现有 BeautifulSoup/lxml、pytest、既有 PDF optional dependencies、静态 HTML/CSS；正式验收使用 Java/EPUBCheck。

**Spec:** [已确认需求与设计](../specs/2026-10-18-weread-proofreading-design.md)，要求 R01—R12 是实现验收依据。

## Global Constraints

- 用户完整决策以 Spec §2 为准；Q12 的最终更正是整本书校对完成才交付新版，不实现阶段版发布。
- 仓库为本工作区 `development/ainiee-translate-skill`，不能在工作区根初始化另一 Git 仓库。源码基线为 `67251a080d5d2b34dda1aedf866479ea701b88b6`，原分支 `refactor/pdf-epub-first`。
- 本计划分支 `docs/weread-proofreading-plan`。实施从包含本计划的实际 HEAD 建 feature 分支，不能切回源码基线而丢失本计划；保留其他人的工作。
- 工作区上层 `AGENTS.md` 仍适用：本地代码、Git 历史、分支及验收资料留在本工作区；PR 需要新的明确指令。本计划不授权 push、Release、部署或全局 skill 替换。
- 采用现有锁、备份、原子保存、PDF 独立校对和出版闸门；微信批复不能复用旧 review 的自动接受路径。
- 运行资料不入 Git；通用夹具全部自造。提交沿用项目身份并使用仓库历史已有的 noreply 邮箱，命令级配置即可，不修改全局 Git 配置。
- 只更改 canonical src，之后用 `build.py` 同步本仓库 skill bundle；不手改 public-fork、全局安装和 publisher 副本。

## Review Focus

1. 分页中断/增量结果不能冒充完整快照并误判删除：Task 0、2 验证 completeness 和 tombstone 规则。
2. 重复句、跨段摘录、emoji/空白和同名章节不能误定位：Task 1、3 验证候选与可逆文本映射。
3. 人在旧报告上批准时，新推荐或新想法不能偷换获批文本：Task 4、5 验证报告/评估/标注版本绑定。
4. 同段多条意见、另一个写入者及中途崩溃不能覆盖已改内容或重复应用：Task 5 验证 CAS、冲突、恢复和撤回。
5. PDF 定稿变化必须产生新 proof，书籍/想法中的 HTML 和伪指令不能成为可执行内容：Task 4、6、7 验证证据更新及报告转义。

## 0. 接手入口与当前状态

本轮已经完成：需求访谈、代码接口勘察、官方公开接口文档核查、本计划及 Spec。尚未安装/调用 WeRead、尚未证明蓝色样式值、尚未添加功能、尚未运行该功能的任何验收。现有 README 中的历史测试数量不是本功能证据。

本机仓库绝对路径：

```text
<workspace>\development\ainiee-translate-skill
```

按顺序执行启动检查；`git status` 若有改动，先辨认其归属，继续在其基础上工作，不能重置：

```powershell
Set-Location -LiteralPath '<workspace>\development\ainiee-translate-skill'
Get-Content -LiteralPath '..\..\AGENTS.md'
git status --short
git branch --show-current
git log -3 --oneline
git switch -c feat/weread-proofreading
.venv/Scripts/python.exe --version
.venv/Scripts/python.exe -m pytest --basetemp local/pytest-weread-baseline
.venv/Scripts/python.exe build.py --check
```

分支名已存在时核实再复用，不重建或覆盖。venv 不存在时按 `docs/fork-testing.md` 建本地环境，先读 pyproject；基线失败先记录，不能拿历史数量当本次通过。Windows PowerShell 命令均在仓库根执行；所有下面的 `python` 省写实际指 `.venv/Scripts/python.exe`。

### 已核实的接入点

| 当前文件 | 可复用能力 / 注意点 |
| --- | --- |
| `src/ainiee_translate/cache_io.py` | `load_cache`、`index_items`、`locked`、`apply_writeback`；锁内结构检查、备份、保存；改译文会使 PDF target proof 失效 |
| `src/ainiee_translate/polish.py` | `write_polished(cache_path, polished, *, force=False, allow_tag_mismatch=False)`；必须保留现有行为 |
| `src/ainiee_translate/pdf_cache.py` | `unit_id/chapter_id`、`reconcile_cache`；原文修订后保留历史和定向失效 |
| `src/ainiee_translate/pdf_review.py` | `export_review_tasks(..., unit_ids=...)`、`import_review_results`、`build_translation_manifest`；独立上下文、原 PDF、原译哈希和证据检查 |
| `src/ainiee_translate/export.py` | `export_project`；PDF 源项目走 `--format epub`；普通 EPUB 项目当前走 `--format source`，不能给普通 EPUB 硬套 `--format epub` |
| `src/ainiee_translate/book_check.py` | `check_epub` 分开报告 structure 和 EPUBCheck；CLI 返回 0 不代表 EPUBCheck 已可用，需要读 JSON 状态 |
| `src/ainiee_translate/review.py` | 现有 Markdown 报告/pick 可参考，但 `final` 对 A/B 自动生成应用文件，不适合作为新流程的批准依据 |
| `src/ainiee_translate/_vendor/ModuleFolders/Domain/FileReader/EpubReader.py` | 普通 EPUB 缓存有 `extra.item_id/original_html`，没有可直接等同微信章节 UID 的键 |
| `src/ainiee_translate/_vendor/ModuleFolders/Domain/FileOutputer/EpubWriter.py` | 导出会转换强调与 HTML；定位应检查实际 EPUB，而非直接以 translated_text 字符偏移当微信 range |
| `build.py`、`pyproject.toml` | canonical src → bundle；现有 `*.html/assets/*.css` package data 已有支持 |

### 本地运行目录和共享契约

用户书籍默认放在忽略的 `local/reading-projects/<book>/`。下面的 `$ROUND` 指其 `work/reading/R0001/`，绝不能把真实文件复制到测试夹具：

```text
edition/reading.epub, cache.frozen.json, source-manifest.json, segments.json
round.json                         # round 身份、bookId、style profile、完成状态
snapshots/<snapshot-id>.json        # 原始响应 + 请求参数（剔除鉴权）+ 完整性
issues.json                        # 稳定编号、标注版本、匹配、当前状态、历史引用
tasks/<revision>.json               # agent 辨析任务
assessments/<revision>.json         # agent 结构化结果和证据
reports/<report-revision>.html      # 永久保留曾展示的报告
decisions/<decision-id>.json        # 聊天批复绑定的确切版本和文本
transactions/<transaction-id>.json # 应用/撤回事务与恢复依据
checks/, final/                    # 内部检查和通过后整本成品
```

新增 JSON 采用 schema 字段版本化，具体必需字段依 Spec §4。类型统一使用普通 JSON-compatible `dict/list`，避免本功能为数据载体新增运行依赖。所有模块使用下列一致接口；若确需调整，同时修正文档、调用者和测试。

## Task 0: 官方能力最小实测与接入闸门

**Files:** 新建 `docs/weread-validation.md`（无私人内容结论）；真实证据位于 `local/weread-validation/`；合成契约夹具在 Task 2 创建。

**Interfaces:** 在 `local/weread-validation/capabilities.json` 产出 capability profile：官方 skill 来源/版本、可用接口、导入书 bookId 识别方法、style 的原始 JSON 值、分页/快照完整性、关联和 range 的已知边界。至少含 `schema=weread-capabilities/1, verified, blue_wave_style, deletion_semantics_verified, evidence_reference`，blue_wave_style 保留原始 JSON 类型。未验证字段明确 `unverified`，而非假设成功。

- [ ] 读官方 README、SKILL、notes、shelf；记录来源和日期。安装需要时使用 skill-installer 工作流，先查已安装副本；不替换 AiNiee 全局副本。账号 Key 由本机环境提供，日志不打印鉴权；缺少 Key 时仅请求本地配置，不要求在聊天贴密钥。
- [ ] 准备自造短 EPUB：重复句、两个同名章节、跨段选择、强调、空白差异、emoji、公式/脚注。用户手动导入并依次创建：蓝色有想法、蓝色无想法、其他颜色、同划线多条想法、编辑及删除样本。先获取初始快照，再编辑/删除后取第二次快照。
- [ ] 通过书架绑定实际导入书，对该书同时读取划线和全部个人想法页。对每个手工样本核对返回摘录、样式、ID 及关联；对完整性不能确认的响应标记 unknown。
- [ ] 在本地保存响应和对照记录，仅将无私人信息的观察、脱敏字段类型和失败原因写入验收摘要。没有实测则写明未通过；不提交真实书名/想法/截图。
- [ ] 若蓝色筛选或导入书不可用，停止宣称集成可用；可以继续独立的离线任务，替代用户习惯需要新的产品决策。
- [ ] 检查摘要无账号内容后提交：`docs: record WeRead capability validation`。后续补实测可另提交；本任务未通过时最终真实验收保持未完成。

## Task 1: 冻结阅读版本与可验证原译索引

**Files:** 新建 `src/ainiee_translate/reading_round.py`、`测试/单元/test_reading_round.py`；在 `src/ainiee_translate/artifact_io.py` 增加共享文本哈希函数；新建合成 EPUB 夹具构造器 `测试/夹具/reading_sample.py`。

**Interfaces:**

```python
def text_sha256(text: str) -> str: ...
def freeze_round(cache_path: Path, epub_path: Path, source_path: Path, *, storage_path: str, round_dir: Path, glossary_path: Path, prompt_path: Path) -> dict: ...
def load_round(round_dir: Path) -> dict: ...
def load_segments(round_dir: Path) -> list[dict]: ...
```

text_sha256 定义在 artifact_io.py，reading_round 与后续 cache_io 均从该基础模块引用，避免缓存层反向导入阅读业务模块。

- [ ] 先写失败测试 `test_freeze_preserves_exact_epub_and_cache`：冻结后更改工作稿，reading.epub 和 frozen cache 字节及其哈希不变；已有 round 不能覆盖。`test_wrong_epub_or_book_rejected`：不同书、错误 storage、缺失/空译正文、同源但不同译稿均不能静默绑定。
- [ ] 增加 `test_epub_spine_and_duplicate_paragraphs`、`test_pdf_unit_ids_retained`：记录实际 spine/href 与原译缓存关系；相同句保留多候选；PDF 保留稳定 unit_id/provenance；排除项保持原项目政策，不假装翻译过。
- [ ] 运行 `python -m pytest 测试/单元/test_reading_round.py`，确认因未实现接口而失败。
- [ ] 实现冻结、内容核对和索引；普通 EPUB 解析 OPF/spine 与真实输出 XHTML，将 cache item 的 item_id/原 HTML 和完整译文用于候选验证；不靠 reader 遍历顺序猜 spine。PDF 使用既有 book 与 unit provenance。无法唯一绑定的段保留歧义，完全不对应的 EPUB 拒绝。所有相对路径限制在已选 round/project 内。
- [ ] 重跑该文件通过；提交 `feat: freeze proofreading reading editions`。

## Task 2: 只读快照、蓝色筛选与增量历史

**Files:** 新建 `src/ainiee_translate/weread_client.py`、`weread_notes.py`；测试 `测试/单元/test_weread_client.py`、`test_weread_notes.py`；合成响应放 `测试/夹具/weread/`。

**Interfaces:**

```python
def fetch_snapshot(*, api_key: str, book_id: str, skill_version: str, transport=None) -> dict: ...
def normalize_snapshot(snapshot: dict, *, style_profile: dict) -> dict: ...
def merge_snapshot(round_dir: Path, normalized: dict) -> dict: ...
```

`fetch_snapshot` 用可注入 transport；保存数据不含 api_key/Header。规范化返回 notes（外部 IDs、原摘录、所有关联想法、样式及原始位置）和 completeness。`merge_snapshot` 在 round 锁下分配稳定编号，返回更新后的 issues。

- [ ] 失败测试：`test_gateway_flat_body_and_version`（端点参数大小写按官方契约、顶层平铺）；`test_reviews_all_pages_and_cursor_stall`（hasMore 时跟随 synckey，游标不推进则报错）；`test_key_never_serialized`；`test_api_error_or_upgrade_not_complete_snapshot`（errcode/升级提示均不得记为成功全量同步，升级先核实官方来源）。
- [ ] 失败测试：`test_blue_style_requires_verified_profile`、`test_blue_without_thought_is_issue`、`test_other_colors_excluded`、`test_ambiguous_thought_link_retained`。关联先同书同章和已验证 range，再核对摘录；未知或多候选保留待关联，绝不按创建时间就近配对。
- [ ] 失败测试：`test_repeat_sync_keeps_ids`、`test_edit_reopens_without_reusing_approval`、`test_partial_snapshot_does_not_delete`、`test_confirmed_delete_does_not_undo_applied_edit`。想法顺序变化本身不算文字修订；同记录重试不增编号。
- [ ] 运行两个测试文件确认红灯；实现三个接口，加入超时、有限重试和错误归类；快照成功写入后才更新 issues。缺少 completeness 证据时所有消失仅为 missing_unconfirmed。
- [ ] 重跑通过；提交 `feat: import versioned WeRead proofreading notes`。

## Task 3: 原译定位与上下文任务

**Files:** 新建 `src/ainiee_translate/reading_match.py`、`reading_review.py`；测试 `测试/单元/test_reading_match.py`、`test_reading_review.py`。

**Interfaces:**

```python
def match_issues(round_dir: Path) -> dict: ...
def record_match_override(round_dir: Path, mapping: dict) -> dict: ...
def export_assessment_tasks(round_dir: Path, cache_path: Path, *, issue_ids: list[str] | None = None) -> dict: ...
def import_assessments(round_dir: Path, results: dict) -> dict: ...
```

- [ ] 失败测试 `test_duplicate_text_remains_ambiguous`、`test_cross_paragraph_match_keeps_each_segment`、`test_unicode_offsets_are_local_and_reversible`：把微信 range 当不透明辅助值；HTML 实体、NBSP、emoji、强调去标记后仍能还原选区到精确本地文本；不采用未核实的 UTF-16/字节偏移假设。首版仅做解实体、Unicode NFC、空白折叠及可追溯偏移映射，不做简繁转换或语义模糊自动定址。
- [ ] 失败测试 `test_round_edition_not_current_cache_used_for_selection`：初始匹配用冻结 EPUB；评估同时带冻结所选文字与当前工作稿，不能因工作稿已改而丢失旧标注。
- [ ] 失败测试 `test_explicit_location_override_validates_edition`：mapping 必须含 issue_id、annotation_revision、edition_id、逐段范围、actor、evidence；范围必须落在冻结文本且与摘录相符。可记录补充上下文形成的定位证据或用户对候选位置的明确选择，过期映射拒绝；不能由操作者字符串本身替代位置证据。
- [ ] 失败测试 `test_expanded_findings_have_independent_ids`、`test_unknown_source_does_not_get_fake_pdf_evidence`：扩展发现按位置单独编号并关联 parent，重复扫描不重复建条；普通 EPUB 给源 XHTML 引用，PDF 给真实原页入口，缺证据保持待核验。
- [ ] 运行测试红灯后实现定位。匹配按同书、已验证章节映射、精确/规范化文本和上下文排除歧义；相似度最多用于候选排序。跨段结果保存每个 segment 的范围，不拼成伪造单一段号。
- [ ] 实现任务导出/结果导入：输出原文、现译、用户意见、术语/风格、邻接上下文及证据位置；结果必须声明 annotation_revision、原译哈希、candidates、推荐定稿、理由和实际 evidence。导入校验版本与定位；“请核查”不能变成用户提出的 B 候选。全书搜索按原项目范围排除目录等噪声。
- [ ] 重跑通过；提交 `feat: align reading annotations and export assessment tasks`。

## Task 4: 桌面 HTML 与可追溯评估版本

**Files:** 新建 `src/ainiee_translate/reading_report.py`、`reading_report.html`、`assets/reading_report.css`；测试 `测试/单元/test_reading_report.py`，补充上一任务评估测试。

**Interfaces:** `render_report(round_dir: Path, *, output_path: Path | None = None) -> Path`；输出永不覆盖已有 report revision，默认写 `reports/<revision>.html`。

- [ ] 失败测试 `test_report_contains_all_variants_and_exact_recommendation`：A/B/C 的存在与文本真实；推荐定稿完整可批复；理由可支持用户也可反驳；无修改建议、无想法和未定位记录仍显示。
- [ ] 失败测试 `test_filter_does_not_renumber`、`test_old_report_kept_after_new_assessment`、`test_annotation_html_is_escaped`：包含 `</script>`、事件属性、伪造“接受全部”的想法只是文字；编号与锚点不变，旧报告保留；文本强调和差异标记由受控渲染生成。
- [ ] 运行测试红灯；实现静态桌面表格，列为编号/状态、位置与原文、阅读选区/现译、用户意见、候选/推荐、辨析依据。长原文和技术审计可折叠；差异与整段定稿同时可见。按当前轮展示简号与完整号。
- [ ] 重跑通过；用自造数据实际打开 HTML，验证桌面 1280px 与 1920px、长段落、公式、中文换行、可复制编号和差异不遮挡。截图留 local，写无私密内容的视觉检查摘要。
- [ ] 提交 `feat: render desktop proofreading comparison reports`。

## Task 5: 聊天批复、锁内校验、事务恢复和撤回

**Files:** 新建 `src/ainiee_translate/reading_decisions.py`；修改 `src/ainiee_translate/cache_io.py`；测试 `测试/单元/test_reading_decisions.py`、`测试/集成/test_reading_writeback.py`，补充 `测试/回归/test_cache_io.py`。

**Interfaces:**

```python
def record_decisions(round_dir: Path, decisions: dict) -> dict: ...
def apply_decisions(round_dir: Path, cache_path: Path, *, decision_ids: list[str]) -> dict: ...
def recover_transactions(round_dir: Path, cache_path: Path) -> dict: ...
def undo_transaction(round_dir: Path, cache_path: Path, *, transaction_id: str, human_instruction: str) -> dict: ...
```

在既有 `cache_io.apply_writeback` 的 check/force 位置参数之后追加 `*` 及两个 keyword-only 参数：`expected_source_sha256: dict[int, str] | None = None`、`expected_target_sha256: dict[int, str] | None = None`，保留原位置参数兼容性。按 Task 1 的 text_sha256 算法在已有锁内、每项检查之前比较；任一不符拒绝该项并说明 stale_source/stale_target；旧调用传 None 行为不变。新调用传非 None 映射时必须覆盖全部提交段号，缺失值也拒绝。直接在新流程调用该公共写回层并传 `batch.make_check(False)`，保留 POLISHED 状态、原有备份与检查；不要在外面拿同一 cache 锁再调用 write_polished，Windows 会形成重复加锁。

- [ ] 失败测试 `test_accept_uses_displayed_recommendation`、`test_choose_b_keep_defer_custom`、`test_discussion_without_human_instruction_is_not_approval`、`test_changed_assessment_rejects_old_approval`、`test_cross_round_short_number_rejected`。Decision 包含 decision_id、issue_id、action、report_revision、assessment_revision、annotation_revision、exact target、expected source/target hashes、human instruction/reference。
- [ ] 失败测试 `test_concurrent_writer_rejected_inside_lock`、`test_overlapping_same_segment_edits_do_not_overwrite`、`test_unrelated_decisions_can_apply_despite_conflict`；采用完整段候选时，一处已改使另一处旧全文候选过期，须重新辨析或明确组合批复。
- [ ] 失败测试 `test_retry_after_cache_write_recovers_once`、`test_recover_before_cache_write`、`test_undo_preserves_later_edits`：分别在 prepared、cache_written 后注入异常；恢复据前后哈希确认状态；第三种哈希转冲突。所有同段重复一致目标为幂等成功，无关段不回滚。
- [ ] 运行新测试确认红灯；实现 round→cache 的固定锁顺序、持久化事务、锁内 CAS、现有结构/标签检查、逐条结果记账；记录每条实际 applied/rejected/noop，不能把整批声明成功。写回后沿用 proof 失效机制。
- [ ] 运行新测试及 `测试/回归/test_cache_io.py`、`测试/回归/test_polish.py`，全通过后提交 `feat: apply chat proofreading decisions with revision guards`。

## Task 6: PDF 重新核验与整本最终交付

**Files:** 新建 `src/ainiee_translate/reading_finalization.py`；按需修改 `src/ainiee_translate/export.py`（仅新轮次集成入口）、`reading_review.py`；测试 `测试/集成/test_reading_pdf_evidence.py`、`test_reading_finalization.py`。

**Interfaces:**

```python
def finalization_status(round_dir: Path, cache_path: Path) -> dict: ...
def record_reading_completion(round_dir: Path, *, human_instruction: str, human_reference: str) -> dict: ...
def finalize_round(round_dir: Path, cache_path: Path, *, output_dir: Path, publication_context: dict) -> dict: ...
```

`finalization_status` 返回 blockers 和 changed PDF unit_ids，不输出阶段 EPUB。`finalize_round` 只在状态和证据通过后生成整本成品；历史初始 reading EPUB 保持不变。

- [ ] 失败测试 `test_changed_pdf_unit_requires_new_target_proof`：批准并写回后旧 proof 入历史、正式生成被拒；由独立上下文回看原页并通过 `pdf_review` 导入新目标 proof 后恢复可生成；未变单元有效 proof 保留。测试用明确 synthetic 证据，仅验证契约，不声称真人原页核验。
- [ ] 失败测试 `test_source_ocr_fix_reconciles_and_reopens_issues`：源文本/结构更正通过既有 reconcile，冻结 baseline 完整保留，依赖旧 source 的评估/批准失效；结构重映射不明转待定位。不能直接改 cache 源文蒙混过关。
- [ ] 失败测试 `test_whole_book_gate_has_no_stage_release`：待定位、搁置、过期、冲突、未执行批复、不完整最终同步或未恢复事务逐一阻塞；remote_deleted 与保留现译终态不误阻塞；仍有未决时 final 目录无可交付新书。
- [ ] 失败测试 `test_epubcheck_unavailable_is_not_final_pass`、`test_pdf_export_uses_same_final_cache`：内部暂存可留检查物，完成状态仅在 structure 与 EPUBCheck 都 passed 后写入；只输出项目明确请求的 PDF 模板且真实编译/检查，不能交付旧残留。
- [ ] 失败测试 `test_sync_during_finalization_blocks_delivery`：暂存构建期间新快照或批复改变本轮状态，交付前再次检查并阻止旧 revision 成品进入 final。用户整本阅读确认有原话与出处，不能从进度或空字符串伪造。
- [ ] 运行红灯；实现状态聚合及现有 export/manifest/check 编排。独立 PDF 原页复核是 agent 的实质工作，脚本校验提交的证据，不生成自称“看过原页”的假记录。用户明确读完整书后，记录其原话并完成最终完整同步；微信 progress=100 不能代替这一确认。
- [ ] 重跑新测试及 PDF lifecycle 回归通过；提交 `feat: finalize whole-book proofreading with publication evidence`。

## Task 7: CLI、skill 路由、打包和综合验收

**Files:** 新建 `src/ainiee_translate/reading.py`、`skills/ainiee-translate/references/weread_proofreading.md`、`commands/reading-review.md`；修改 `skills/ainiee-translate/SKILL.md`、`commands/menu.md`、`README.md`、`.env.example`；测试 `测试/集成/test_reading_workflow.py`；运行 build 生成 bundle。按最终实际结果更新 `docs/weread-validation.md`。

**Interfaces:** `main(argv=None) -> int`。以下全部是待新增 CLI，不是基线现有命令：

```text
python -m ainiee_translate.reading freeze --cache <cache> --epub <epub> --source <source> --storage-path <book> --round <round> --glossary <locked> --prompt <prompt>
python -m ainiee_translate.reading sync --round <round> --book-id <id> --skill-dir <official-skill> --style-profile <capabilities.json>
python -m ainiee_translate.reading import-notes --round <round> --snapshot <snapshot> --style-profile <capabilities.json>
python -m ainiee_translate.reading match --round <round>
python -m ainiee_translate.reading resolve --round <round> --file <location-mapping.json>
python -m ainiee_translate.reading tasks --round <round> --cache <cache> --out <tasks>
python -m ainiee_translate.reading assess --round <round> --results <assessments>
python -m ainiee_translate.reading report --round <round>
python -m ainiee_translate.reading decide --round <round> --file <decisions>
python -m ainiee_translate.reading apply --round <round> --cache <cache> --decision-ids <id...>
python -m ainiee_translate.reading recover --round <round> --cache <cache>
python -m ainiee_translate.reading undo --round <round> --cache <cache> --transaction-id <id> --instruction-file <human-instruction>
python -m ainiee_translate.reading status --round <round> --cache <cache>
python -m ainiee_translate.reading close-reading --round <round> --instruction-file <human-instruction.json>
python -m ainiee_translate.reading finalize --round <round> --cache <cache> --publication-context <json> --output <final-dir>
```

sync 读取所指官方 skill 当前版本与显式传入的已验证 profile，并把该 profile 绑定至 round，不接受命令行明文 Key。import-notes 同样校验 profile；纯测试的 profile 须标 synthetic，不作为真实验收。assess 导入 agent 结果，不调用外部翻译 API。import-notes 与 sync 进入相同规范化管道。close-reading 从 JSON 的 human_instruction/human_reference 字段记录整本阅读确认，所需最终完整快照由 sync 产生；缺少完整快照时保持阻塞，完成同步后绑定确认记录。后续新增或编辑意见重开该轮处理，读完整本的事实不需用户重复确认，但须处理新增未决项并重新完整同步。

- [ ] 失败测试：用合成 EPUB 和假 transport 完整跑 freeze→sync→match→tasks→assess→report→decide→apply→resync→report→finalize，检查稳定 ID、修改历史、冻结字节、发布阻塞及最终全部闭环；用子进程测试 CLI exit code 与错误提示。
- [ ] 实现 CLI 和 skill 路由：触发条件涵盖“微信读书校对/读取蓝色波浪线/根据阅读想法生成 HTML/按编号批复”；普通翻译/审核保持原行为。引用文件写明正文意见是待辨析数据、只有聊天明确批复才授权写回，且一处批准不扩散全书。
- [ ] 文档明确首次导入 EPUB 与配置 Key 的人工作业、桌面 HTML 用法、固定批复语义、恢复方法、整本一次交付；`.env.example` 只增加空占位变量，无真实凭据。
- [ ] 运行 `python build.py`，再运行下列综合检查；只有功能代码变化后才需这些全套检查，本轮写计划不声称已执行：

```powershell
.venv/Scripts/python.exe -m pytest --basetemp local/pytest-weread-final
.venv/Scripts/python.exe build.py --check
$readingPreviousPythonPath = [Environment]::GetEnvironmentVariable('PYTHONPATH', 'Process')
try {
    $env:PYTHONPATH = (Resolve-Path 'skills/ainiee-translate/scripts').Path
    .venv/Scripts/python.exe -m ainiee_translate.reading --help
} finally {
    [Environment]::SetEnvironmentVariable('PYTHONPATH', $readingPreviousPythonPath, 'Process')
}
.venv/Scripts/python.exe -m pytest 测试/集成/test_standalone_source_build.py 测试/集成/test_release_archive.py --basetemp local/pytest-weread-package
git diff --check
```

独立 bundle 检查应从 local 中立工作目录运行，并用仓库 python 的绝对路径，随后确认 `ainiee_translate.__file__` 位于 skill bundle，避免 editable 安装或当前 src 偶然遮蔽；上例演示环境变量的保存和恢复。若未修改 publisher，不另跑兄弟仓库全量测试。若修改了它则独立记录授权范围、Git 分支和验收，不把副本修改冒充 canonical 修改。

- [ ] 正式 EPUB 再用 `python -m ainiee_translate.book_check <final.epub> --report <checks.json>`，检查 JSON 两项均 passed；模板按实际请求编译并查看 PDF。缺外部检查工具写明受阻，不宣称正式完成。
- [ ] 回到 Task 0 的真实导入书跑一次完整人工样本链路，实际打开桌面 HTML，用聊天批复应用至少一处；确认非蓝色未混入、无想法蓝色在列、反驳/第三方案可见、编辑删除和重复同步不误写。真实记录留 local；通用夹具不能充当账号验收。
- [ ] 运行 `git diff --check`、人工检查 staged 文件范围与敏感内容，提交 `feat: integrate WeRead proofreading workflow into the skill`。本地构建测试不是 GitHub 发布许可，不 push/PR/Release。

## 需求覆盖与交付清单

| 需求 | 任务 |
| --- | --- |
| R01/R02 | Task 1、3、6 |
| R03/R11 | Task 0、2、3 |
| R04/R05 | Task 3、4、7 |
| R06/R08 | Task 3、4、5 |
| R07 | Task 3、6 |
| R09/R10 | Task 4、5、7 |
| R12 | Task 6、7 |

- [ ] 所有 R01—R12 均有对应测试和实际结果；全文不存在阶段版交付分支。
- [ ] 新模块源码、skill bundle、入口、文档和包装一致；旧翻译与审核回归通过。
- [ ] `docs/weread-validation.md` 区分自动测试、合成样本、真实账号、HTML 视觉检查、正式 EPUBCheck 及模板编译结果；记录实际命令、退出码、失败/skip 原因和本地证据索引。
- [ ] 最终接手报告给出分支/commit、完成任务、未决事实、下一条可执行命令；未测能力明确标未测，不借用历史报告。

## 本次计划交付检查（2026-10-18）

已核对 R01—R12 覆盖、Task 0—7 依赖、既有接入文件和测试入口、Markdown 本地链接、代码围栏、UTF-8 读取及提交范围。本次只改 README、Spec 与计划三份文档；实施任务的复选框全部保留未完成。功能测试、账号连接、正式 EPUBCheck 与模板编译均留给实施验收，不能把文档检查通过解释为功能通过。

## 给下一个 agent 的启动提示词

> 在本工作区的 `development/ainiee-translate-skill` 仓库接手微信读书人工校对功能。先读上层 AGENTS.md、`docs/superpowers/specs/2026-10-18-weread-proofreading-design.md` 和本计划，再检查 Git 状态与当前提交。按 Task 0—7 实施，每项记录实际验证并提交本地 Git；先验证官方接口对自导入 EPUB、蓝色波浪线和想法的支持。用户已确认：每轮冻结 EPUB，电脑 HTML 稳定编号，聊天逐条批复，允许 AI 反驳/第三方案，明确批复分批写回，整本校对完成才统一交付。PDF 改译后须更新独立原页校对证据。已有访问凭据从本地环境读取；需要人工作业时集中说明并继续不依赖它的离线工作。真实证据保存在本工作区的忽略目录，缺少真实验证不得宣称端到端通过。保持原有翻译功能和全局 skill 安装；本任务不授权 push、PR 或远端发布。实施范围以我发给你的本条接手指令为准。
