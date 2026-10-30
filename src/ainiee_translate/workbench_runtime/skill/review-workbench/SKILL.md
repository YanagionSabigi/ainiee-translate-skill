---
name: review-workbench
description: Use when a workflow needs human review of text revisions, terminology, OCR, images, formulas or tables through a local review page, including portable review packages and returned decisions.
---

# 通用校对工作台

把人类需要判断的内容交给本地审核页面。上游 skill 生成材料、解释业务含义并修改业务原稿；本 skill 准备审核包、保存决定并提供比较结果。

## 调用

以本文件所在目录为 `SKILL_DIR`，统一调用：

```text
python SKILL_DIR/scripts/review.py --help
```

源码中的 launcher 自动找到仓库运行资源；独立安装包使用同目录下的 `runtime/`。首次缺依赖时，安装相应运行根目录的 `requirements.txt`。公式决定的提交/导入需要本机 Node.js，使用同份离线 KaTeX 校验；无需 npm 安装。完整输入例子在运行根目录 `examples/demo/package.json`；准备真实材料前读 [通用协议](references/protocol.md)。

## 准备一轮审核

1. 确定明确的业务项目根目录及本轮文件范围，检查该位置是否已有 Git（含上层仓库/worktree）。已有则复用；没有则在明确的项目根初始化。`prepare` 会完成这项检查。
2. 生成通用输入 JSON、`assets/` 资源和项目相对路径 scope 数组。给每项稳定 `id` 和 `target_id`，唯一主目录、少量可交叉筛选。缺证据/无法确定的条目设 `requires_human: true`；没有方案写 `proposal: null`。
3. 区分页面 `before`（保留原版所指）、`proposal`（接受建议所指）、`baseline`（当前真实业务稿）和 `evidence`（外文或源图）。已经先执行推荐时，baseline 反映执行后的真实稿件，不能沿用旧 before。
4. 验证输入，再准备新目录并启动页面：

```text
python SKILL_DIR/scripts/review.py validate INPUT_JSON
python SKILL_DIR/scripts/review.py prepare --project PROJECT --input INPUT_JSON --scope SCOPE_JSON --out NEW_PACKAGE_DIR
python SKILL_DIR/scripts/review.py serve NEW_PACKAGE_DIR
```

prepare 用临时 index 和独立 Git 引用固定本轮范围，不移动业务 HEAD 或改变原有暂存内容。保持输出目录唯一；材料冻结后产生新建议时开新一轮。被忽略的文件先由调用方整理成允许追踪的审核材料，不强制加入整个目录。

把启动输出的完整本地 URL 交给用户；可在所在应用中打开。自动保存不等于提交，AI 先执行推荐也不等于人已审核。等待用户在页面提交并回到聊天明确指示继续，不替人填决定或批量批准。

## 用户回复以后

读取审核包 `submissions/` 中的不可变已提交决定；`drafts.json` 只供恢复输入。使用完整结果块，不重新猜选中的建议。comment 是需要继续处理的指示，不是已经批准的最终文本。

先把此时业务稿投影成 `current.json`，再比较：

```text
python SKILL_DIR/scripts/review.py compare PACKAGE --current CURRENT_JSON
```

按 target/block 对照 Git 基准、当前稿和人工决定。已满足的无需重做；可应用的由业务 agent 按原业务流程写回；冲突显示各方内容并交人处理，保留历史。缺失当前目标或基准时先补齐，不直接应用旧包。语义正确性仍由业务 skill 判断，Git 无冲突不等于业务验收。

## 转交他人

```text
python SKILL_DIR/scripts/review.py export PACKAGE --out REVIEW_ZIP
python SKILL_DIR/scripts/review.py export PACKAGE --out OFFLINE_ZIP --offline-deps
python SKILL_DIR/scripts/review.py import-results PACKAGE --from RETURNED_JSON_OR_ZIP
```

审核包只携带启动入口、材料、前端、必要的 Python 服务与校验结构，不含 skill、示例或 Git 仓库；接收者需要 Python，无需 Git。含公式时保留离线 KaTeX，公式决定需要 Node.js。导出基准使用材料指纹清单，保留原 base_commit 供回传核对；旧 Git 迁移包仍兼容。离线 wheel 仅显式请求时携带，且匹配导出机环境。接收者在网页“记录”下载结果 JSON；`export --results-only` 由完整工具仓库执行。导入程序只读回传数据，不运行对方包内的启动脚本。

本 skill 不提供任何翻译/出版工具适配，也不直接修改已有业务 skill。
