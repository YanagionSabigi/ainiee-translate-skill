# 微信读书校对验收（2026-10-18）

实施分支 `feat/weread-proofreading`，起点 `df72461`。仅本地开发、提交、构建和验收；不推送、不 PR、不发布、不替换全局 skill。

## 官方与账号

已读取 Tencent/WeChatReading 的 [README](https://github.com/Tencent/WeChatReading)、[SKILL](https://github.com/Tencent/WeChatReading/blob/main/skills/SKILL.md)、[notes](https://github.com/Tencent/WeChatReading/blob/main/skills/notes.md)、[shelf](https://github.com/Tencent/WeChatReading/blob/main/skills/shelf.md)，当前文档版本 1.0.5。本地文档副本在忽略目录 `local/weread-validation/official-skill/`，版本从文档读取。

用户已配合真实账号验收，密钥仅从本机用户环境读取。通过真实书架选择两本导入书，读取各自划线及全部返回的个人想法页；没有写入手机书籍。原始响应、书籍、报告、截图及 PDF 原页证据均留在忽略的 `local/`，不随代码提交。

| 账号观察 | 结果与边界 |
|---|---|
| 自导入 EPUB 可见性 | 通过书架确认实际导入书 ID；未用书城同名书替代 |
| 蓝色波浪线 | 用户核对真实样式为整数 `colorStyle=3`；与字符串 `"3"` 区分 |
| 其他样式 | 实际出现 1、4、5；用户确认跨段第二轮 4 为绿色高亮，第三轮改为蓝色后为 3；绿色未混入蓝色队列 |
| 有/无想法、多想法 | 均读到；同一划线新增第二条想法后沿用编号并增加 annotation_revision |
| 跨段、Unicode 与强调 | 中文跨段无分隔符摘录精确回映两段；café、emoji、强调保留；重复句用已核验章节或逐字上下文定址 |
| 重复同步 | 第三轮重复导入完全幂等；新增蓝色项追加编号，已应用项保持原状态 |
| 删除 | 用户删除后原项在后续快照中缺失；全量/增量删除语义仍未验证，保留 missing_unconfirmed，不标成已确认 tombstone |
| 关联与 range | 验证可用字段的精确相等关联；歧义保留待关联审计；微信 range 的计数单位及偏移含义未验证，不作为本地字符偏移 |
| 编辑已有想法 | 本次手机操作实际新增了一条想法，未验证原 review ID 编辑行为；离线回归另覆盖编辑导致版本失效 |

真实源自 PDF 的项目读到 8 处蓝色划线和 8 条想法，形成 8 项辨析及 1 项独立扩展发现。实际查看对应原 PDF 的 9 个物理页，记录可见印刷页码；文字建议与字体/颜色请求分别说明。只在工作区副本形成报告，原项目 cache 哈希仍与初始绑定一致，未执行其自定义脚本或写回。

自造测试书完成三轮快照、颜色变化、删除观察和一次真实聊天批复：用户明确选择第二轮报告第 3 条 C，仅写入本地测试缓存；事务结果 `applied=1, conflicts=0`，第三轮同步保持已应用。批复绑定原 report/assessment/annotation revision，旧报告完整保留。测试书仍有待批准、缺失待确认项目，未伪造整本已读完或交付其阶段 EPUB。

## 基线

- `.venv/Scripts/python.exe -m pytest --basetemp local/pytest-weread-baseline`：沙箱内 167 passed / 1 failed，失败为 `test_progress.py::test_serve_endpoints`，WinError 10013。
- 同一 HTTP 测试在主机权限下执行：1 passed（0.73s），证实为沙箱 socket 限制。
- `.venv/Scripts/python.exe build.py --check`：退出码 0，源码与 bundle 一致。

## 实施证据

- Task 1：7 个冻结测试先因缺少模块失败，实施后 7 passed。覆盖冻结字节不变、禁止覆盖、错书/错译稿/空译文拒绝、spine、重复句和 PDF 单元身份。
- Task 2—7 已实现：只读网关、版本化同步、精确定位、agent 辨析契约、静态报告、报告绑定批复、锁内 CAS、事务恢复/撤回和整本出版闸门；CLI、skill 路由和 bundle 已接通。
- 独立代码审查发现的 11 项问题均补充回归并修复：冲突处理、恢复投影、后批复覆盖前批复、同目标幂等、工作稿漂移、锁内身份、跨颜色想法歧义、墓碑保持、同 XHTML 重复候选、PDF 出版参数隔离及 preserve_source 校验。
- 真实项目接入补充 PDF 行内片段、现有阅读版省略规则的精确哈希绑定、局部用户方案及待关联想法的显式解析。没有对应证据的省略或重解析仍拒绝。
- Skill 行为检查：改造前无微信校对入口；改造后能走新流程、拒绝含糊授权、拒绝旧推荐偷换以及阶段导出。

| 需求 | 证据 |
|---|---|
| R01—R02 | EPUB/PDF 冻结与来源测试；真实两类项目；冻结字节不随写回改变 |
| R03、R08、R11 | 真实三轮样式/关联/跨段观察；合成编辑、删除、歧义及幂等回归；未知能力保持未知 |
| R04—R06 | A/B/C、部分用户方案、独立扩展发现测试；真实 PDF 辨析及桌面报告 |
| R07 | 真实原 PDF 页面渲染并查看；PDF proof 失效与 publication manifest 集成回归 |
| R09—R10 | 真实单条聊天批准写回；过期、重叠、锁内 CAS、恢复和撤回回归 |
| R12 | 自造整本链路实际导出并通过结构检查和正式 EPUBCheck；真实项目未满足整本完成闸门 |

## 分开的验收结论

- **自动化回归**：`.venv/Scripts/python.exe -m pytest --basetemp local/pytest-weread-release-final` 在主机权限下完成，**255 passed（58.45s）**，日志 `local/weread-release-final.log`。localhost 测试需主机 socket 权限，不能把沙箱的 WinError 10013 当成功。
- **打包与 skill**：`build.py --check`、standalone/release archive 测试、从中立目录运行 bundle CLI；skill-creator quick_validate 使用 UTF-8。
- **HTML 视觉**：浏览器实际查看 1280/1920 桌面宽度；真实长段折叠、推荐全文、全部想法、状态与跨段选区可读。截图仅存本地。
- **正式 EPUBCheck**：最终代码自造整本项目 `local/reading-projects/offline-release-final/`，实际既有 exporter 与 EPUBCheck 5.4.0 均 passed，finalization 的 validation_mode 明确为 synthetic；不代替账号或 PDF 模板验收。
- **PDF 模板**：本次未请求生成模板 PDF，没有声称真实编译通过；出版集成测试仅对编译器及最终检查使用替身，其余 PDF manifest/export 调用为真实执行。
- **真实整本交付**：尚未进行。须用户明确读完、后续完整同步、全部未决项解决及最新 PDF 出版校对证据齐备；当前账号完整性未知仍构成闸门，不能用合成结果绕过。

本次仅保留本地 `feat/weread-proofreading` 分支及工作区内验收资料；无远端上传、PR、Release 或全局安装。
