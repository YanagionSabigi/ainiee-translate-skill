# ainiee-translate

让编码 Agent 按你的术语表、提示词和风格要求翻译书籍，并用本地 Python 工具管理分段、进度、校对和导出。支持 EPUB、TXT 和经过结构整理的 PDF，也可以导入已有 AiNiee 缓存继续翻译。

**PDF 翻译依赖 MinerU 完成内容提取，优先使用本地部署。** 本地模式需要自行准备 MinerU 运行环境和模型；也可以显式选择远程 MinerU API，在允许上传指定文档后完成提取。本项目不附带 MinerU 模型、远程凭据或服务额度，本地失败不会自动改用远程服务。EPUB / TXT 的基础翻译不需要 MinerU。

翻译和语言审校由当前 Agent 完成，脚本负责读写与验证，无需另配翻译 API。使用过程仍受所在 Agent 平台的模型用量和权限限制；微信读书同步是另外启用的联网功能。

本项目依赖并继承两个上游项目的成果：[AiNiee](https://github.com/NEKOparapa/AiNiee) 提供基础文件读写、缓存结构及翻译规则，[AiNiee-skill（ainiee-translate-skill）](https://github.com/xuanji86/ainiee-translate-skill) 提供 Agent 翻译技能、提示词与术语表管理、批次工作流和插件基础。本项目在此基础上扩展 PDF 出版与阅读校对；基础运行所需的相关代码和技能文件已随本项目包含，无需为 EPUB / TXT 另外安装上述两个上游项目。

> 当前版本：`v2.0.0`，本仓库首个正式版本。核对日期：2026-10-22。

## 可以做什么

| 场景 | 使用方式与结果 |
| --- | --- |
| 翻译 EPUB / TXT | 解析为缓存，按批翻译、润色，导出原格式译文及支持的双语版本 |
| 继续已有翻译 | 导入 AiNiee 工程缓存或本工具的 `cache.json`，从尚未完成的段落接续 |
| 统一译名与风格 | 使用锁定术语表、自定义提示词，或复用包含这些设置的任务模块 |
| 翻译 PDF | 优先本地 MinerU，也可显式选用远程 API 提取；整理结构、初翻、对照原页独立校对，再出版 EPUB；可选 Markdown、LaTeX、Typst 和模板 PDF |
| 阅读时人工校对 | 在微信读书用蓝色波浪线和想法标记问题，生成桌面 HTML 对照报告，按编号明确批复后写回 |

普通 EPUB / TXT 等项目按原格式导出；跨格式的 Markdown、EPUB 和书籍模板导出目前要求经过审阅的 PDF 结构。PDF 输出为重新排版的译书，不保留原 PDF 的逐页版式。

## 安装

需要 Python **3.12 或更新版本**，以及能够加载技能、读写本地文件和运行 Python 的编码 Agent。基础格式无需安装 AiNiee 桌面应用，也无需配置 `AINIEE_REPO`。

翻译 PDF 时还需配置 MinerU：本地模式准备独立环境和模型，远程模式准备 API 凭据并明确文档上传范围。两种配置及其限制见下方“PDF 翻译与出版”。

以下从**本仓库根目录**开始，适用于首次手动安装。已有同名技能时，先备份原目录，再替换完整技能目录。技能附带运行脚本，单独安装 Python 包不能代替安装技能。

### Windows / PowerShell

```powershell
python -m venv .venv
$env:AINIEE_PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $env:AINIEE_PY -m pip install msgspec beautifulsoup4 lxml rich openpyxl polib python-pptx chardet

# Codex 默认技能目录；若自定义了 CODEX_HOME，改为相应目录。
$skillParent = Join-Path $HOME '.codex/skills'
New-Item -ItemType Directory -Force -Path $skillParent | Out-Null
Copy-Item -LiteralPath .\skills\ainiee-translate -Destination $skillParent -Recurse
$env:SKILL_DIR = Join-Path $skillParent 'ainiee-translate'
$env:PYTHONPATH = Join-Path $env:SKILL_DIR 'scripts'

& $env:AINIEE_PY -c "from ainiee_translate.io_dispatch import supported_extensions; print(supported_extensions())"
```

### macOS / Linux

```bash
python3 -m venv .venv
export AINIEE_PY="$PWD/.venv/bin/python"
"$AINIEE_PY" -m pip install msgspec beautifulsoup4 lxml rich openpyxl polib python-pptx chardet

SKILL_PARENT="${CODEX_HOME:-$HOME/.codex}/skills"
mkdir -p "$SKILL_PARENT"
cp -R skills/ainiee-translate "$SKILL_PARENT/"
export SKILL_DIR="$SKILL_PARENT/ainiee-translate"
export PYTHONPATH="$SKILL_DIR/scripts"

"$AINIEE_PY" -c 'from ainiee_translate.io_dispatch import supported_extensions; print(supported_extensions())'
```

在 Claude Code 中手动安装时，将目标父目录改为 `~/.claude/skills`。仓库另提供 `.claude-plugin/` 和 `commands/`，用于 Claude Code 插件方式的命令入口。自然语言使用技能不依赖这些斜杠命令。

`AINIEE_PY` 是上述虚拟环境的 Python 路径，`SKILL_DIR` 是完整技能目录，`PYTHONPATH` 指向其中的 `scripts`。新终端需要重新设置它们；Agent 的执行环境也需要能访问这些路径。

## 翻译第一本书

安装并让 Agent 加载技能后，可以直接说：

```text
用 ainiee-translate 把 D:/Books/sample.epub 翻译成简体中文，
项目放在 D:/Translations/sample。先给我一章试译，确认风格后继续。
人名保留英文，术语按我提供的术语表；译完检查并导出 EPUB。
```

没有现成术语表时，可以要求 Agent 先起草，审阅译名后再锁定。已有提示词、风格文件或 AiNiee profile 时，一并提供路径。

开始时约定介入方式：先看试译后继续、每章确认，或全自动完成后汇总待审问题。长书可以在宿主支持时分章并行，统一由主控写回缓存。

普通 EPUB / TXT 的流程是：

```text
解析 → 确认翻译范围 → 锁定术语与提示词 → 分批翻译 → 可选润色 → 检查 → 导出
```

EPUB 的范围工具会建议排除版权、广告等非正文；应先检查预览，再决定保留哪些内容。排除内容在原格式输出中保留原文。

后续可以这样继续：

```text
继续 D:/Translations/sample 的项目，从 cache.json 的未译段接着翻译。
```

或导入旧工程：

```text
用 ainiee-translate 导入 D:/OldProject/AinieeCacheData.json，
项目放在 D:/Translations/sample，检查已有进度后继续。
```

## 设置翻译模板：初翻、润色与术语表

翻译模板是可复用的任务设置，在工具中称为“模块”。设置前，先向 Agent 提供源语言、目标语言、书籍题材、目标读者、译名政策和偏好的译文例段；已有 AiNiee profile 时可以直接导入，再按当前书复核。三项内容按以下标准分别生成：

| 项目 | 文件与作用 | 生成标准 |
| --- | --- | --- |
| **初翻** | 模块中的 `translate_prompt.md`，加载后成为项目的 `work/user_prompt.md` | 写明语言方向、题材和叙述／对白风格；以源文为依据完整传达信息，检查否定、指代、人物关系、数字和单位，不增补情节或删减难句。逐段与 `text_index` 对齐，保留强调、占位符及 PDF 结构标记，遵循锁定译名；用原文—译文例段说明期望表达，歧义列为待审。 |
| **润色** | `polish_prompt.md`，加载后成为 `work/polish_prompt.md` | 同时对照原文和初翻，改善语序、搭配、节奏、对白及翻译腔；保留原意、信息量、人物口吻、锁定译名和结构标记。写明允许调整什么、哪些用户确认的写法不得改，并用“原译—改译—理由”示例说明尺度；准确通顺的句子可以保留，不为换说法而重写。 |
| **术语表** | `glossary.locked.json`，加载后成为 `work/glossary.locked.json` | 从当前书实际出现的名称、专业词和用户资料抽取候选，结合上下文确定译法。人物写入 `characters`，术语写入 `terms`，禁翻标记写入 `non_translate`；统一原形、别名、译名和保留原文政策。同姓人物不能误合并，歧义项交用户确认，不编造源文中没有的词条或直接套用另一本书的表。 |

生成后先检查三者是否一致：初翻和润色都服从同一份锁定术语表；提示词中的示例不能与译名政策冲突。用一段代表性正文和对白试译、试润色，确认后再用于全书。新增术语先列为候选，按约定确认后更新锁定表；项目提供术语 JSON Schema 时，还需通过该 Schema 校验。术语表结构可用 `python -m ainiee_translate.glossary lint --locked <文件路径>` 检查，机械检查不能代替译名审阅。

可直接这样要求 Agent：

```text
为这本书建立 my-book 翻译模块，源语言英语，目标语言简体中文。
先根据我提供的原文、术语资料和译文偏好生成初翻提示词、润色提示词、术语表。
初翻要完整准确，润色要对照原文改善中文表达，二者均保留标记并遵循锁定译名。
术语只收录有依据的词条，人物别名不得混淆；未定译法单独列给我确认。
展示这三份草稿，并用同一组例段演示初翻和润色的差别，确认后加载到项目。
```

模块默认保存在 `~/.ainiee-translate/modules/<模块名>/`。手动创建和启用的 PowerShell 示例：

```powershell
& $env:AINIEE_PY -m ainiee_translate.module create my-book --source-language en --target-language zh
# 在模块目录中完善 translate_prompt.md、polish_prompt.md、glossary.locked.json，审阅后再加载。
& $env:AINIEE_PY -m ainiee_translate.module load my-book --work 'D:/Translations/sample'
```

`module create` 只建立骨架，不会自动生成符合上述标准的提示词和词条；模块加载会把这三份文件复制进项目。修改模块后需重新加载才能用于该项目，已有项目文件会先备份；加载本身不会重译已完成的内容。

已有 AiNiee profile 时，可用 `python -m ainiee_translate.profile import --profile <profile.json> --name <模块名>` 导入其初翻、润色和术语设置；profile 没有润色配置时不会凭空生成。Claude Code 插件也提供 `/ainiee-translate:gen-prompt translate <模块名>`、`/ainiee-translate:gen-prompt polish <模块名>` 和 `/ainiee-translate:import-profile <profile.json> <模块名>`，提示词由 Agent 起草后供你审阅。

## 脚本使用示例

通常让 Agent 执行完整流程即可。需要手动检查管道时，下面是普通 TXT 的最小例子；沿用上面的 PowerShell 环境，在新建的空项目目录中运行：

```powershell
New-Item -ItemType Directory -Force -Path work, out | Out-Null
'The room fell silent.' | Set-Content -LiteralPath sample.txt -Encoding utf8

& $env:AINIEE_PY -m ainiee_translate.parse --input sample.txt --out work/cache.json
& $env:AINIEE_PY -m ainiee_translate.batch read work/cache.json --size 100
```

`batch read` 输出带 `text_index` 的源文。此例只有一段，将以下 JSON 保存为 UTF-8 文件 `work/translations.json`：

```json
[
  {"text_index": 1, "translated_text": "房间里一片寂静。"}
]
```

再写回并导出：

```powershell
& $env:AINIEE_PY -m ainiee_translate.batch write work/cache.json work/translations.json
& $env:AINIEE_PY -m ainiee_translate.batch read work/cache.json --size 100
& $env:AINIEE_PY -m ainiee_translate.export --cache work/cache.json --input sample.txt --output out
```

此时读取未译批次应得到 `[]`，输出包括 `out/sample_translated.txt` 和 `out/bilingual_txt/sample_bilingual.txt`。这演示的是数据管道；批次读取命令本身不会调用模型翻译。

每次批次写回会加锁、先备份，再原子保存。默认只保留最近 10 份自动备份，可用 `AINIEE_BACKUP_KEEP` 调整，`0` 表示不清理。空译文、未知编号和不匹配的强调标记会触发拒收；根据输出逐条处理，不要只看部分成功数量。

`batch read` 只返回未译段。普通项目导出可能仍包含未译原文，因此空队列之外，还需核对翻译范围、状态和实际成品。

## PDF 翻译与出版

PDF 是单独的结构化流程，依赖 MinerU 提取文本、图表、公式及布局信息。技能分发目录自带 `pdf-to-epub` 出版器，**不包含 MinerU 的模型和运行环境**。无论选择本地还是远程 MinerU，本工具环境都需 `pymupdf>=1.24`、`jsonschema>=4.22`；本地模型的依赖留在 MinerU 自己的环境中。在仓库虚拟环境中可执行：

```powershell
& $env:AINIEE_PY -m pip install 'pymupdf>=1.24' 'jsonschema>=4.22'
```

### 优先使用本地 MinerU

默认后端为 `mineru-local`，调用本地安装的 `mineru-kit parse`。用 `AINIEE_MINERU_ROOT` 或 `--mineru-local-root` 指定安装根目录；也可用 `--mineru-local-cli`、`--mineru-local-config`、`--mineru-local-env` 指定相应文件。提取前确认模型已在本地、远程 VLM 和额外 LLM 处理已关闭；文档提取与模型推理留在本机。安装上述两个 Python 库还不足以完成提取。

按 [PDF 工作流](skills/ainiee-translate/references/pdf_workflow.md) 完成检查和出版范围计划后，可以执行：

```powershell
$env:AINIEE_MINERU_ROOT = 'D:/Tools/MinerU'
& $env:AINIEE_PY -m ainiee_translate.pdf extract 'D:/Books/sample.pdf' --out 'D:/Translations/sample-pdf' --language en --backend mineru-local
```

本地配置缺失或提取失败时保留诊断与进度，不会自动上传文档。开发者选用独立出版器时，可设置 `AINIEE_PDF_TO_EPUB`；使用完整技能分发目录时一般无需此变量。

### 可选远程 MinerU

没有合适的本地模型环境时，可以显式选择 `--backend mineru`，通过远程 MinerU API 提取，无需本地模型。凭据从本机 `MINERU_TOKEN` 环境变量或 `~/.mineru/config.yaml` 的 `token:` 读取；不要将真实令牌写进提示词或仓库。远程服务的可用性、配额和费用由服务端决定。

远程模式会上传所选文档内容，需要你明确允许上传指定文件和范围，并在提交时使用 `--allow-upload`。例如，以下命令将原书第 1–20 个物理页交给远程服务：

```powershell
# 先在本机配置 MINERU_TOKEN；以下提交仅适用于已明确允许上传的文档范围。
& $env:AINIEE_PY -m ainiee_translate.pdf extract 'D:/Books/sample.pdf' --out 'D:/Translations/sample-cloud' --language en --backend mineru --pages 1-20 --allow-upload
```

当前远程入口不接受本地流程的 `publication-input.json` 出版排除计划；需要按该计划精确排除页面或区域时，使用本地路线。也可以用 `import-mineru` 导入已取得的完整 MinerU 结果 ZIP／目录，导入本身不上传原书。配置、结果格式与接续规则见 [MinerU 本地与远程说明](skills/ainiee-translate/scripts/ainiee_translate/publication_skill/references/mineru.md)。远程提取结果同样需要结构整理和原页校对。

### 翻译与正式导出

可以向 Agent 说明：

```text
用 ainiee-translate 翻译这本 PDF，使用本地 MinerU。
先确认出版范围和阅读顺序，初翻后对照原 PDF 独立校对，
最终导出 EPUB，保留图注、公式和脚注关系，并报告未解决的问题。
```

流程包括 `inspect → extract → draft → prepare → parse`，随后初翻、源文修订与受影响单元重译、独立上下文对照原页校对，最后正式导出。PDF 结构标记必须保留；`--force` 不能绕过这项检查。

正式导出要求与当前源文、译文、术语表和提示词版本一致的校对记录。仅完成润色或机械检查不能代替原页校对。旧的平面 PDF 缓存需要保留历史，并从原 PDF 建立新结构项目。

可选输出如下：

| 输出 | 额外条件 |
| --- | --- |
| EPUB | 使用共享出版器；正式 EPUBCheck 另需 Java 与本地 EPUBCheck JAR |
| Markdown | 使用与 EPUB 相同的已审阅译书结构与出版校验 |
| LaTeX / Typst 源码 | 使用书籍模板；配置与资源随源码保留 |
| 模板 PDF | 另需 XeLaTeX 或 Typst、相应字体；Typst 的 TeX 数学转换另需 Pandoc |

`--format pdf` 默认尝试 LaTeX、Typst 两条路线，可用 `--pdf-engine latex` 或 `--pdf-engine typst` 选择。详见 [书籍模板与工具要求](skills/ainiee-translate/references/book_templates.md)。

## 微信读书人工校对

适合已经有翻译缓存和阅读 EPUB、希望边读边改的项目：

1. 冻结本轮 EPUB、原书、缓存及术语和提示词版本；手动将这一份 EPUB 导入微信读书。
2. 用**蓝色波浪线**划出问题，可附自然语言想法；同步后定位到冻结版本。
3. Agent 对照原文辨析，生成带稳定编号的桌面 HTML，展示现译、想法、候选与推荐。
4. 在聊天中明确批复，例如“接受 7”“7 用 B”“保留 7”“搁置 7”或“7 改为……”，再写回对应段落。
5. 整本读完并明确确认后，完成同步、处理全部未决事项，通过出版检查，统一生成新版。

在线同步另需独立的微信读书官方技能目录和本机 `WEREAD_API_KEY` 环境变量。接口只读，不负责上传 EPUB，也不会把书中内容或阅读想法当成批准修改的指令。密钥不要写进聊天、命令参数或仓库。

真实账号需要先核验自导入书、蓝色样式、笔记关联与快照完整性；能力不明时会保留待确认状态。当前验收记录尚未完成真实账号整本交付，不能据离线回归结果认定所有账号都能完成这一流程。

操作与文件格式见 [微信读书人工校对](skills/ainiee-translate/references/weread_proofreading.md)，现有验证范围见 [微信读书校对验收记录](docs/weread-validation.md)。

## 常用入口与排查

Claude Code 插件提供以下入口；手动技能安装和 Codex 可直接用自然语言提出同样的请求。

| Claude Code 命令 | 用途 |
| --- | --- |
| `/ainiee-translate:translate <文件> [模块名]` | 启动翻译 |
| `/ainiee-translate:import-project` | 导入已有缓存 |
| `/ainiee-translate:module` | 创建、查看、加载任务设置模块 |
| `/ainiee-translate:polish` | 润色已译内容 |
| `/ainiee-translate:status`、`/ainiee-translate:progress` | 查看进度与接续位置 |
| `/ainiee-translate:verify`、`/ainiee-translate:audit`、`/ainiee-translate:scan` | 规则检查、机械体检、词汇表缺口扫描 |
| `/ainiee-translate:reading-review` | 微信读书人工校对 |
| `/ainiee-translate:export <原始文件>` | 导出当前项目 |

| 遇到的问题 | 检查什么 |
| --- | --- |
| 找不到 `ainiee_translate` | `AINIEE_PY` 是否指向装好依赖的解释器；`PYTHONPATH` 是否指向完整技能的 `scripts` |
| `parse` 拒绝覆盖缓存 | 已有缓存应接续或导入；重新解析请选择新的输出路径 |
| EPUB/TXT 请求模板输出被拒绝 | 普通项目使用原格式导出；跨格式模板目前需要结构化 PDF 项目 |
| PDF 提取无法启动 | 本地模式检查 MinerU 环境和模型；远程模式检查凭据、上传授权和服务状态；不要用 `AINIEE_REPO` 绕回旧 PDF 流程 |
| PDF 校对记录失效 | 源文、译文或配置是否变动；重新处理受影响单元并补齐当前版本证据 |
| 检查没有输出问题，却仍不放心 | `verify` 只覆盖部分规则，且发现问题也不以非零退出码表示；阅读实际报告，并检查成品 |
| EPUBCheck 显示 `unavailable` | 安装 Java 并通过 `EPUBCHECK_JAR` 指定本地 JAR；未运行不等于通过 |

## 进一步阅读

- [技能操作指南](skills/ainiee-translate/SKILL.md)：翻译、术语表、模块、润色与接续流程。
- [通用翻译规则](skills/ainiee-translate/references/translation_rules.md)：逐段对应和标记保留。
- [PDF 工作流](skills/ainiee-translate/references/pdf_workflow.md)：结构准备、修订和正式出版。
- [书籍模板](skills/ainiee-translate/references/book_templates.md)：工具、字体和导出设置。
- [微信读书人工校对](skills/ainiee-translate/references/weread_proofreading.md)：同步、HTML、批复和定稿。

## 许可证与来源

项目采用 [AGPL-3.0-only](LICENSE)。本项目基于上游 [AiNiee](https://github.com/NEKOparapa/AiNiee) 和 [AiNiee-skill（ainiee-translate-skill）](https://github.com/xuanji86/ainiee-translate-skill) 的代码与工作流发展，保留相应许可和来源声明；内置读写与缓存代码的具体来源见 [vendored NOTICE](src/ainiee_translate/_vendor/NOTICE)。PDF 提取另依赖 MinerU，本地安装或远程服务需单独准备；LaTeX 模板内的 Rosé Pine 主题另附 [MIT 许可证](src/ainiee_translate/templates/book/latex/rosepine/LICENSE)。字体与外部工具不随技能分发。
