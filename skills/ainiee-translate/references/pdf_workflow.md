# PDF 初翻、独立校对与 EPUB 出版

PDF 的检查、MinerU 调度、源书结构与 EPUB 写包均由 pdf-to-epub 执行。开发时设置 `AINIEE_PDF_TO_EPUB` 为同级开发副本；构建的技能 bundle 和 wheel 自带逐字同步的 publication_skill。全局安装目录不因本地开发改变。

## 准备与初翻

以下 PowerShell 示例使用中文与空格路径；先把变量换成实际项目路径。初翻前只整理阅读顺序、单元边界、资产与定位，保留未决引用和 OCR 错误。源文核验、独立对照校对和正式出版是不同状态。

```powershell
$env:PYTHONPATH = "<AiNiee开发副本>/src"
$env:AINIEE_PDF_TO_EPUB = "<工作区>/development/pdf-to-epub-skill"
$work = "D:/译书 项目/源书"
python -m ainiee_translate.pdf inspect "D:/原书/样书.pdf" --out $work
# 按出版技能 references/publication.md 确认页/区域角色并保存 publication-input.json。
python -m ainiee_translate.pdf extract "D:/原书/样书.pdf" --out $work --language en
python -m ainiee_translate.pdf draft --work $work
# 仅整理 review.json 的最低结构；metadata_provenance 记录书名的 PDF 依据。
python -m ainiee_translate.pdf prepare --work $work
python -m ainiee_translate.parse --input "D:/原书/样书.pdf" --pdf-work $work --out "D:/译书 项目/cache.json"
```

随后沿用批次命令与用户给定的锁定术语表、提示词初翻，主控原子写回 CacheProject。先用 `pdf_review.load_review_config` 校验锁定术语表 Schema；可以提供额外项目 Schema。初翻阶段不全面清理 OCR，也不把缺失内容补造为译文。bibliography-entry 原文策略使用独立保留状态，不把原文复制为已翻译。

## 延后的源文修订

`corrections.json` 每项含 `unit_id`、当前 `source_sha256`、新 `text` 和原 PDF 核验 `evidence`；关系修订含 ref_id/reference_sha256/targets/evidence。

```powershell
python -m ainiee_translate.pdf revise --work $work --changes "D:/译书 项目/corrections.json"
python -m ainiee_translate.pdf_review reconcile --book "$work/book.source.json" --cache "D:/译书 项目/cache.json" --work $work --output "D:/译书 项目/reconcile.json"
```

原始 raw 不变，每次源修订保留旧快照和依据；只重排受影响单元。重复句子按位置 ID 区分。拆并单元必须给显式旧/新 ID 映射，不能猜分旧译文；替换 PDF 则建立新项目。对缓存修订/校对的写入保留原有备份。

## 独立上下文对照原 PDF

完成初翻不等于校对通过。导出任务让独立上下文读取原 PDF 页面/区域、当前源文、译文、相同提示词和术语表，检查漏译、误译、OCR、术语、数字、公式、结构及引用。

```powershell
python -m ainiee_translate.pdf_review export --book "$work/book.source.json" --cache "D:/译书 项目/cache.json" --work $work --prompt "D:/译书 项目/prompt.md" --glossary "D:/译书 项目/glossary.locked.json" --context-id "review-session-2" --translation-context-id "translate-session-1" --output "D:/译书 项目/review-tasks.json"
# 独立审校者读取实际 PDF，输出带发现、处理、复核和 PDF 定位证据的 records；不能填写虚假通过。
python -m ainiee_translate.pdf_review import --book "$work/book.source.json" --cache "D:/译书 项目/cache.json" --work $work --prompt "D:/译书 项目/prompt.md" --glossary "D:/译书 项目/glossary.locked.json" --tasks "D:/译书 项目/review-tasks.json" --results "D:/译书 项目/review-results.json" --output "D:/译书 项目/proofreading.json"
```

任务与结果字段由脚本生成/核验。结果必须带当前 source/target hashes、独立 context_id、完整 checks、PDF sha/pages/observations、findings 的 resolution/recheck；源文或译文变更后的旧记录不能放行。单位 ID 和内容版本不变时可分章增量恢复。润色的 POLISHED 状态与机械检查均不能替代对照校对。

人工问题用 `python -m ainiee_translate.pdf_issues report --book BOOK --ledger LEDGER --output REPORT.md` 聚合；`decide` 需要 `--id --actor --reason --decisions-output`，只记录用户明确批准的疑难引用纯文字呈现。机器日志和详细诊断另存。

## 正式输出

```powershell
python -m ainiee_translate.export --cache "D:/译书 项目/cache.json" --input "D:/原书/样书.pdf" --output "D:/译书 项目/输出" --locked "D:/译书 项目/glossary.locked.json" --prompt "D:/译书 项目/prompt.md" --proofreading "D:/译书 项目/proofreading.json" --format epub --format latex --format pdf --pdf-engine latex
```

新 PDF 默认 EPUB，source 原版式输出明确不支持。MD、LaTeX、Typst 与 EPUB 使用同一当前译书及正式闸门。输出含独立译书快照、translation-manifest/1 和出版报告；源书 book.json、原审阅及状态保持不变。TeX/Typst 只使用临时渲染视图，源书仍以 epub-book/2 为准。

EPUB 结构检查、正式 EPUBCheck 和实际阅读器检查分别记结果。TeX 编译检查缺字、溢出、引用、公式与新 PDF，保留源码和相对资源。工具缺失、未运行或独立校对不可用时，正式验收保持待验证。

旧 PDF 缓存保留在历史中，从原 PDF 建新项目；外部 AiNiee 回退只服务非 PDF Office。原生 EPUB/TXT 等原流程继续使用。
