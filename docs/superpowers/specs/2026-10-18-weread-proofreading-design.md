# 微信读书人工校对：已确认需求与设计

日期：2026-10-18（Asia/Shanghai）。状态：需求访谈已完成；本文件与配套实施计划供下一个 agent 接手，尚未实施或完成账号实测。

实施入口：[实施与交接计划](../plans/2026-10-18-weread-proofreading.md)。本文件是产品需求的唯一依据；计划中的模块、文件名和 CLI 是待实现的工程设计。

## 1. 用户目标

用户在手机微信读书中阅读 AiNiee 翻译的 EPUB，以蓝色波浪线标记待校对文字，在划线处直接写“想法”表达修改意见。阅读整本书后，由 agent 拉取标注、定位译稿、对照原文并生成桌面 HTML 表格。用户在电脑阅读表格，再在 agent 聊天中按稳定编号批复。修改分批写入工作稿，整本书处理完才统一生成最终成品。

此流程接入现有 ainiee-translate skill，agent 本身完成翻译辨析，Python 负责同步、定位、证据校验、报告和受控写回。

## 2. 用户已确认的要求

| ID | 约束 | 验收结果 |
| --- | --- | --- |
| R01 | 微信读书中的校对文件统一 EPUB；源书可以是 EPUB 或 PDF | 两类源书均能回到原文；PDF 仅作为可选排版成品，不是本流程的阅读标注介质 |
| R02 | 每轮冻结一个阅读版本 | 精确保存阅读 EPUB、原译快照、身份及哈希；后续写回不改变阅读基线 |
| R03 | 蓝色波浪线是校对标记；直接在划线处写想法，允许自然语言 | 其他颜色不混入校对条目；蓝色波浪线无想法也收录，解释为“请核查此处” |
| R04 | AI 可以反驳用户意见，也可以提出第三种译法 | HTML 完整展示现译、用户方案（若有）、AI 方案（若有）、推荐定稿、判断依据和不确定之处 |
| R05 | HTML 面向电脑；稳定编号；聊天批复 | 支持桌面宽表、展开上下文、差异高亮；首版不开发手机适配或网页批复后端 |
| R06 | 可检查整段、必要上下文及全书同类问题 | 扩展发现另编号并关联起因；接受一处不代表全书替换；普通阅读笔记不变成自动修改指令 |
| R07 | PDF 来源的每条辨析须核验对应原页 | 记录实际原页证据、物理页码及可用的印刷页码；OCR/公式/脚注问题独立说明；修改定稿后重新取得有效出版校对证据 |
| R08 | 定位失败不阻塞其他条目 | 待定位条目也有编号，显示摘录、想法和候选位置；不能凭最高相似度猜定一个位置 |
| R09 | 聊天批复含义固定 | “接受 7”采用所展示的推荐定稿；“7 用 B”采用 B；“保留 7”保留现译并关闭；“搁置 7”仍未决；“7 改为……”采用用户定稿 |
| R10 | 明确批复后分批写回工作稿；轮末统一导出；可追溯、可撤回 | 讨论不算批准；变更有前后文本与版本；撤回按当前版本校验，不能整份旧缓存覆盖后续修改 |
| R11 | 重复同步保存历史并沿用编号 | 新增追加编号；修改标注或想法后重新辨析，旧批复保留但不套用到新意见；删除只标记，不自动撤销已应用修改 |
| R12 | 整本书校对结束后一次发布，不需要阶段版 | 待定位、搁置、过期、冲突及待执行条目均清零；批准修改全部应用并通过原有出版检查，才生成本轮最终成品；允许保存中间 HTML、工作缓存和检查用临时产物，不能把它们当成阶段版交付 |

“发布”在此指生成并交付整本书的本地最终成品。上传微信读书、推送 Git、GitHub Release、PR、替换全局 skill 均不由这个词自动授权。

## 3. 可行性证据与实测缺口

核查日期为 2026-10-18。以下是官方公开文档的能力，尚不是本账号实测结论：

- [官方 SKILL](https://github.com/Tencent/WeChatReading/blob/main/skills/SKILL.md)：统一网关为 `POST https://i.weread.qq.com/api/agent/gateway`，从环境读取 `WEREAD_API_KEY`，请求参数平铺并携带安装版本；本次读到顶部版本为 `1.0.5`，实施时重新确认，不把该值硬编码为永久常量。
- [笔记文档](https://github.com/Tencent/WeChatReading/blob/main/skills/notes.md)：`/book/bookmarklist` 提供划线 ID、摘录、章节、range、colorStyle；`/review/list/mine` 提供个人想法 ID、content 以及条件存在的 abstract/range/章节字段。两种接口须结合使用，不能只读取其中一种。
- [书架文档](https://github.com/Tencent/WeChatReading/blob/main/skills/shelf.md)：书架可列举导入书。自译书须从实际书架选择并绑定 bookId，不应按书名搜索到书城同名书后直接绑定。
- [官方 README](https://github.com/Tencent/WeChatReading)：提供 `npx skills add Tencent/WeChatReading -g` 和 API Key 配置说明。当前公开能力未提供导入本地译书的接口，用户手动导入 EPUB。

必须先验证的事实：

1. 自行导入 EPUB 的蓝色波浪线和私有想法，能否经官方接口完整返回。
2. 蓝色波浪线的真实 `colorStyle` 值及类型；未知样式不得按经验猜测。
3. “想法”与划线的关联方式；文档没有给两者提供必然存在的共同 bookmarkId 外键。
4. `range` 的计数和章节分割语义，跨段、emoji、标点及空白对定位的影响；未验证前仅作辅助证据。
5. 划线列表是完整快照还是增量结果，如何确认删除；请求失败、分页未完成或语义未知时不得把“未出现”认定为删除。
6. 同一划线的修改、删除及重新创建是否保留 ID，想法是否独立更换 ID。

缺少账号或样本时可以实现合成数据离线链路；真实端到端验收保持未通过。接口若不支持本用法，记录实测证据并就替代标记方式重新与用户决策，不能悄悄更换蓝色波浪线规则。

## 4. 数据与状态约定

以下 schema 名称及顶层字段由本计划固定，模块间使用一致拼写；每个文件另有 `created_at`（含时区的 ISO 8601）与 `project_id/round_id`。历史 JSON 文件不可就地覆盖，当前 round/issues 物化视图可以在锁内原子更新。

| schema | 必需顶层字段（除公共字段） |
| --- | --- |
| `reading-round/1` | `edition_id, storage_path, book_id, style_profile, reading_completion, last_complete_snapshot_id, next_issue_number`；未绑定字段为 null，未绑定时相应操作拒绝执行 |
| `reading-edition/1` | `epub_sha256, cache_sha256, source_sha256, glossary_sha256, prompt_sha256, source_path` |
| `reading-segments/1` | `segments`；每项含 `segment_id, text_index, storage_path, source_text, target_text, source_text_sha256, target_text_sha256, locators`；PDF 项另有 `document_id, unit_id, provenance` |
| `weread-snapshot/1` | `snapshot_id, book_id, skill_version, requests, responses, completeness`；completeness 含 `reviews_complete, highlights_complete, deletion_semantics_verified` 布尔值 |
| `reading-issues/1` | `issues`；每项含 `issue_id, external_key, annotation_revision, status, note, matching, current_assessment_revision, history`；扩展发现另含 `origin_issue_id` |
| `reading-assessment-tasks/1` | `task_revision, issues, prompt_sha256, glossary_sha256`；任务项包含输入标注版本、原译文本/哈希、定位与必要上下文 |
| `reading-assessments/1` | `assessment_revision, task_revision, issues`；每项含 `issue_id, annotation_revision, segments, candidates, recommended_candidate, recommended_text, rationale, uncertainties, evidence` |
| `reading-decisions/1` | `decisions`；每项含 `decision_id, issue_id, action, report_revision, assessment_revision, annotation_revision, selected_text, expected_segments, human_instruction, human_reference` |
| `reading-transaction/1` | `transaction_id, decision_ids, action, state, segments`；段项含 text_index、前后文本及哈希、逐项结果；state 为 prepared/cache_written/committed/conflict |

`load_segments` 返回 reading-segments/1 的 segments 数组，其他载入函数返回完整对象。候选均为 `{label, text, edits}`；跨段时 edits 是逐段完整替换 `{segment_id, replacement_text}`，text 是供用户阅读的组合显示文本。selected_text 记录用户所见定稿，expected_segments 保存原文/当前译文哈希及逐段精确替换，不把多个段号合为一次字符串替换。action 为 accept/candidate/keep/defer/custom；事务 action 为 apply/undo。表格保留原始状态值，HTML 使用对应中文名称。

### 4.1 阅读基线和身份

- 一个 round 只绑定一个本地书籍条目及一个微信 bookId；缓存包含多本书时显式选择 `storage_path`。
- `edition_id` 为上传的精确 EPUB 文件字节 SHA-256；`project_id` 沿用缓存工程身份，round 序号持久化分配。
- 冻结前验证 EPUB 与所选缓存的实际译文一致。记录 OPF/spine、章节标题、XHTML href、实际可见文本与缓存段落的可验证关联。重复段落保留多个候选，不伪造唯一对应。
- PDF 段落用 `document_id + unit_id`，普通 EPUB 用冻结版本内的 `storage_path + text_index` 定位；普通 EPUB 的 `extra.item_id/original_html` 仅作为映射证据。重新 parse 后的 text_index 不自动继承旧映射。
- 新层文本哈希统一为原始字符串 UTF-8 SHA-256，命名 `source_text_sha256/target_text_sha256`；现有 PDF contract 的摘要继续调用其既有函数，不能混用两套算法。

### 4.2 条目与同步

- 报告编号示例 `WR-R0001-000007`。聊天中的“7”仅在当前 round 明确时映射到该编号。跨轮有歧义时使用完整编号。
- 外部划线身份是 `(bookId, bookmarkId)`，想法身份是 `(bookId, reviewId)`；它们与人类编号分开保存。一个划线可关联多条想法，关联不明就保留候选关系并待确认。
- 首次分配后编号单调递增、永久保留；筛选、排序、报告重建、定位修正和同步均不重新编号。全书扩展发现同样分配编号，记录 `origin_issue_id` 与具体位置；重复扫描按同轮位置及问题键去重。
- 快照记录抓取时间、分页完成状态、已核实的完整性语义和内容哈希。仅在确认完整快照或显式删除证据后标为 `remote_deleted`；其余缺失为 `missing_unconfirmed`。
- 内容修订增加 `annotation_revision`，当前评估和未执行批复随之过期，历史永不覆盖。已写回的旧修改不会倒退，新的评估从当前工作稿形成候选。
- 无法关联到蓝色划线的想法留在同步审计中，必要时列入“待关联”；不自动当作蓝色标注。普通书评和其他颜色划线不进入校对处理队列。

### 4.3 辨析与报告

每条包括：稳定编号、状态、章节/原文位置、所选译文、当前工作译文、完整原文及必要上下文、用户想法、用户明确提出的替代文本、AI 理由、候选、推荐定稿、精确差异和证据。

候选标签为 A=保留所展示的当前工作译文，B=用户明确提出的方案，C=AI 替代方案。不存在 B/C 时明确缺省，不能把“这里不通顺”编造成用户方案；另存 `recommended_candidate` 和确切定稿文本。

每份 HTML 有 `report_revision`；每条评估有 `assessment_revision`、输入标注版本、原译哈希、候选文本和证据。更新推荐后保留旧报告，旧报告上的批准不自动转而批准新文本。

HTML 是离线静态文件，所有书籍、想法、引用及候选内容按数据转义，保留合法强调的显示效果但不执行其中的脚本/指令。使用本地 CSS，无网页批复服务。显示用户需要的书籍信息及页码；哈希和审计细节放在展开区。

### 4.4 聊天批复与应用

由 agent 理解聊天并生成结构化 Decision，不实现自由文本自动授权解析器。每条 Decision 必须绑定已展示的报告、条目及评估版本，并保存用户原话/可追溯聊天出处和确切选中文本。A/B/C 指的是该报告中的版本，不能指向随时变化的“最新建议”。

应用前在同一个缓存写锁内核验当前原文及译文哈希，再走已有结构、标签与保护标记闸门。保留 existing API 的缺省行为；新流程不使用 `--force` 或自动接受 A/B 类问题的旧 review 路径。

同一段有多个批准时，完全相同的修改可幂等去重；相互覆盖或依赖旧全文的修改列为冲突并重新辨析。首版不默默合并互相覆盖的候选。一次调用允许无关条目成功、冲突条目失败，逐条准确记账。

缓存写入和账本不是一个文件事务：应用使用持久化事务记录（prepared → cache_written → committed），恢复时用每段前后哈希核对，不能因崩溃重复应用或把未写入的条目标为成功。反向撤回也是版本校验的显式事务。

`保留` 与已经确认的 `remote_deleted` 可结束该条；删除不会撤销已应用修改。`搁置`、`待定位`、`待关联`、`missing_unconfirmed`、`待辨析`、`待批准`、`待执行`、`过期`、`冲突` 和恢复未完成的事务仍阻塞整轮最终发布。

issues.status 固定使用 `needs_link/needs_location/needs_assessment/needs_approval/deferred/approved_pending_apply/applied/kept/remote_deleted/missing_unconfirmed/stale/conflict/out_of_scope`。终态为 applied、kept、经完整性证据确认的 remote_deleted，以及实际改成其他颜色后保留历史的 out_of_scope；颜色改变不能被误称为删除。其他状态均未决，事务冲突即使尚未投影到条目也阻塞完成。定位补充必须记录当前标注版本、候选取舍的证据和操作者，不直接手改 JSON 绕过校验。

### 4.5 原页核验和最终生成

PDF 来源先对照真实原页完成辨析；这份判断只证明当时检查过的文本。工作稿变化后，沿用 `cache_io` 的旧 proof 失效机制，为所有受影响单元取得独立上下文、绑定最新目标文本的校对证据，其他单元有效记录保留。

若发现源文提取错误，复用既有源书修订、reconcile、局部重译和重审流程；保持本轮冻结资料，受影响条目转为过期待重审，不能只在缓存改 source_text。源结构变化无法唯一继承时进入待定位。

完成条件：用户明确整本阅读已结束，完成一次完整同步，全部适用条目有终态、应用事务完成、当前工作稿与证据一致、原有出版闸门通过。无需用微信阅读进度百分比代替用户确认。同步之后有新变化则重新打开本轮。

reading_completion 保存用户原话、聊天出处、确认时刻和完成同步后的 snapshot_id；最终生成读取其绑定的最新完整快照。生成开始时记录 round/issues revision，交付前在 round 锁内再次核对；期间发生同步或批复变化则暂存检查物，重新检查后才交付，不能发布漏掉新意见的成品。

本轮只在完成条件成立后交付新的完整 EPUB；用户原项目要求模板 PDF 时，使用同一最终译稿生成并核验模板成品。导出至内部暂存目录，EPUB 结构检查及正式 EPUBCheck 均通过后再交付；`unavailable` 不是 `passed`。模板只在原项目要求时生成，编译失败不能拿旧 PDF 充数。

## 5. 范围与工程默认值

以下是为实现上述要求选定的工程方案，不是新增用户偏好：

- WeRead 是可选集成，官方 skill 保持独立；AiNiee 新增只读网关适配和离线快照入口，使用标准库 HTTP，核心翻译安装不强制增加第三方网络依赖。
- 源码在 `src/ainiee_translate`；`skills/ainiee-translate/scripts/ainiee_translate` 由 `build.py` 生成。计划和开发都在现有本地仓库，不另建工作区根 Git 仓库，不自动同步 `development/public-fork` 或全局安装。
- 私人书籍、原始接口响应、想法、HTML、截图、凭据及工作账本放在忽略的 `local/` 下，或本工作区内用户指定的独立项目目录；Git 仅收通用源码、合成夹具和无私人内容的验收摘要。
- 本轮产物只是设计与计划。安装官方 skill、配置账号、真实接口测试、功能代码、上线和 PR 均未在本轮完成。下一个 agent 从计划 Task 0 开始，执行范围由其收到的用户指令决定。
