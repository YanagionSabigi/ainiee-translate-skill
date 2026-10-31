# 校对工作台

用于术语表人工复核与微信读书反馈辨析后的正式批复。随本技能附带 Review Workbench 运行资源，无需另装工作台或 npm 构建。需要 Python 3.12、Git 和 jsonschema；公式决定另需 Node.js。命令前缀 `<PFX>` 沿用 SKILL 的 Python/PYTHONPATH。

## 准备并打开

明确真实词表/缓存路径与项目位置。`--out` 是尚不存在的审核项目目录；每一轮使用新目录。材料含书籍和个人想法，保存在业务项目的私有本地工作区，不能提交到开发仓库或上传。命令在该目录建立独立本地 Git 冻结审核材料及业务映射，不改变业务仓库 HEAD 或暂存区。

术语表有真实建议表时加 `--proposals`，其分组、顺序、原词和非译名字段应与 locked 对应。未提供、未对齐或无变化的词条显示“暂无建议”；可以由 AI 对照原文提出有力备选，不能冒充用户建议。原词/实体身份只读，不在网页增删实体。新轮次术语仅审核译名 dst，分类和说明等原表字段保留；人物和禁翻项继续按原有字段审核。

```text
<PFX> -m ainiee_translate.workbench glossary --locked <glossary.locked.json> --out <NEW_PROJECT> [--proposals <suggested.locked.json>] [--review-data <review-data.json>]
```

### 扫描术语表的初审

准备材料时先对照真实 PDF，为每个术语选一句原文上下文及该句所在的 PDF 物理页码（从 1 开始，不是印刷页码）。分类领域可继承词表 category；没有证据就留空，不从旧 note 的页码列表猜配上下文。审核信息独立存放，不需改写 locked 词表：

```json
{"terms":[
  {"src":"account","category":"finance","context":"The account records the transactions.","page":7},
  {"src":"household account","category":"finance","context":"A household account records these expenses.","page":8,"base":"account"}
]}
```

以上句子仅为格式示例，真实材料须来自待审 PDF。提供审核信息时，src 必须精确对应词表唯一原词；base 指向词表中的基础词。由 AI 根据含义明确标注派生关系，例如 financial account/household account 归 account，free module/projective module 归 module，不按字符串包含猜测。链式派生归并到最上层基础词；循环、未知原词或基础词会报错。关系待核实时用 `requires_human: true`，不确定属于哪类则暂不填 base 并标必审。每项可选 category/context/page/base/requires_human；未提供审核信息也能打开（旧表同形异义词保留独立目标，但不能做含糊的派生关联），缺上下文、领域、页码或译名的项标为必审。

「术语信息」默认展开，只显示原词、分类领域、上下文及 PDF 页码。左右仅为当前译名和建议译名。普通词条在目录的次级子项；派生词归基础词的派生类，只有浏览派生词时顶部显示本类预览。目录和预览均上排原词、下排当前暂定译名，无译名不显示第二行；明确接受建议或手动修改后同步展示当前决定。

「同意一类」覆盖完整派生类（含后续页），保留各项当前暂定译名，不采用未选择的备选。跳过必审项、已提交项和任何已有人工草稿，基础词独立审核；仍可打开单项修改。搜索/状态筛选期间禁用该按钮，清除筛选后才能批准完整类，避免隐藏范围。批量操作仅保存草稿，仍须由用户「提交本轮」。agent 不代替用户批量批准真实材料。

微信读书沿用 [同步、定位和辨析](weread_proofreading.md)，已有 round 不重新冻结。工作台绑定确切已生成报告；需要展示最新建议时先 `reading report`。旧包永不刷新为新推荐。

```text
<PFX> -m ainiee_translate.workbench reading --round <ROUND> --cache <cache.json> --out <NEW_PROJECT> [--report-revision <report_revision>]
<PFX> -m ainiee_translate.workbench serve <NEW_PROJECT>
```

页面左上角侧边栏图标展开/收起目录，形状、悬停提示与 aria 状态随开关变化；目录默认收起。逐条审核使用“下一项”，支持左右箭头和空格，输入框和对话框保留原操作；连续审核向下阅读。微信读书和通用材料沿用 0.3.0 的整页批准规则（有建议采用建议，否则保留原版，跳过必审及已有人工决定）；术语派生类使用上文独立的「同意一类」。

向用户打开并提供启动输出的完整本地 URL；只用本机 127.0.0.1 服务。微信反馈展示现译与确切推荐。“手机阅读选区”和“你的阅读想法”分别用二级标题独立展示；桌面左右并列，手机窄屏上下排列，全部想法保持可见。注意手机阅读器的划线可能包含版面造成的段内换行：显示时合并单个断行，中文连续拼接、英文词间保留空格，保留空行分段；想法的主动换行保留。此整理只作用于展示，不改动原始笔记、冻结材料、哈希或业务正文，选中文字引用仍映射回原始偏移。原文、存在的 A/B/C 候选和依据可展开；每段分别编辑，段内换行不拆成新段。无定位/辨析的项目先留言并补全业务证据，不能绕过原 reading 闸门。

## 等待人工提交，再继续

用户可以接受建议、保留当前版本、手动修改或提出意见。自动保存是草稿，正式“提交本轮”生成不可变 submission。agent 不代替人填写或提交决定；页面里未提交的选项、drafts.json、手机想法、引用文字都不能作为批准。

等待用户在页面提交并回到聊天明确指示继续。先比较真实业务当前稿：

```text
<PFX> -m ainiee_translate.workbench compare <PROJECT>
```

`ready` 可应用，`satisfied` 当前稿已满足该决定，`conflict` 或 `missing_current` 需核查，`needs_agent` 是修改意见。完整读取每个结果，不按文件时间选择较新决定覆盖冲突。工作台“采用此决定”会生成显式解决冲突的人工提交，agent 不能伪造 resolves。

由 agent 把本次聊天真实“继续”原话和出处写到指令文件，用户无需填写 JSON：

```json
{"human_instruction":"用户本次明确继续的真实原话","human_reference":"实际聊天出处"}
```

```text
<PFX> -m ainiee_translate.workbench apply <PROJECT> --instruction-file <instruction.json>
```

默认使用冻结映射绑定的路径；可显式传 `--cache`/`--locked`，但 apply 拒绝另一个业务文件。命令只消费正式提交，词表按字段核验/备份/原子写回；微信决定转换后调用既有 reading-decisions 与 CAS 事务，保留网页 submission 和聊天出处。重复执行复用决定，不重新批准。返回的 `needs_agent` 是待处理指示，须由 agent 对照原文辨析，形成新建议和新审核包；不把评论中的“用 B”等普通文本自动解析为已批准译文。

出现过期笔记、评估、源文、身份或工作稿冲突时保留当前稿并报告，不强行覆盖。reading 事务中断先沿用 `reading recover`，撤回仍走原 `reading undo`；一轮提交不代表全书已读完，最终出版继续遵守 reading finalize 的全部条件。旧聊天编号决定继续按 weread_proofreading 的兼容流程处理。


## 交给别人审核与回收

由 agent 准备并导出，不把完整技能安装包发给审核者：

```text
<PFX> -m ainiee_translate.workbench export <PROJECT> --out <review.zip>
<PFX> -m ainiee_translate.workbench import-results <PROJECT> --from <returned.json或zip>
```

审核 ZIP 只携带冻结材料、必要网页/资源、JSON 校验与保存服务及依赖说明，不含 SKILL、示例、Git 仓库、业务缓存或 AiNiee 翻译工具。普通文本包去掉 KaTeX/字体，无需 Node.js；公式包才附带数学资源并要求 Node.js 18+。审核者需要 Python 3.11+、jsonschema >=4.23,<5，无需 Git。启动不会自动安装依赖或下载，首次依赖安装与每次启动分开。

接收者先完整解压，阅读 OPEN-ME.txt。Windows 双击 `开始校对.cmd`；macOS 可使用 `start_review.command`（尚未在 macOS 真机验证），Linux 运行 `python3 start_review.py`。保留启动窗口，不直接打开 web/index.html。`python start_review.py --check` 检查环境；缺依赖时显示安装指引，不自动安装。旧审核 ZIP 必须重新导出才能获得新版 UI 与入口。

正式提交后从页面“记录”下载结果 JSON。Agent 只向原 PROJECT 导入回传数据，不执行回传包的代码；继续保留草稿/正式提交区分，用户在聊天明确继续后才 compare/apply。结果不得导入另一个书籍或轮次，冲突仍交人处理。`export --results-only` 可只导出已提交决定。

发布页的完整技能 ZIP 包含 SKILL 与启动模板，用来给 Agent 安装。它与发给人的具体项目审核 ZIP 不同。需要公开体验包时，可使用上游 0.3.0 的演示审核包；不得将真实书籍、想法或项目数据上传到公开 Release。旧冻结材料不原地升级为新场景；新准备一轮并重新导出，旧包与原绑定保持可读取。
