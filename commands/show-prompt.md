---
description: 查看模组的提示词与词汇表摘要
argument-hint: [模组名]
allowed-tools: Bash, Read
---
使用 module CLI 的 show 读取指定模组的元数据、完整文件列表与术语统计；未给名字时从 AINIEE_TRANSLATE_HOME 下的 active.json 读取 active_module。通过 module.module_dir(name) 解析真实目录，使用 Read 展示初次翻译.md、润色校对.md、预设参数.md、语言风格.md；旧模组回退为 translate_prompt.md、polish_prompt.md、style.md。不得硬编码用户主目录或将名字拼入 shell 命令。

```bash
PYTHONPATH="${CLAUDE_PLUGIN_ROOT}/skills/ainiee-translate/scripts" "${AINIEE_PY:-python3}" -m ainiee_translate.module show "$1"
```
