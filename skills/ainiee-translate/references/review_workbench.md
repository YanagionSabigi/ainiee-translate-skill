# 校对工作台

用于术语表人工复核与微信读书反馈辨析后的正式批复。随本技能附带 Review Workbench 运行资源，无需另装工作台或 npm 构建。需要 Python 3.12、Git 和 jsonschema；公式决定另需 Node.js。命令前缀 `<PFX>` 沿用 SKILL 的 Python/PYTHONPATH。

## 准备并打开

明确真实词表/缓存路径与项目位置。`--out` 是尚不存在的审核项目目录；每一轮使用新目录。材料含书籍和个人想法，保存在业务项目的私有本地工作区，不能提交到开发仓库或上传。命令在该目录建立独立本地 Git 冻结审核材料及业务映射，不改变业务仓库 HEAD 或暂存区。

术语表有真实建议表时加 `--proposals`，其分组、顺序和原词应与 locked 对应。未提供、未对齐或无变化的词条显示“暂无建议”；不要编造用户建议。原词/实体身份只读，首版不在网页增删实体。分类、说明、人物别名等字段按原表显示，别名每行一项，保留原文字段使用“是/否”。

```text
<PFX> -m ainiee_translate.workbench glossary --locked <glossary.locked.json> --out <NEW_PROJECT> [--proposals <suggested.locked.json>]
```

微信读书沿用 [同步、定位和辨析](weread_proofreading.md)，已有 round 不重新冻结。工作台绑定确切已生成报告；需要展示最新建议时先 `reading report`。旧包永不刷新为新推荐。

```text
<PFX> -m ainiee_translate.workbench reading --round <ROUND> --cache <cache.json> --out <NEW_PROJECT> [--report-revision <report_revision>]
<PFX> -m ainiee_translate.workbench serve <NEW_PROJECT>
```

页面左上角侧边栏图标展开/收起目录，悬停提示与 aria 状态随开关变化；目录和条目列表默认收起，按需展开。逐条审核使用“下一项”，连续审核向下阅读。

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

发布页的完整技能 ZIP 包含 SKILL 与启动模板，用来给 Agent 安装。它与发给人的具体项目审核 ZIP 不同。需要公开体验包时，可使用上游 0.2.0 的演示审核包；不得将真实书籍、想法或项目数据上传到公开 Release。
