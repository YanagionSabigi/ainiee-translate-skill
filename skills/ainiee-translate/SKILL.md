---
name: ainiee-translate
description: Use when translating a novel, EPUB, TXT or PDF on the coding agent itself, resuming an AiNiee cache, exporting reviewed translations, reviewing terminology, or proofreading translations using 微信读书 highlights and reading thoughts through a local review workbench or numbered chat decisions.
metadata:
  version: "2.4.0"
---

# ainiee-translate 技能指南

## 总览

本技能让 **编码 agent 本身（Claude Code / Codex 等）** 充当翻译引擎，配合一组确定性 Python 管道脚本，把一本 epub/txt 小说**端到端翻译**：

```
parse → 构建锁定词汇表 → 逐章翻译（agent 按规则） → 写回缓存 → 导出成品
```

- Agent IS 翻译引擎：无需调用任何外部 API；翻译质量由 agent 按规则实时应用保证。
- **不限于中译**：支持任意源语言 → 目标语言（`{source_language}` 解析时自动检测、`{target_language}` 由用户指定）；本指南以中文为例，其他目标语言同理。
- 进度状态驱动（`translation_status`）：中断后重跑自动从首个未译段继续，天然可恢复。
- 每批写回前自动备份（时间戳）：`cache.json.bak.YYYYMMDD_HHMMSS`。

本技能自带管道脚本（`scripts/ainiee_translate/`），无需单独 `pip install` 本包；只需一个装了几个轻量库的 Python venv（见下）。

**校对入口：** 术语表人工复核、建议对照或网页审核，先读 [校对工作台](references/review_workbench.md)。微信读书划线/想法校对先读 [微信读书人工校对](references/weread_proofreading.md)，完成定位辨析后默认接入同一工作台。网页正式提交后，用户回到聊天明确说继续，才核验并受控写回；草稿、留言和手机想法不构成最终文本批准。旧静态报告和聊天按编号批复仍可用，整本结束后统一生成成品。

---

使用、制作或修改 LaTeX 模板时，必须先读取并遵循 [LaTeX 写作规则](rule/LaTeX 写作规则.md)，包括后端代码、标点、空格和数学排版规范。

## 前置依赖与安装（重要）

`parse`/`export` 的轻量格式随技能打包在 `scripts/ainiee_translate/_vendor/` 下（改写自 AiNiee、剥离其 App 框架），无需克隆 AiNiee App。自带 epub/txt/md/docx/xlsx/pptx/csv/srt/vtt/ass/lrc/po/json 系列。**新 PDF 默认本地 MinerU**，通过独立解释器调用；先阅读并执行 [PDF 工作流](references/pdf_workflow.md)。`AINIEE_REPO` 仅用于原有 Windows Office 非 PDF 回退。

请求 LaTeX/Typst 源码或模板 PDF 时，再读 [书籍模板](references/book_templates.md)，先检查可选工具和字体。沿用已审阅的同一译文结构；保留源码、编译报告并检查真实 PDF，不重复提取或翻译，不把编译失败后残留的旧 PDF 当作成品。

**一次性准备：**

1. **确认本技能的安装位置**。把本 `ainiee-translate/` 文件夹放进 agent 的 skills 目录：
   ```bash
   ~/.claude/skills/ainiee-translate/     # Claude Code
   ~/.codex/skills/ainiee-translate/      # Codex（OpenAI Codex CLI）
   ```
   下文用 `$SKILL_DIR` 指代它。**在 Codex 等非 Claude Code 平台使用、以及工具名（Bash/Task/TodoWrite…）对照见 [`references/codex-tools.md`](references/codex-tools.md)。**

2. **建一个 venv 并装依赖**（任意 Python ≥ 3.12）：
   ```bash
   python3 -m venv ~/.venvs/ainiee-translate
   ~/.venvs/ainiee-translate/bin/pip install \
     msgspec beautifulsoup4 lxml rich openpyxl polib python-pptx chardet 'jsonschema>=4.23,<5'
   ```

3. **设置两个路径变量**（每个新终端；或写入 shell profile）：
   ```bash
   export SKILL_DIR=~/.claude/skills/ainiee-translate            # 本技能安装目录
   export AINIEE_PY=~/.venvs/ainiee-translate/bin/python         # 上面 venv 的 python
   # 可选：非 PDF Office(Windows) 回退到 AiNiee：
   # export AINIEE_REPO=/path/to/AiNiee
   ```

**命令前缀（后文用 `<PFX>` 代替）：**

```bash
PYTHONPATH="$SKILL_DIR/scripts" "$AINIEE_PY"
```

> 管道脚本以 `ainiee_translate` 包形式打包在 `$SKILL_DIR/scripts/` 下，`PYTHONPATH` 指向该 `scripts` 目录即可 `-m ainiee_translate.<module>` 调用。`AINIEE_REPO` 仅供非 PDF Office 回退；新 PDF 按 PDF 工作流配置 MinerU。

**自检命令（确认环境就绪）：**

```bash
PYTHONPATH="$SKILL_DIR/scripts" "$AINIEE_PY" \
  -c "from ainiee_translate import io_dispatch; print('formats OK:', io_dispatch.supported_extensions())"
```

---

## 步骤 1：准备工作目录

每个翻译项目独立一个工作目录（下文用 `$WORK` 指代）：

```bash
export WORK=~/my-book          # 自取
mkdir -p "$WORK/work" "$WORK/out"
```

---

## 步骤 2：解析输入书籍

**输入含 PDF 时先执行 [PDF 工作流](references/pdf_workflow.md)**：pdf-to-epub 检查和本地提取 → 最低结构 prepare → parse 初翻 → 修正源文并局部重译 → 独立上下文对照 PDF 校对 → 定稿译书与绑定清单 → 实际 build/check。初翻前暂缓全面 OCR 校勘。旧 PDF 缓存需从原 PDF 建立新项目，保留历史。

将 epub/txt 解析成 `cache.json`（AiNiee `CacheProject` 格式）：

```bash
<PFX> -m ainiee_translate.parse \
  --input /path/to/book.epub \
  --type AutoType \
  --out "$WORK/work/cache.json"
```

- `--type`：`AutoType`（自动检测）、`Epub`、`Txt` 等，默认 `AutoType`。
- 成功后打印：`parsed N items -> work/cache.json`。
- **普通 EPUB 项目默认只译正文**：解析后跑 `scope` 划定范围（见下「步骤 2.5」）。新 PDF 的范围由提取前出版计划确定，保留已核验的序言、图注、注释及参考文献。
- **epub 的行内排版会被保留**：源书的斜体/粗体（`<i>`、`<em>`、`<span class="italic">` 等各种写法）在 `source_text` 里统一成 `<i>…</i>` / `<b>…</b>` 标记，导出时按该段原文的实际写法还原。翻译时**原样保留标记**（见 `references/translation_rules.md`），不要再用『』手动标斜体。
---

## 步骤 2.5：划定翻译范围（只译正文 + Historian's Note）

书评、版权页、献词、题记、目录页、致谢、作者简介、出版社注册/广告页、他书试读都不译：标成排除（状态 7），agent 不会读到，导出保留原文。

```bash
<PFX> -m ainiee_translate.scope "$WORK/work/cache.json"            # 预览：每个书内文件一行 keep/DROP + 理由 + 字数
<PFX> -m ainiee_translate.scope "$WORK/work/cache.json" --apply    # 写入（先备份）
```

按每个文件的第一段判断：章号（数字 / 罗马数字 / One / Chapter…）、Part/Book/Act、Prologue/Epilogue/Interlude、Historian's Note → 保留；
≤6 词的全大写或「月份 年份」分部/日期标题 → 保留（它们是正文结构）；目录 ncx 保留（章节标题）；其余排除。
预览里判错的用 `--keep <id>` / `--drop <id>` 纠正。三本实测书的非正文只占 1–1.7% 字数——省的主要是 agent 的注意力和一批无谓的审核，不是大钱。

## 步骤 2 附：修复存量项目的行内标记与空格（`repair`）

v1.4.1 及更早版本的 epub 解析用 `soup.get_text(strip=True)` 抽文本，有两个后果：
①**丢掉行内斜体/粗体**；②对每个文本片段单独 strip 再无缝拼接，把片段间的空格挤掉，
产生系统性粘连词（`her <i>blade</i> fell` → `herbladefell`）。解析层已修复；
**存量项目**不必重新解析（那会丢掉已有译文），用本命令从每段的 `extra.original_html`
就地重建 `source_text`：

```bash
# 预览（默认不写）
<PFX> -m ainiee_translate.repair ~/my-project/work/cache.json
# 写入（自动时间戳备份）
<PFX> -m ainiee_translate.repair ~/my-project/work/cache.json --apply
# 列出「补回了标记、但已有旧译文」的段——这些段的译文缺斜体，需重做
<PFX> -m ainiee_translate.repair ~/my-project/work/cache.json --list-marked
```

只改 `source_text`，不动译文与状态。补回的标记不会自动进旧译文，所以：
`--apply` 之后跑 `--list-marked`，把列出的段用 `batch write`（已译）/
`polish write`（已润色）重做一遍即可。

---

## 步骤 2 替代：导入已有项目（含 AiNiee 缓存）

不必每次从头解析。若已有一个翻译缓存——AiNiee 的工程缓存（`AinieeCacheData.json`）或另一个 ainiee-translate 项目的 `cache.json`（同为 `CacheProject` 格式）——可直接导入，再续翻/润色/校验/导出。

- 列出可导入的 AiNiee 工程（扫描 `~/Library/Application Support/AiNiee/ProjectCache`，可用 `AINIEE_CACHE_DIR` 覆盖）：

  ```bash
  <PFX> -m ainiee_translate.project list
  ```

  每项给出 `project_id`、`project_name`、`input_path`（原书）及状态计数（未译/已译/已润色/已排除）。

- 导入到项目（项目 ID 用 `--ainiee`，缓存文件路径用 `--cache`）：

  ```bash
  <PFX> -m ainiee_translate.project import --ainiee <项目ID> --work "$WORK"
  # 或：--cache /path/to/AinieeCacheData.json --work "$WORK"
  ```

  把缓存规范化进 `$WORK/work/cache.json`（已存在则先时间戳备份），并打印 `input_path` 与状态计数。

导入后按状态接续：还有未译段→步骤 5 续翻；已译待润色→步骤 6.5 润色；直接出成品→步骤 6 导出（原书路径见 `input_path`）；查残留→步骤 7。

---

## 步骤 3：生成并审核锁定术语表

新任务先读取[术语表文档](scripts/ainiee_translate/assets/docs/术语表文档.md)与[Schema 契约](references/glossary_schema.md)。从当前文献和用户资料提取有上下文依据的候选，生成结构化 `glossary.locked.json`：`persons`、`terminology`、`abbreviations`、`non_translate`；分类自定义，不预置领域。

人名的 `chinese_translation` 填明确音译或通行中文译名，术语的 `target_form` 填目标语言译法；不要因为正文默认 D 就在这些目标字段重复源语言。源文另存 `source_form`，转写另存 `latin_form`。动态冠名可用 `target_template` 和显式人名引用，模板与固定译文互斥；缺少依据就标待核实，不臆造译名。

译名和 note 遵循[标点说明](scripts/ainiee_translate/assets/docs/标点符号.md)：中英文、汉字与数字间合适地加一个空格，数字与单位不加空格；同一姓名与词内用 `-`，两个人名之间用 `–`，中文破折号用 `——`。带公式的术语用 TeX 记录，JSON 反斜杠须转义。识别源文保留实际写法。

按[校对工作台](references/review_workbench.md)生成术语审核页面，展示上下文、页码、候选和依据；没有真实建议时保持无建议状态。用户在网页正式提交并回到聊天说继续后，核验版本再写回。新条目和歧义先审核，再锁定。

```text
<PFX> -m ainiee_translate.glossary lint --locked "$WORK/work/glossary.locked.json"
<PFX> -m ainiee_translate.glossary_bundle --locked "$WORK/work/glossary.locked.json" --out "$WORK/out/术语迁移包.zip" --notes 本表特殊说明.md
```

生成锁定表并准备跨项目复用时，配套运行打包命令。先整理该表特殊的身份、转写、领域、公式、固定译法及标点说明，再用 `--notes` 附入包中。包须包含词表、Schema、政策及其 Schema、术语表文档和本表说明；迁移不等于自动认可新文献中的所有译法。

已有 AiNiee config/profile 的 `glossary --config ... --analysis ... --out ...` 入口仍生成旧 `characters/terms` 格式，仅用于兼容导入，不能当作新建术语表的默认入口。同姓自动归并结果要人工核实；旧词表须先人工迁移再使用新格式打包功能。

## 翻译模组：复用任务设置

先读[翻译模组](scripts/ainiee_translate/assets/docs/翻译模组.md)。新目录是 `~/.ainiee-translate/翻译预设/翻译模组/<用户命名>/`，包含 `初次翻译.md`、`预设参数.md`、`润色校对.md`、`语言风格.md`、`glossary.locked.json`、`glossary.locked.schema.json`，另有 module 元数据和绑定政策。通用预设位置暂留空。

```text
<PFX> -m ainiee_translate.module create <名字> --source-language en --target-language zh --punctuation-mode full --name-mode D
<PFX> -m ainiee_translate.module load <名字> --work <项目目录>
```

翻译与润色前读取 `work/预设参数.md`、`work/style.md`、本批提示词和锁定词表；项目旁有个人 Schema 时先验证。`预设参数.md` 明确 full/half 和 A/B/C/D；每次任务单独确认输出格式，不在模组中默认输出。PDF 项目将标点模式同步到 `review.json.structure_rules.punctuation_mode`。半角模式或明确启用直角引号时，机械 audit 的相应风格警告要按所选政策辨析，不自动改回全角或把所选引号当错误。

加载时复制六项用户文件并重新绑定当前人名政策，保留已有项目文件备份；旧英文模组兼容读取，不自动迁移。模板选择见[输出模板](scripts/ainiee_translate/assets/docs/输出模板选择.md)，姓名选择见[人名模式](scripts/ainiee_translate/assets/docs/人名翻译模式.md)。

---

## 步骤 3+：用户自定义提示词（可选，像 AiNiee 一样自己写规则）

翻译规则分两层，**领域/风格规则不写死在技能里**——和 AiNiee 一样由用户自己写：
- **通用层（技能自带）**：`references/translation_rules.md`，即 AiNiee 原生标准提示词（逐行、保留标记、忠实准确）。
- **项目层（用户自己写）**：人名怎么处理、头衔怎么摆、对话风格、世界观、示例等，全由用户提供。

两种来源：
1. **复用 AiNiee app 的提示词设置**（推荐）：你在 AiNiee 里配的「自定义系统提示词 / 角色介绍 / 写作风格 / 世界观 / 翻译示例」都存在 `config.json`，按各自开关汇总成一份：
   ```bash
   <PFX> -m ainiee_translate.prompt --config "<AiNiee config.json>" --out ~/my-project/work/user_prompt.md
   ```
   （读取 `translation_user_prompt_data` / `characterization_data` / `writing_style_content` / `world_building_content` / `translation_example_data`，仅纳入开关打开的部分。）
2. **手写项目提示词**：直接在 `~/my-project/work/user_prompt.md` 写你的规则（如「人名保留原文」「军衔后置」等）。

翻译时 agent 遵循：**AiNiee 原生原则（translation_rules.md）＋ 用户自定义提示词（user_prompt.md，若有）＋ 锁定表（术语表/角色表）**。技能本身不预设任何特定题材的规则。

---

## 步骤 4：选择介入模式

开始翻译前，与用户确认介入模式：

| 模式 | 行为 | 适用场景 |
|------|------|---------|
| **A 抽样自动（默认）** | 先译约 1 章展示给用户确认风格和规则对齐；之后自动逐章。遇到锁定表外的歧义新实体时停下询问。 | 第一次翻译新书 |
| **B 每章过目** | 每章译完后展示给用户，点头确认后写回，再译下一章。歧义实体停下询问。 | 用户想细粒度监控 |
| **C 全自动** | 整本一次性译完写回，歧义实体不停止，记入 `needs_review` 列表，最后统一报告。| 已熟悉风格、快速跑完 |

---

## 步骤 5：翻译循环

### 5a. 读取未译批次

```bash
<PFX> -m ainiee_translate.batch read \
  "$WORK/work/cache.json" \
  --size 100
```

输出：JSON 数组，每项包含 `text_index`（段落编号）和 `source_text`（源文）：

```json
[
  {"text_index": 1, "source_text": "The room fell silent."},
  {"text_index": 2, "source_text": "Marlow studied the letter."}
]
```

**恢复机制**：`read` 只返回 `translation_status = UNTRANSLATED` 的段落。重跑时自动跳过已译段，从断点继续。

### 5b. Agent 翻译

**Agent 本身就是翻译引擎。** 读取上一步的 JSON，逐段按以下规则翻译：

1. **通用规则**见 `references/translation_rules.md`（AiNiee 原生：逐行对应、保留标记、忠实准确）。
2. **项目规则**（人名保留、头衔摆放、风格等）见用户自定义提示词（步骤 3+，由用户自己写，不写死在技能里）。
3. **人名/术语** 以锁定表及任务政策为准。新表按 A 汉化／B 拉丁转写／C 源语言／D 姓名体系处理（默认），资料不足保留源文并列待核实；先读[默认术语表契约](references/glossary_schema.md)。旧表 `render` 为英文则保留原文。
4. 遇到锁定表外的新实体：模式 A/B 停下询问用户；模式 C 用锁定表最近匹配或保留原文，并记入待审列表。

将翻译结果写成 JSON 文件：

```json
[
  {"text_index": 1, "translated_text": "房间里一片寂静。"},
  {"text_index": 2, "translated_text": "Marlow 端详着那封信。"}
]
```

保存为 `$WORK/work/translations_batch_001.json`（命名自取）。

### 5c. 写回缓存

```bash
<PFX> -m ainiee_translate.batch write \
  "$WORK/work/cache.json" \
  "$WORK/work/translations_batch_001.json"
```

- 写回前自动创建带时间戳的备份 `cache.json.bak.YYYYMMDD_HHMMSS`（默认只保留最近 10 个，`AINIEE_BACKUP_KEEP` 可调，0 = 不清理；手工备份如 `cache.json.pre_xxx` 不受影响）；写入是原子的（临时文件 + rename），并持有 `cache.json.lock` 文件锁。
- **写回闸门**：空译文、`<i>`/`<b>` 数量与源文不符、未知 `text_index` 拒收并逐条列出，退出码 1 表示有拒收。项目允许 i/b 变化时可加 `--allow-tag-mismatch`。结构 PDF 的 `⟦AT:kind:id⟧` 标记须原样、各一次、原序保留；翻译与润色写回均检查，`--force` 和 i/b 例外均不能绕过。普通旧项目的 force 行为沿用原规则。批次中的章节、图注和注释元数据是结构上下文，参考批次只读；主控统一写 cache。同时统计风格警告（见 `audit`）。
- 可以一次给多个文件，也接受 **JSONL**（每行一个 `{"text_index","translated_text"}`）：`batch write cache.json t1.json t2.jsonl …`——一次备份、一次加载、一次保存。
- 成功后打印：`applied N of M`。重复执行步骤 5a → 5c 直到 `batch read` 返回空数组（`[]`）为止。

---

## 步骤 5+：多 agent 并行翻译（可选，大书加速）

书很大、章节相互独立、且**风格已用模式 A 锁定**后，可派多个 subagent 并发翻译不同章节范围，
墙钟时间≈最慢的 agent（实测 11 章 1704 段用 7 个 agent 约 9 分钟译完）。编排的每一步都是一条命令：

```bash
<PFX> -m ainiee_translate.batch split "$WORK/work/cache.json" --target 300 --out-dir "$WORK/work/par" --context 20   # 按章节边界分组 → grp_N_src.json + grp_N_ctx.json（前 20 段只读上下文）
<PFX> -m ainiee_translate.glossary filter --locked "$WORK/work/glossary.locked.json" --for "$WORK/work/par/grp_1_src.json" --out "$WORK/work/par/g_1.json"   # 每组一份只含本组出现条目的瘦身词汇表（66 KB → ~5 KB）
#   … subagent 边译边 append par/trans_N.jsonl …
<PFX> -m ainiee_translate.batch validate "$WORK/work/par/grp_1_src.json" "$WORK/work/par/trans_1.jsonl"   # 索引齐全/无空译/标记成对 + 风格警告；不过只重派那一组
<PFX> -m ainiee_translate.batch write "$WORK/work/cache.json" "$WORK/work/par"/trans_*.jsonl                 # 一次写回全部
<PFX> -m ainiee_translate.glossary merge-newterms --locked "$WORK/work/glossary.locked.json" "$WORK/work/par"/newterms_*.txt --apply
```

**唯一铁律：subagent 绝不写 `cache.json`**。subagent 只产出 `trans_N.jsonl` + `newterms_N.txt`，**主控 validate 后一次 `batch write`**。
各 agent 共享 `STYLE_GUIDE.md`（用 `references/style_guide_template.md` 生成，要点从已确认的样章反推）+ 可选 `BOOK_BIBLE.md`
（`references/book_bible_template.md`：译前抽出人物性别/实衔/亲属/舰级等事实，防止跨章一致的事实性错译）+ 本组瘦身词汇表 + `translation_rules.md`。
新实体一律「保留原文 + 记录」，每波收工就 merge-newterms + scan，下一波直接受益。

完整流程、派发 prompt 模板、模型分层建议、Workflow 脚本模板见 **`references/parallel_translation.md`**。

---

## 步骤 6：导出成品

```bash
<PFX> -m ainiee_translate.export \
  --cache "$WORK/work/cache.json" \
  --output "$WORK/out/" \
  --input /path/to/book.epub
```

- 使用 AiNiee 的 `FileOutputer` 保留原书结构和富文本标签。
- 输出文件名带 `_translated` 后缀（默认），例如 `book_translated.epub`。

---

## 步骤 6.5：润色（可选）

若当前模块带 `polish_prompt.md`（已随加载落到 `work/`），可对已译文本做润色 pass：状态 TRANSLATED→POLISHED，可断点续跑；导出读 `final_text`，自动采用润色后的文本。模块无润色提示词则跳过本步。

循环直到 `batch read-translated` 返回 `[]`：
1. `<PFX> -m ainiee_translate.batch read-translated work/cache.json --size 100` → `{text_index, source_text, translated_text}` 数组。
2. agent 按 `work/polish_prompt.md` + 锁定词汇表润色每段（**逐行 1:1、保留标记、人名/术语依词汇表**），写 `work/polished_NNN.json`（`{text_index, polished_text}`）。
3. `<PFX> -m ainiee_translate.polish write work/cache.json work/polished_NNN.json`（写回并置 POLISHED；同样过闸门，接受多文件与 JSONL）。

**润色也能并行**（大书）：`batch split --stage polish --out-dir work/par` 把已译段按章切组，组文件带 `translated_text`；每个 subagent 边润边 append `par/polished_N.jsonl`（`{text_index, polished_text}`）；`batch validate grp_N_src.json polished_N.jsonl` 验收；`polish write work/cache.json work/par/polished_*.jsonl` 一次写回。`progress` 读到 `par/_stage.json` 里的 `polish` 会显示翻译/润色两条进度条，组状态 `written` = 全部已置 POLISHED。

---

## 步骤 7：验证残留规则违规

```bash
<PFX> -m ainiee_translate.verify \
  "$WORK/work/cache.json" \
  "$WORK/work/glossary.locked.json"
```

输出 JSON 格式的问题列表，并打印问题总数。基础检测：

- `empty_translation`：源段有内容但译文为空（漏译）。
- 旧格式 `name_not_preserved`：源段含锁定表要求原样保留的人名，但译文中该名消失。新格式按源形式识别人名，再核对所选 A/B/C/D 模式的目标姓名；汉化本身不构成错误。

verify 检查**已译（status 1）和已润色（status 2）**两类段（润色文本就存在 `translated_text`）。明确的漏译或政策不符，使用 `batch write`（已译段）/ `polish write`（已润色段，保住状态）修正后重查。新格式的姓名表示缺失、未知体系和同形多义须保留为待核实／待辨义；不能猜造译名或修改正确译文来清零问题。

### ⚠️ verify 的局限：为什么「verify 干净」≠「没有翻译错误」

verify 是**词汇表执行器**，不是**发现器**。它只能发现「锁定表里登记过的人名」消失的情况，因此天然漏掉下面这些（实战中绝大多数漏网错误都属于此）：

1. **词汇表覆盖不全（头号原因）**：verify 只知道表内姓名（新表 `persons`，旧表 `characters`）。**没进表的名字它根本不知道要查**——配角、地名、舰名，尤其当词汇表是从「上一本书」或 AiNiee 分析缓存里种出来、没针对当前书补全时。一份「2 个问题」的干净报告，往往只是因为表里恰好只有 2 个相关名字。→ **对策：词汇表必须随当前书补全**（见下方 `scan` 发现流程）。以下英文保留的例子主要描述旧表；新表须以当前姓名模式为准。
2. **整段成员检查，漏「同段对错并存」**：若同一段里某名字一处保留英文、另一处被音译（例：`Keru 看着…后来克鲁离开`），verify 看到「Keru 在」就不报。
3. **「全程音译」的名字无信号**：若某名字在**全书每一处**都被音译（例 `Tenmei→天明`、`Rianu→里亚努`），它从没以英文出现过，"时而对时而错"的不一致信号为零。
4. **区分不了「音译错误」与「合理代词省略 / 合法意译」**：补全词汇表后，那些把名字合理处理成「他/她」的段会被误报；`Vulcan→瓦肯` 这种合法意译它也无法识别。
5. **完全不覆盖的错误类型**：①「张冠李戴」——表外名字被换成**别的**名字（`Dax→萨姆`、`Gard→Vic`）；② **丢空格的粘连词**漏进译文（`thenaiskosfragment`；epub 解析器那批已修，见 `repair`）；③ 整句**未翻译的英文残留**留在译文里；④ 模型**幻觉插入**的短乱码（顶替源文的 `Lt`/`Vic`）。

### 步骤 7+：用 `scan` 发现词汇表缺口与解析瑕疵（补 verify 盲区）

```bash
<PFX> -m ainiee_translate.scan \
  "$WORK/work/cache.json" \
  --locked "$WORK/work/glossary.locked.json" \
  --mode all        # all | discover | terms | strays | merges
```

- `discover`：找**不在词汇表、原文有但译文中消失**的专名（语言无关、不依赖词汇表、逐出现处、覆盖 status 1+2）。
  - `inconsistent`（**高置信，优先处理**）：同名时而保留英文、时而消失——单点滑落 / 同段对错并存（如 Rio Grande、Keru）。
  - `never_preserved`（**需人眼判断**）：从不以英文出现，含「全程被音译的真名」（Tenmei→天明、Rianu→里亚努）与「合法意译的术语」（Vulcan→瓦肯）两类混在一起。
- `terms`：**反向漏译**——词汇表里有中文译名（`dst`、非 `keep_source`）的术语，却在个别段被留成了英文（`Starfleet`→星际舰队 全书都译了、唯独某段漏成 "Starfleet"）。
- `strays`：**模型幻觉插入**——译文里出现、但该段原文里没有的英文 token（凭空写出的错名 `Vic`/`Sam`/`Sef`、顶替"the guard"的 `Lt`）。是**复查列表非合格门**：含一贯保留的外星术语，需人眼筛；真信号是无来由的短错名。
- `merges`：原文里**超长 Latin 串或 camelCase 跳变**的丢空格粘连词（`thenaiskosfragment`、`speciesDraco`、`TheAlexandria`）；调小 `--min-merge-len` 可挖更短的。
  - ⚠️ 这类粘连的**主因**曾是 epub 解析器逐片段 strip（`her <i>blade</i> fell` → `herbladefell`），已在解析层修复。新解析的项目里 `merges` 命中数应大幅下降；**存量项目**先跑 `repair --apply` 再看，剩下的才是源书本身的排版缺陷。

### 步骤 7++：`audit` 机械体检与 `glossary lint`

```bash
<PFX> -m ainiee_translate.audit "$WORK/work/cache.json" --out "$WORK/work/audit.json"      # 空译/标记不匹配（硬伤）+ 半角标点/「」/省略号/中文内空格/未译原样搬运/长度比异常（警告）
<PFX> -m ainiee_translate.glossary lint --locked "$WORK/work/glossary.locked.json"         # alias 带头衔（verify 假阳性源）、两人共用同一 alias、同姓角色、重复/缺译名的术语
```

`audit` 与 `batch write` 闸门用同一套检查，所以正常写入的项目 `empty`/`tag_mismatch` 应为 0；警告类按段号抽查。
`glossary lint` 的 `alias_has_title`（如 `Admiral Janeway`）会让 verify 在头衔被翻译的每一处都误报，`alias_collides`（`Paris` 同时挂在 Owen Paris 与 Tom Paris 下）说明清洗时把两个人并了——改表再 verify。

**推荐校对闭环**：`verify` → `audit` → `glossary lint` → `scan --mode all`，根据上下文修正明确问题，补充确认的词条后再核验。新格式修改正式表的 `persons/terminology/abbreviations`，保留稳定 ID、语言、引用和政策；不得把运行视图的 `characters/terms` 写回新表。旧格式才向 `characters` 补姓名、向 `terms` 补带 `dst` 或明确 `keep_source:true` 的术语。资料不足和歧义继续列待核实，不为清零猜译名；同段正确姓名与错误写法并存仍需语义检查。改已润色段一律用 `polish write` 保住状态。

> 经验：写自查脚本做名字比对时，先归一化撇号（弯/直撇号 `'`/`'` 统一），否则 `Mak'ala`、`Quark's`、`O'Brien` 会因撇号不同被误判为「消失」。verify/scan 内部已统一处理。

## 步骤 7.5：对抗性审核（可选，去 AI 味 + 抓润色漏掉的误译）

润色只改表达，且同一个模型自审漏得多（Warpath 实测：Sonnet 润色后人工逐句校 4 章仍抓出 ~80 段，几乎全是词法/搭配层与真误译）。
本步先让 **Blind Reader** 只读中文、像读者一样标出读着别扭的地方（`review blind` / `review hints`），再把**找问题**（Reviewer，带源文逐条落实 flag，句式病整句重写）和**否决问题**（Challenger，奖励精度，但读者绊过的地方不许以「原译可通／偏好」否决）拆给互不通气的 Opus 实例，另加一个只读术语清单的
Consistency auditor；主控只跑机械闸门：`review pre`（`offending` 恰好一次、红线改动即拒、定稿术语只加不删、`<i>/<b>` 成对、
不动拉丁 token）→ `review final`（合并 verdicts：A 误译/B 硬伤自动进 `apply_X.json` → `polish write`；C 翻译腔/D 不一致进 `review_ALL.md`
给用户勾选 → `review pick`）。分类标准与十二条 AI 味清单在 `references/review_taxonomy.md`，三份 prompt 在 `references/review_prompts.md`，
协议、`config.json` 红线格式、先在人工校过的章节上做基准打分（`review benchmark/score`，判定门召回 ≥60% 且精度 ≥80%）见
[`references/adversarial_review.md`](references/adversarial_review.md)。斜杠命令 `/ainiee-translate:review <起-止段号>`。

**开工前**：全书性的译法政策（种族名音译与否、集体智慧体代词、军衔体系、外语短句）按 `references/book_bible_template.md` §5
一次问清并落进机械规则——审完再定就是全书返工。**省 token**：`review rules` 给每组切词汇表/裁定；`review segs --tier`
让有盲读佐证的低严重度条目免 Challenger（实测送审量 −63%，佐证条目否决率 0.1%）；前几组后 `review stats` 复核分级是否安全。

```bash
<PFX> -m ainiee_translate.batch split "$WORK/work/cache.json" --stage review --range 438-719 --target 140 --prefix g --out-dir "$WORK/work/review/groups" --context 3
<PFX> -m ainiee_translate.review rules "$WORK/work/cache.json" g1 g2          # → rules_gN.json（agent 读它，不读整份 EXAMPLES）
<PFX> -m ainiee_translate.review blind "$WORK/work/cache.json" g1 g2
# … Blind Reader ×N（Opus，只读中文）→ flags_gN.jsonl …
<PFX> -m ainiee_translate.review hints "$WORK/work/cache.json" "$WORK/work/review"/flags_g*.jsonl
# … Reviewer ×N（Opus，读 hints_gN.json）→ findings_gN.jsonl …
<PFX> -m ainiee_translate.review pre  "$WORK/work/cache.json" "$WORK/work/review"/findings_g*.jsonl
<PFX> -m ainiee_translate.review segs --tier "$WORK/work/cache.json" "$WORK/work/review"/findings_g*.pre.jsonl   # → challenge_gN.jsonl + verdicts_gN.auto.jsonl
<PFX> -m ainiee_translate.review inventory "$WORK/work/cache.json" --range 438-719
# … Challenger ×N（读 challenge_gN.jsonl）+ Consistency ×1 → verdicts_gN.jsonl / findings_D.jsonl …
<PFX> -m ainiee_translate.review stats "$WORK/work/cache.json" g1 g2           # → stats.md：各格否决率，>2% 的移回送审
<PFX> -m ainiee_translate.review final "$WORK/work/cache.json" g1 g2 D
<PFX> -m ainiee_translate.polish write "$WORK/work/cache.json" "$WORK/work/review"/apply_g*.json
<PFX> -m ainiee_translate.review merge "$WORK/work/cache.json" g1 g2 D        # → review_ALL.md 给用户
```

---

## 附录 A：命令速查

```bash
# 路径变量（每次新终端）
export SKILL_DIR=~/.claude/skills/ainiee-translate
export AINIEE_PY=~/.venvs/ainiee-translate/bin/python   # venv with: msgspec bs4 lxml rich openpyxl polib python-pptx chardet
export WORK=~/my-book
# 可选：export AINIEE_REPO=/path/to/AiNiee   # 非 PDF Office 回退

# 命令前缀
PFX="PYTHONPATH=$SKILL_DIR/scripts $AINIEE_PY"

# 解析
$PFX -m ainiee_translate.parse --input book.epub --type AutoType --out "$WORK/work/cache.json"
$PFX -m ainiee_translate.scope "$WORK/work/cache.json" [--apply] [--keep ID…] [--drop ID…]   # 只译正文 + Historian's Note

# 词汇表
$PFX -m ainiee_translate.glossary --config "<config.json>" --out "$WORK/work/glossary.locked.json"

# 用户自定义提示词（汇总 AiNiee 配置里的自定义提示词）
$PFX -m ainiee_translate.prompt --config "~/Library/Application Support/AiNiee/config.json" --out work/user_prompt.md

# 批次读取
$PFX -m ainiee_translate.batch read "$WORK/work/cache.json" --size 100

# 批次写回
$PFX -m ainiee_translate.batch write "$WORK/work/cache.json" "$WORK/work/translations_001.json"

# 导出
$PFX -m ainiee_translate.export --cache "$WORK/work/cache.json" --output "$WORK/out/" --input book.epub

# 验证
$PFX -m ainiee_translate.verify "$WORK/work/cache.json" "$WORK/work/glossary.locked.json"

# 修复存量项目的行内标记与空格（旧版解析出的 cache.json；预览去掉 --apply）
$PFX -m ainiee_translate.repair "$WORK/work/cache.json" --apply

# 发现（补 verify 盲区：表外被音译/丢失的专名 + 术语漏译 + 幻觉错名 + 粘连词）
$PFX -m ainiee_translate.scan "$WORK/work/cache.json" --locked "$WORK/work/glossary.locked.json" --mode all

# 续翻/补章：从已译段抽专名先例表给并行 agent 对齐
$PFX -m ainiee_translate.precedents "$WORK/work/cache.json" --for "$WORK/work/par"/grp_*_src.json --locked "$WORK/work/glossary.locked.json" --out "$WORK/work/BOOK_BIBLE.md"

# 机械体检 / 词汇表结构检查 / 并入并行 agent 记录的新词
$PFX -m ainiee_translate.audit "$WORK/work/cache.json" --out "$WORK/work/audit.json"
$PFX -m ainiee_translate.glossary lint --locked "$WORK/work/glossary.locked.json"
$PFX -m ainiee_translate.glossary merge-newterms --locked "$WORK/work/glossary.locked.json" "$WORK/work/par"/newterms_*.txt --apply

# 进度面板（多 agent 时每组一行；--watch 在另一个终端分屏跑，--line 给 statusline）
$PFX -m ainiee_translate.progress "$WORK/work/cache.json" --once
$PFX -m ainiee_translate.progress "$WORK/work/cache.json" --watch

# 并行翻译：分组 / 瘦身词汇表 / 验收 / 一次写回多组（详见 references/parallel_translation.md）
$PFX -m ainiee_translate.batch split "$WORK/work/cache.json" --target 300 --out-dir "$WORK/work/par" --context 20
$PFX -m ainiee_translate.glossary filter --locked "$WORK/work/glossary.locked.json" --for "$WORK/work/par/grp_1_src.json" --out "$WORK/work/par/g_1.json"
$PFX -m ainiee_translate.batch validate "$WORK/work/par/grp_1_src.json" "$WORK/work/par/trans_1.jsonl"
$PFX -m ainiee_translate.batch write "$WORK/work/cache.json" "$WORK/work/par"/trans_*.jsonl

# 对抗性审核：切组 / 闸门 / 抽段 / 术语清单 / 合并 verdicts / 过目表 / 勾选 / 基准打分 / 留痕（详见 references/adversarial_review.md）
$PFX -m ainiee_translate.batch split "$WORK/work/cache.json" --stage review --range 438-719 --prefix g --out-dir "$WORK/work/review/groups" --context 3
$PFX -m ainiee_translate.review rules|blind|hints|pre|segs [--tier]|final|merge|pick|inventory|stats|benchmark|score|log "$WORK/work/cache.json" …
```

---

## 附录 B：常见问题

**Q: `parse` / `import` 报 `ModuleNotFoundError`（bs4 / lxml / openpyxl / polib / pptx）？**
A: 缺依赖。在 `$AINIEE_PY` 的 venv 里 `pip install msgspec beautifulsoup4 lxml rich openpyxl polib python-pptx chardet`，并确认 `PYTHONPATH` 指向 `$SKILL_DIR/scripts`。不再需要 `AINIEE_REPO`（非 PDF Office 回退才设）。

**Q: `batch read` 返回空数组 `[]`？**
A: 所有段落均已翻译完毕（`translation_status = TRANSLATED`），可以进行导出步骤。

**Q: 导出后 epub 没有内容？**
A: 检查 `cache.json` 中是否有 `translation_status = 1` 的段落（即已译段）。可用 `batch read` 确认剩余未译数量。

**Q: 如何重做某段译文？**
A: 直接用 `batch write` 写入新的 `translated_text`（按 `text_index` 覆盖），`write_back` 会用新值替换旧值。

**Q: 如何跳过不需要翻译的段落（如纯数字章节号）？**
A: 在 `translations.json` 中将 `translated_text` 设为源文原样，或在生成时 agent 判断后直接复制源文。

**Q: `verify` 报 0 问题，但书里明明还有人名被音译 / 错译，为什么？**
A: verify 只执行**锁定表里登记过的**人名，且无法识别张冠李戴、粘连词、未译残留、幻觉插入。「0 问题」常常只说明表内名字没丢。用 `scan --mode all` 发现表外被音译/丢失的专名（`discover`）、被漏译成英文的术语（`terms`）、幻觉错名（`strays`）、粘连词（`merges`），**把确认的真名补进词汇表后再 verify**。详见步骤 7「verify 的局限」。

---

## 附录 C：斜杠命令（菜单）

安装为插件后，所有操作都可用 `/ainiee-translate:<命令>` 完成（`/` 选择器即菜单，或 `/ainiee-translate:menu` 看清单）：

| 命令 | 作用 |
|------|------|
| `menu` | 显示命令菜单 |
| `translate <输入> [模块]` | 端到端翻译（解析→词汇表→翻译→导出→校验）|
| `import-profile <profile.json> <模块>` | 导入 AiNiee profile 为模块 |
| `module list\|show\|create\|load …` | 管理模块 |
| `gen-prompt translate\|polish [模块]` | 让 agent 起草翻译/润色提示词 |
| `switch-prompt [模块]` / `show-prompt [模块]` | 切换 / 查看模块 |
| `polish [批大小]` | 润色 pass |
| `repair` | 修复存量 epub 项目的行内标记与空格（旧解析器遗留）|
| `glossary` / `export <输入>` / `verify` / `status` | 词汇表 / 导出 / 校验 / 状态 |
| `scan [discover\|terms\|strays\|merges\|all]` | 补 verify 盲区：表外被音译/丢失的专名(`discover`)、被漏译成英文的术语(`terms`)、幻觉插入的错名(`strays`)、粘连词(`merges`)|
| `audit [--allow-tag-mismatch]` | 机械体检：空译/标记不匹配（硬伤）+ 半角标点/「」/长度比等风格警告 |
| `progress [--line\|--json]` | 进度面板：全书进度 + 每个并行组的 running/stalled/ready/needs_fix/written |
| `review <起-止段号> [--target 140]` | 对抗性审核：Reviewer 找问题 → 机械闸门 → Challenger 否决 → A/B 自动写回、C/D 给用户过目（去 AI 味 + 抓误译）|

命令脚本路径用 `${CLAUDE_PLUGIN_ROOT}/skills/ainiee-translate/scripts`，并需用户设好 `AINIEE_PY`（`AINIEE_REPO` 非 PDF Office 回退才需要）。

---

## 附录 D：实时进度（`progress`）

翻译进度在磁盘上是可观测的：`cache.json` 的状态计数在每次 `batch write` 后变化；并行时每个 subagent 边译边 append 的 `par/trans_N.jsonl` 行数就是该组的实时进度；`apply_writeback` 每次写回都往 `work/progress.jsonl` 追加一条事件。`progress` 模块只读这些文件：

```bash
<PFX> -m ainiee_translate.progress work/cache.json --watch     # 另开终端分屏：rich 实时面板，2 秒刷新
<PFX> -m ainiee_translate.progress work/cache.json --once      # 渲染一次（斜杠命令 /ainiee-translate:progress 就是它）
<PFX> -m ainiee_translate.progress work/cache.json --line      # 一行摘要：📖 Warpath 2391/2507 (95%) · ▶3 18/24 ▶4 25/25 · ✓1,2 · 4.1/min
<PFX> -m ainiee_translate.progress work/cache.json --json      # 完整快照（--out FILE 写文件）
<PFX> -m ainiee_translate.progress work/cache.json --serve 8765 --open   # 本地网页看板：任何浏览器、Claude Code Desktop 都能开，2 秒轮询
```

每组状态：`running`（jsonl 在长）→ `ready`（条数够且无空译/标记问题，可 `batch write`）或 `needs_fix`；jsonl 超过 `--stall` 秒（默认 180）没动就标 `stalled`；写回后变 `written`。面板底部给速率、剩余段的 ETA、卡死与可写回的组。**润色阶段**（`split --stage polish` 产生的 `par/_stage.json`）：顶部多一条润色进度条，组文件识别 `polished_N.jsonl`，`written` 指全部已置 POLISHED。

**Claude Code Desktop / 手机**（无终端分屏时）两条路：
1. `--serve`：本地 stdlib 服务，浏览器打开 `http://127.0.0.1:8765/`，与 `--watch` 同一份快照、真实时；Desktop 里点链接即可。
2. **Artifact 看板**（云端、可分享、手机能看）：一个声明了 `db` 能力的 Artifact 页面订阅文档 `progress/current`。主控 agent 每收到一组完成通知或每波写回后执行
   `progress --json --out work/progress_snapshot.json`，再用 Artifact 工具 `write_db`（`db_op: set`，`collection: progress`，`doc_id: current`，`file_path` 指向该文件）推送；页面实时刷新。粒度是「组完成 / 每波」，不是 2 秒——中途要更细就让主控定时推。看板页面源码在 `references/progress_artifact.html`，任何账号都能用它重新发布一份。

**statusline 接入**：`--watch` 与 `--line` 都会把一行摘要写到 `~/.ainiee-translate/progress.line`；在 statusline 脚本里加几行「文件存在且 5 分钟内更新过就拼进状态栏」，会话底栏就常驻进度，不用切窗口。示例（macOS `stat -f %m`）：

```bash
pl="$HOME/.ainiee-translate/progress.line"
if [ -f "$pl" ] && [ $(( $(date +%s) - $(stat -f %m "$pl" 2>/dev/null || echo 0) )) -lt 300 ]; then
  line+=" | $(head -c 200 "$pl")"
fi
```
