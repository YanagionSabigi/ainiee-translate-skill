---
description: 管理翻译模块（list / show / create / load）
argument-hint: <list|show|create|load> [名字] [--work 项目目录]
allowed-tools: Bash
---
管理模块（存放于 `~/.ainiee-translate/modules/`）。把用户给的参数透传给 module CLI：

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/skills/ainiee-translate/scripts" \
"${AINIEE_PY:-python3}" -m ainiee_translate.module $ARGUMENTS
```

- `list` —— 列出所有模块（标记当前激活）
- `show <名字>` —— 看某模块的元数据 + 术语/角色/禁翻计数
- `create <名字> [--source-language X --target-language Y --title T]` —— 新建空模块
- `load <名字> [--work 项目目录]` —— 设为激活；给 `--work` 时把提示词+词汇表拷进该项目 `work/`

注：`module` 子命令为纯文件操作，不需要 `AINIEE_REPO`。

新建 module 默认使用通用术语表 Schema，人名、术语、缩写和领域分类均从空表开始。建议创建前根据当前文献生成并检查领域分类；不预设学科或自动填入分类，没有分类也可以创建。

`create` 可用 `--name-mode A|B|C|D` 选择姓名模式（默认 D），用 `--categories <分类JSON>` 导入自己准备的分类，以重复的 `--category <ID>` 选择范围。人名 A 完全汉化，B 拉丁转写，C 保留源文，D 按经确认的姓名体系处理。详见 [默认术语表契约](../skills/ainiee-translate/references/glossary_schema.md)。

加载新 module 时须连同词表的 `.policy.json` 快照复制；移动或过滤词表也须携带配套政策。旧 module/profile 不自动迁移。
