# ainiee-translate

让编码 Agent 按你的术语表、提示词和风格要求翻译书籍，并用本地 Python 工具管理分段、进度、校对和导出。支持 EPUB、TXT 和经过结构整理的 PDF，也可以导入已有 AiNiee 缓存继续翻译。

**PDF 翻译依赖 MinerU 完成内容提取，优先使用本地部署。** 本地模式需要自行准备 MinerU 运行环境和模型；也可以显式选择远程 MinerU API，在允许上传指定文档后完成提取。本项目不附带 MinerU 模型、远程凭据或服务额度，本地失败不会自动改用远程服务。EPUB / TXT 的基础翻译不需要 MinerU。

翻译和语言审校由当前 Agent 完成，脚本负责读写与验证，无需另配翻译 API。使用过程仍受所在 Agent 平台的模型用量和权限限制；微信读书同步是另外启用的联网功能。

本项目依赖并继承两个上游项目的成果：[AiNiee](https://github.com/NEKOparapa/AiNiee) 提供基础文件读写、缓存结构及翻译规则，[AiNiee-skill（ainiee-translate-skill）](https://github.com/xuanji86/ainiee-translate-skill) 提供 Agent 翻译技能、提示词与术语表管理、批次工作流和插件基础。本项目在此基础上扩展 PDF 出版与阅读校对；基础运行所需的相关代码和技能文件已随本项目包含，无需为 EPUB / TXT 另外安装上述两个上游项目。

> 当前版本：`v2.4.0`，更新连续阅读模板、Dawn／白底样式和三级列表示例，保留通用术语表与阅读校对功能。核对日期：2026-11-08。

## 可以做什么

| 场景 | 使用方式与结果 |
| --- | --- |
| 翻译 EPUB / TXT | 解析为缓存，按批翻译、润色，导出原格式译文及支持的双语版本 |
| 继续已有翻译 | 导入 AiNiee 工程缓存或本工具的 `cache.json`，从尚未完成的段落接续 |
| 统一译名与风格 | 使用锁定术语表、自定义提示词，或复用包含这些设置的任务模块 |
| 翻译 PDF | 优先本地 MinerU，也可显式选用远程 API 提取；整理结构、初翻、对照原页独立校对，再出版 EPUB；可选 Markdown、LaTeX、Typst 和模板 PDF |
| 人工校对术语表 | 在本地工作台核对原词、上下文与 PDF 页码；按派生类批准暂定译名，也可逐项修改并提交决定 |
| 阅读时人工校对 | 在微信读书用蓝色波浪线和想法标记问题，在同一本地工作台查看原文、现译和候选，提交后回到聊天继续写回 |

普通 EPUB / TXT 等项目按原格式导出；跨格式的 Markdown、EPUB 和书籍模板导出目前要求经过审阅的 PDF 结构。PDF 输出为重新排版的译书，不保留原 PDF 的逐页版式。

## 安装

需要 Python **3.12 或更新版本**，以及能够加载技能、读写本地文件和运行 Python 的编码 Agent。交互校对工作台另需 **Git**；公式决定的提交或导入还需 Node.js，普通文本校对不需要 Node.js。基础格式无需安装 AiNiee 桌面应用，也无需配置 `AINIEE_REPO`。

翻译 PDF 时还需配置 MinerU：本地模式准备独立环境和模型，远程模式准备 API 凭据并明确文档上传范围。两种配置及其限制见下方“PDF 翻译与出版”。

以下从**本仓库根目录**开始，适用于首次手动安装。已有同名技能时，先备份原目录，再替换完整技能目录。技能附带运行脚本，单独安装 Python 包不能代替安装技能。

### Windows / PowerShell

```powershell
python -m venv .venv
$env:AINIEE_PY = (Resolve-Path .\.venv\Scripts\python.exe).Path
& $env:AINIEE_PY -m pip install msgspec beautifulsoup4 lxml rich openpyxl polib python-pptx chardet 'jsonschema>=4.23,<5'

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
"$AINIEE_PY" -m pip install msgspec beautifulsoup4 lxml rich openpyxl polib python-pptx chardet 'jsonschema>=4.23,<5'

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

## 开始前选择模式与翻译模组

开始翻译前，明确三项选择：**标点用全角还是半角、人名用 A／B／C／D 哪种模式、输出什么格式及模板**。默认标点为全角、人名为 D；翻译模组不设置默认输出格式。

| 文档 | 你可以在其中确认什么 |
| --- | --- |
| [标点符号与空格](src/ainiee_translate/assets/docs/标点符号.md) | 两种模式对照表、引号、横线、数字、单位和空格规则 |
| [人名翻译模式](src/ainiee_translate/assets/docs/人名翻译模式.md) | A／B／C／D 的设计考量，为什么默认 D |
| [输出模板选择](src/ainiee_translate/assets/docs/输出模板选择.md) | EPUB 文件、六份 LaTeX 模板与实际示例截图，Typst 预留 |
| [LaTeX 后端设计](src/ainiee_translate/assets/docs/LaTeX后端设计.md) | 后端代码、数学排版和格式校正的完整有序规范 |
| [术语表文档](src/ainiee_translate/assets/docs/术语表文档.md) | 四类记录与 Schema、人工审核、公式格式、打包迁移 |
| [翻译模组](src/ainiee_translate/assets/docs/翻译模组.md) | 中文目录、六份用户文件、创建／加载与旧模组兼容 |

翻译模组默认位于 `~/.ainiee-translate/翻译预设/翻译模组/<你取的名字>/`，主要内容为：

```text
初次翻译.md               # 初翻：完整准确、逐段对齐、保留标记和锁定译名
预设参数.md               # 标点符号模式、人名翻译模式；输出格式每次任务另选
润色校对.md               # 对照原文改善表达，保留信息、口吻和结构
语言风格.md               # 题材、读者、语气与例段
glossary.locked.json      # 人名、术语、缩写、禁翻项
glossary.locked.schema.json
```

目录中另有 `module.json` 与绑定姓名政策的 `.policy.json`。从当前书和用户资料提取候选后，先核实身份、别名、上下文与领域，再在工作台确认；没有依据的译法列为待审。人名的中文译名资料与正文的姓名模式分开保存，模式 D 不要求目标译名重复源文。

```powershell
& $env:AINIEE_PY -m ainiee_translate.module create 我的模组 --source-language en --target-language zh --punctuation-mode full --name-mode D
# 完善中文提示词、风格、术语表后加载；输出格式在任务中另选。
& $env:AINIEE_PY -m ainiee_translate.module load 我的模组 --work 'D:/Translations/sample'
```

`create` 建立空骨架，初翻、润色和风格内容由你与 Agent 按文献确定；用同一组例段试译、试润色，确认后用于全书。修改模组后需重新加载，已有项目文件会先备份，已译内容不会自动重译。旧的英文目录与提示词仍可读取；旧 AiNiee profile 可导入，不自动升级词表格式。

[通用翻译预设模组](skills/ainiee-translate/翻译预设/翻译模组/通用翻译预设模组/)暂留空，不预设题材与内容。新模组由用户自行命名。完整流程和迁移方式见上表。

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

## 本地校对工作台

术语表和微信读书反馈共用一套本地校对页面，复用 [Review Workbench](https://github.com/YanagionSabigi/review-workbench) 的设计与运行资源。左侧查看当前版本，右侧查看建议；可展开原文、其他候选和辨析依据，按需切换单项或连续阅读。页面资源、公式预览与相关字体随技能提供，无需 npm 安装或前端构建。

每项可选择接受建议、保留当前版本、手动修改或提出意见。**自动保存是草稿；点击“提交本轮”后，回到聊天说“继续”，Agent 才核验并写回。** 如果工作稿已变动，先处理冲突；留言会交给 Agent 继续辨析，不会直接变成已批准译文。

可以直接说：

```text
用校对工作台检查这个项目的术语表，并载入我提供的建议表。
我会在网页逐项修改并提交，完成后回到聊天说继续。
```

没有建议表时显示“暂无建议”，仍可手动修改或留言。人物、术语与禁翻项分组展示；当前版本不在网页增删术语实体。微信读书反馈需先完成定位和 Agent 辨析，再交给工作台处理。页面由本机服务打开，审核项目和本地版本记录保留在用户指定的工作目录。

完整入口见 [校对工作台指南](skills/ainiee-translate/references/review_workbench.md)，验证范围见 [接入验收](docs/review-workbench-validation.md)。

### 交给别人审核

让 Agent 将当前审核项目导出为“给别人审核的包”，把 ZIP 发给审核者。接收者解压后阅读 `OPEN-ME.txt`，准备 Python 3.11+ 和 jsonschema，Windows 双击 `开始校对.cmd` 打开页面；macOS 可使用 `start_review.command`，Linux 运行 `python3 start_review.py`。先完整解压，保留启动窗口；不要直接打开网页 HTML。可用 `python start_review.py --check` 检查环境，缺少依赖时窗口会显示安装指引。启动脚本只启动本地服务，不安装依赖、不联网下载。普通文本包不含公式引擎或字体，也不需要 Node.js；含公式时才附带对应资源并需要 Node.js 18+。接收者不需要 Git、AiNiee 或任何 AI skill。

审核者在网页正式提交后，从“记录”下载结果 JSON 回传；让原 Agent 导入原审核项目，再回到聊天明确继续写回。给别人审核的包不含技能目录、示例或 Git 仓库，与完整技能安装 ZIP 是两种用途不同的文件。

### 审核包与技能安装包

[本项目 Release](https://github.com/YanagionSabigi/ainiee-translate-skill/releases/latest) 的 `ainiee-translate-v版本.zip` 是完整 AI 技能安装包，包含 SKILL 和生成审核包所需的启动模板。发给审核者时，应从具体项目重新导出审核 ZIP；旧 ZIP 不会自动更新界面或启动入口。

只想体验通用工作台，可下载上游已发布的 [Review Workbench 0.2.0 演示审核包](https://github.com/YanagionSabigi/review-workbench/releases/download/v0.2.0/review-workbench-demo-0.2.0.zip)。它使用上游公开示例，含公式，不含你的书籍或微信读书数据；它也不代替 AiNiee 技能安装包。macOS 启动入口尚未在 macOS 真机验证。

## 微信读书人工校对

适合已经有翻译缓存和阅读 EPUB、希望边读边改的项目：

1. 冻结本轮 EPUB、原书、缓存及术语和提示词版本；手动将这一份 EPUB 导入微信读书。
2. 用**蓝色波浪线**划出问题，可附自然语言想法；同步后定位到冻结版本。
3. Agent 对照原文辨析，生成带稳定编号的校对工作台，展示现译、全部想法、原文、候选与推荐。
4. 在网页接受、保留、逐段修改或留言，正式提交本轮后回到聊天说“继续”，再核验并写回对应段落。
5. 整本读完并明确确认后，完成同步、处理全部未决事项，通过出版检查，统一生成新版。

在线同步另需独立的微信读书官方技能目录和本机 `WEREAD_API_KEY` 环境变量。接口只读，不负责上传 EPUB，也不会把书中内容或阅读想法当成批准修改的指令。密钥不要写进聊天、命令参数或仓库。

真实账号需要先核验自导入书、蓝色样式、笔记关联与快照完整性；能力不明时会保留待确认状态。当前验收记录尚未完成真实账号整本交付，不能据离线回归结果认定所有账号都能完成这一流程。

旧静态 HTML 和聊天编号批复继续可用，例如“接受 7”“7 用 B”“保留 7”“搁置 7”或“7 改为……”。操作与文件格式见 [微信读书人工校对](skills/ainiee-translate/references/weread_proofreading.md)，账号验证范围见 [微信读书校对验收记录](docs/weread-validation.md)。

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
- [校对工作台](skills/ainiee-translate/references/review_workbench.md)：术语与阅读反馈的页面审核、草稿、提交和受控写回。
- [微信读书人工校对](skills/ainiee-translate/references/weread_proofreading.md)：同步、辨析、批复和定稿。

## 许可证与来源

项目采用 [AGPL-3.0-only](LICENSE)。本项目基于上游 [AiNiee](https://github.com/NEKOparapa/AiNiee) 和 [AiNiee-skill（ainiee-translate-skill）](https://github.com/xuanji86/ainiee-translate-skill) 的代码与工作流发展，保留相应许可和来源声明；内置读写与缓存代码的具体来源见 [vendored NOTICE](src/ainiee_translate/_vendor/NOTICE)。PDF 提取另依赖 MinerU，本地安装或远程服务需单独准备；LaTeX 模板内的 Rosé Pine 主题另附 [MIT 许可证](src/ainiee_translate/templates/book/latex/rosepine/LICENSE)。校对工作台另附 [MIT 许可和来源](src/ainiee_translate/workbench_runtime/UPSTREAM.md)，KaTeX 与预览字体保留各自许可。书籍排版所需的系统字体和外部工具仍需自行准备。
