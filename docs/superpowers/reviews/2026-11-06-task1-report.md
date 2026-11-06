# Task 1 实现记录

范围：落实已批准的默认术语表契约、独立政策、module、运行消费者、工作台原始格式写回。未操作 PR、push、merge、安装目录或原 template checkout。

## 实现与裁定

- 新增 Draft 2020-12 结构 Schema 与政策 Schema；集中校验分类树、稳定 ID、引用、模板互斥、未知字段与非空文本。没有预置领域分类或正式词条。
- `glossary_document` 提供计划指定的七个接口；旧表保留未知字段，新表始终以原始结构存储，运行投影只在内存生成。
- 政策配套文件按 stem 命名，正式文档绑定字节 SHA-256；拒绝丢失、篡改或非法分类选择。写前校验、两文件备份、逐文件替换；双文件中断由哈希发现，未声称双文件原子事务。
- module 创建支持四模式、分类导入和 ID 选择；默认 D/空分类，同配置幂等、冲突报错；加载复制并冻结政策及其哈希。
- glossary CLI 过滤保留引用闭包与政策；新候选不编造译文。扫描、verify、review、precedents 使用集中运行投影；歧义候选不强制同时满足互斥译名，缺失资料保持可见。
- 工作台按稳定 ID 查找结构化词条，编辑原始姓名表示/目标文本/模板/说明，保留语言、分类、引用；模板展开仅作只读证据；政策变化要求重新准备。
- Ruling: 补接 `pdf_review`、`reading_round`、`reading_review` —— 它们也是实际消费者与冻结路径，仅修改计划列举文件会让新 module 的后续审核失败；冻结时配套政策一并保留，旧审核包继续使用旧表。
- Ruling: 分类导入包装只接受 `{categories: [...]}` 或裸数组，拒绝拼错字段，避免误生成空分类。
- Ruling: 人名识别包括源形式、经确认的拉丁形式、汉字名与显式别名/词形，覆盖源书已使用转写的情况，不据字符推断姓名体系。

## TDD 证据

所有命令使用 `../ainiee-translate-skill/.venv/Scripts/python.exe -m pytest --basetemp=local/<本轮目录> --tb=short`；父目录预先创建，输出保存在 checkout 的 local/。

- `local/task1-red.txt`：契约模块不存在，导入失败（RED）。
- `local/task1-workbench-red.txt`：3 failed，旧工作台没有 terminology 分组，真实提交无法找到目标（RED）。
- `local/task1-more-red.txt`：2 failed，漏识别已确认拉丁形式、残缺新契约被当旧表（RED）。
- `local/task1-module-red.txt`：1 failed，同配置重复创建误报冲突（RED）。
- `local/task1-pdf-red.txt`：1 failed，PDF 审核仍要求旧表字段（RED）。
- `local/task1-scan-red.txt`：1 failed，扫描未显示政策资料缺失（RED）。
- `local/task1-validation-red.txt`：3 failed，纯空白文本与分类包装拼错未拒绝（RED）。
- `local/task1-precedents-red.txt`：1 failed，先例表未显示缺失表示问题（RED）。
- 首轮相关新旧回归：`local/task1-related.txt`，35 passed in 39.74s。
- 扩充后相关回归：`local/task1-related2.txt`，47 passed in 44.89s。
- 新增契约/module/工作台：`local/task1-newtests-final.txt`，27 passed in 17.32s（后续又增加稳定 ID、项目 Schema、先例表验证，最终结果见下）。

## 最终验证

最终通过结果见文末。独立全分支审核由主控负责。

## 最新验证补充

- 最终相关新旧回归 `local/task1-related-final.txt`：53 passed in 54.80s。
- 全量初跑 `local/task1-full.txt`：309 passed, 4 failed, 1 warning in 279.50s。三个产品失败来自扫描歧义保护误插入其他函数，已删除误插块；回归 `local/task1-scan-green.txt`：32 passed in 1.70s，覆盖整个 scan 回归与新增契约测试。
- 别名候选去重补充：`local/task1-alias-red.txt` 1 failed 后修复 `_glossary_known`，上述 32 项已验证 GREEN。
- 剩余初跑失败是 `test_progress.py::test_serve_endpoints` 的 WinError 10013，本机回环 socket 权限限制；已请求允许现有回归使用回环服务的独立复验。普通权限全量最终重跑进行中。

## 独立审核修复

主控独立审阅要求三项修复，`local/task1-review-red.txt` 实际观察 3 failed 后实现：

- 人名/缩写歧义索引与 verify 统一使用 `recognition_key`，沿用 `latin_boundary_search` 的弯直撇号归一规则且不改变显示大小写；同一归一形式的多个稳定 ID 只报告待辨义，不同时强制多个目标。
- 缩写工作台增加显式 `keep_source` 布尔字段，可由真实提交关闭保留原文并保存目标译名，运行输出随之更新。
- 同集合首选源形式同形的多个身份要求每条填写非空辨义 note；普通识别别名碰撞仍可合法保留为待辨义。

`local/task1-review-green.txt`：43 passed in 28.14s，包含新契约、module、新格式工作台与全部 scan 回归。

此前普通权限完整重跑在审核修复后已主动停止（当时无产品失败），未作为最终证据。已允许仅本机回环运行最终整套，结果见最终验证。

本机回环单项独立复验 `local/task1-progress-loopback.txt`：1 passed in 0.78s。


## 最终验证结果

- 完整回归：`../ainiee-translate-skill/.venv/Scripts/python.exe -m pytest --basetemp=local/glossary-full-reviewed --tb=short`，**329 passed in 230.46s (0:03:50)**，退出码 0；日志 `local/task1-full-reviewed.txt`。执行许可仅用于现有本机回环进度服务测试，不访问外部网络。
- `git diff --check` 对本任务源码、测试与报告通过，退出码 0。
- 实现提交：`a6aed4e`；独立审核问题修复：`1f74bd6`。
- 产品失败均已修复并完成完整绿色回归。本任务没有已知未解决的重要问题；技能副本同步、交付打包和最终全分支审阅由主控统一负责。
