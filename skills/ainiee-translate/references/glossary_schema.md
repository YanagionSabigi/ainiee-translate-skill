# 默认术语表契约

创建 module、编写或校对新格式词表、切换姓名政策以及过滤子表时使用本说明。旧 AiNiee profile、旧 module 和冻结审核包沿用旧格式，不自动迁移。

## 开始整理

建议先根据文献内容和翻译任务生成领域分类，核对名称、层级和适用范围后再给词条分配分类。系统只定义分类结构，不附带学科枚举、数学分类树、默认领域、词库或缩写。空分类合法，不需要为了创建 module 填写“其他”等占位分类。

新建 module 会生成空的 `glossary.locked.json` 和 `glossary.locked.policy.json`，前者保存唯一正式词表，后者保存任务的姓名模式和分类选择。两份 JSON Schema 随运行脚本的 `ainiee_translate/schemas/` 提供。

```text
<PFX> -m ainiee_translate.module create <名字> --source-language English --target-language 简体中文 --name-mode D
<PFX> -m ainiee_translate.module show <名字>
<PFX> -m ainiee_translate.module load <名字> --work <项目目录>
```

如已有自己的分类文件，可创建时传 `--categories <JSON>`，并用重复的 `--category <ID>` 选择范围。默认选择全部领域；父节点包含后代，未分类条目和公共缩写仍保留，引用递归补齐。分类文件的具体包装格式以 `module create --help` 为准。

## 字段

根对象版本为 `schema_version: "1.0.0"`，分类内容单独记录 `taxonomy_version`。五个集合分别列于下表。

| 集合 | 用途 |
| --- | --- |
| `categories` | 项目自己定义的分类树：稳定 `id`、`name`、可选 `parent_id` 和别名 |
| `persons` | 人名：`person.*` ID、源文、拉丁转写、经确认汉字名和姓名体系 |
| `terminology` | 术语：`term.*` ID、源文与首选目标译文，或明确的人名组合模板 |
| `abbreviations` | 缩写具体义项：`abbr.*` ID、源文、必填展开义和译法／明确保留原文政策 |
| `non_translate` | 既有禁翻标记与正则规则，不与文字缩写混用 |

语言形式是 `{text, language}`。保留 Unicode、重音和实际语言标签；不把非英语原文伪标成英语。词条共用 `source_form`、可选 `category_ids`、`aliases`、`derived_forms`、`references` 与辨义 `note`。别名的 `usage` 区分 `accepted` 和 `recognition_only`；后者可识别但不推荐输出。独立含义另建条目；同姓、同拼写或字符串前缀不能作为自动合并依据。

术语／缩写首选译文用 `target_form`，支持不同目标语言。未确认译文可暂缺，但必须作为待审核项。缩写须有 `expansion`；公共缩写可标记 `common: true`，有明确依据时才设置 `keep_source: true`。同形多义保留独立 ID 和辨义说明；扫描／核验报告候选，不能要求同一处同时出现各候选译名。

组合译名可用 `target_template`，如 `<<person:person.poincare>> 猜想`，引用的 ID 必须存在并列在 `references`。模板与 `target_form` 互斥，模板本身是正式值；展开预览只供阅读，不能写回为固定译文。没有模板的固定译文须人工检查人名部分与当前政策一致。不通过替换字符串前缀猜测冠名。

## 四种姓名模式

| 模式 | 规则 |
| --- | --- |
| A | `chinese_translation`，完全汉化 |
| B | `latin_form.text`，通行拉丁转写 |
| C | `source_form.text`，保留源语言 |
| D（默认） | 经确认 `name_system` 为 han 时用汉字名，latin 时用源语言拼写，other 时用拉丁转写 |

三种姓名表示须指同一人、同一姓名范围。`name_system` 描述经确认的姓名体系，不能根据输入字符或国籍猜测。例如已拉丁化的日本姓名仍须核对人物身份后选择其汉字名。汉字名可保留日本原有日语汉字。

资料不足或体系 unknown 时暂留源文，同时记录待核实；不得猜造汉字名、转写或把 fallback 当成核验通过。模板中的人名同样按所选模式展开。旧格式的 render 保持既有意义。

## 政策快照与文件操作

姓名模式属于 module／任务配置，不在每条姓名里重复保存。`module.json` 引用配套政策，加载时复制到项目。改变全局激活 module 不改变进行中项目的冻结政策。

正式词表通过 `policy_sha256` 绑定同目录 `<词表 stem>.policy.json`。复制、改名或过滤词表时须带配套政策；`glossary filter` 会生成输出对应的政策文件。丢失、篡改或配置非法时应报错，不能悄悄改为默认 D。独立、从未绑定的草拟词表默认采用 D。

编辑配套政策须通过工具重新生成哈希绑定，不能仅手改文件继续使用。两文件更新前校验并保留备份；若更新中断导致不一致，使用配套备份恢复。它们不是单一原子文件。不要把运行时 characters/terms 兼容视图另存回正式词表。

## 校验与人工复核

```text
<PFX> -m ainiee_translate.glossary lint --locked <glossary.locked.json>
<PFX> -m ainiee_translate.glossary filter --locked <glossary.locked.json> --for <源文JSON> --out <子表JSON>
```

校验覆盖 Schema、分类父关系与循环、ID／引用和模板约束；机械检查不证明人物身份、词义或译法正确。`AINIEE_GLOSSARY_SCHEMA` 可追加项目级校验，约束原始文档。

使用[工作台](review_workbench.md)核对原始字段。新表按稳定 ID 绑定；模板审核编辑模板而非展开结果。未编辑的语言、引用、分类等字段保留，正式提交后才受控写回。政策或业务身份漂移须重新准备审核，不能应用旧政策下的决定。Agent 不代用户提交真实决定。
