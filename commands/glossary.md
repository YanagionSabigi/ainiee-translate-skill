---
description: 提取、审核、锁定或打包迁移术语表
argument-hint: [用户要求或旧 --config 参数]
allowed-tools: Bash, Read, Edit
---
先读技能步骤 3 与[术语表文档](../skills/ainiee-translate/scripts/ainiee_translate/assets/docs/术语表文档.md)。新建任务从当前文献提取候选，生成 persons、terminology、abbreviations、non_translate 四类记录；自定义领域，按 Schema 校验，生成工作台供人审核。中文译名填音译或通行译名，不因正文模式 D 重复源文；中英文空格与 -／–／—— 分清，公式用 TeX。

仅当用户明确导入旧 AiNiee config/profile 时使用 `glossary --config ... --out work/glossary.locked.json`，该入口保留旧格式，不能当作新表默认流程。已激活模组时通常直接使用模组词表，不重建。

网页保存是草稿；正式提交并回到聊天明确继续后才比较并应用。没有真实建议表时不伪造建议。准备跨项目复用时整理本表特有的身份、译名、分类、公式与标点说明，运行：

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/skills/ainiee-translate/scripts" "${AINIEE_PY:-python3}" -m ainiee_translate.glossary_bundle --locked work/glossary.locked.json --out out/术语迁移包.zip --notes 本表特殊说明.md
```
