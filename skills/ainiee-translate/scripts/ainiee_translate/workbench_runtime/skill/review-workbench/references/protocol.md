# 通用输入与反馈协议

运行根目录的 `schemas/` 是字段类型的权威定义。源码根目录是本 skill 的上两级；独立安装包根目录为本 skill 下 `runtime/`。使用 `validate` 验证输入，避免凭示例推断所有约束。

## 输入

`schema_version: "1"`。包字段为 package_id、title、base_commit（输入时 null）、groups、facets、assets、items。ID 使用英文/数字/点/横线/下划线，最多 128 字符；中文用于 title、location、正文。

groups 为 `[{id,title}]`；facets 为 `[{id,title,options:[{id,title}]}]`。条目只属于一个 group_id，`facets` 是维度到选项 ID 数组的映射。

每项结构：

```json
{
  "id": "term-compactness",
  "target_id": "glossary-compactness",
  "group_id": "terms",
  "facets": {"domain": ["math"]},
  "requires_human": false,
  "before": [{"id": "term", "type": "text", "text": "紧性"}],
  "baseline": [{"id": "term", "type": "text", "text": "紧性"}],
  "proposal": [{"id": "term", "type": "text", "text": "紧致性"}],
  "evidence": [{"id": "source", "type": "text", "text": "compactness"}],
  "rationale": "与紧致空间的用语一致。",
  "location": "compactness"
}
```

该例的 `terms`、`domain/math` 需要在包级定义。同一目标的多个审核项共享 target_id 与相同 baseline。每个版本按 block id 配对，before/baseline/proposal 的 block id 与类型一致；proposal 可为 null。

| 块类型 | 内容 |
| --- | --- |
| text | `id,type,text`，纯文本，不是 HTML |
| tex | `id,type,text`，TeX 数学表达式，无需 `$` 分隔符 |
| image | `id,type,asset_id`，建议用在 evidence；图像本身不能当作文本编辑 |
| table | `id,type,rows`，矩形字符串二维数组 |

资源格式为 `{id,path,media_type}`，path 必须在 `assets/` 下且为相对路径。支持 PNG、JPEG、WebP、GIF、SVG；可补 full_asset_id、物理 page、printed_page、width/height 与 region。prepare 自动补资源 SHA256，检测冻结材料被更换；版本依据仍是 Git commit，不用时间戳判断冲突。

图像圈画预留 drafts 条目 `shapes: [{asset_id,kind,coordinates,comment}]`：kind 为 rectangle/ellipse/arrow，四个坐标均归一化到 0…1，对应源图原尺寸。首版没有圈画 UI，不向用户声称已实现。

scope JSON 是普通文件的项目相对路径数组。`--out` 指定尚不存在、位于明确 `--project` 内的新目录；命令参数优先使用绝对路径，避免工作目录歧义。准备前确认文件可进入业务项目本地 Git。`prepare` 把明确范围与输出审核材料纳入独立基准引用，保持业务分支和真实 index 不变；不会 stash 或推送。无首个提交也支持，Git 身份由项目环境提供。独立演练若位于另一个仓库内，先在演练项目根 git init；真实业务正常复用已有仓库。

## 保存与提交

drafts.json 包含 package_id、base_commit、material_hash、revision 与 items。material_hash 用于冻结材料完整性检查，revision 用于防止页面覆盖；它们都不用于推断业务版本先后。条目 mode 为 null/accept/keep/edit/comment，各模式草稿独立保留。

页面每次保存携带 expected_revision；过期返回409。成功返回新 revision 后才认为已落盘。提交只包含用户选择范围内的有效决定，保存到 `submissions/SUBMISSION_ID.json`。

accept/keep/edit 的决定含 `item_id,target_id,action,blocks`，blocks 为完整最终内容。comment 含 `instruction,quotes,processing: "needs_agent"`，没有 blocks。accept 精确使用冻结 proposal，keep 精确使用冻结 before。

引用含 item_id、block_id、version、text、start/end，可带 prefix/suffix/base_commit。范围按 Unicode 码点计算，不是浏览器 UTF-16 单元；回传时校验精确文字，不能自动匹配到另一处同文。

## 当前稿与冲突

当前投影格式：

```json
{
  "package_id": "the-package-id",
  "base_commit": "本轮实际的完整 Git commit ID",
  "targets": [{"target_id": "glossary-compactness", "blocks": [{"id": "term", "type": "text", "text": "当前实际译名"}]}]
}
```

比较状态包括 satisfied、ready、conflict、needs_agent、missing_current。不要把缺失目标当成原稿未改。不同人工决定按目标列出，即便来自不同 item；不因文件顺序或较晚导入而覆盖。

用户可以在比较视图“采用此决定”。这会生成新的人工提交，`resolves: [{submission_id,target_id}]` 明确列出被解决的旧决定。旧提交仍可审计，活跃比较只使用未被明确解决的决定；回传包需带上被引用的历史。`resolves` 不由业务 agent 擅自补写。

包 ID/基准不匹配、同提交编号不同内容、未知条目或伪造 accept 内容会被拒绝。回传只认已提交决定，草稿和未提交选项不自动应用。跨目录迁移通过包内 baseline.json 材料指纹、原 base_commit 与 origin_commit 关联，不携带 Git 仓库，也不要求接收者安装 Git。旧 Git 迁移包仍可读取。
