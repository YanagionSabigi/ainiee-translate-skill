# Workbench 0.2.0 同步验收 · AiNiee 2.1.2

同步上游 `208e5a9bd15b75ca21a201cd97cfdfd85270c101`（0.2.0 发布后的文档更新），基线为 2.1.1 固定的 `9a3b0d6`。保留 AiNiee 的术语可空字段、微信反馈展示、私有差异临时目录及正式提交后受控写回。

## 界面与启动

- 使用现有原生 HTML/CSS/JS 与纸色、绿色 CSS tokens，无 Tailwind、组件库或前端构建依赖；保持既有浅色界面。
- 目录默认收起，开关移至左上角侧边栏图标；展开时显示“收起目录”，收起时显示“展开目录”，同时更新 title、aria-label 与 aria-expanded。保留键盘焦点样式、窄屏隐藏 AiNiee 前缀和按需展开的条目列表。
- 对外审核包新增 Windows `开始校对.cmd`、macOS `start_review.command`。Python 入口提供 `--check`，缺依赖时显示安装步骤；启动不安装或下载。OPEN-ME.txt 统一说明完整解压、各系统入口、Python/jsonschema/Node 版本、回传方法。
- 完整 skill 和 wheel 保留生成审核包所需的模板；收件人 ZIP 不复制重复模板目录。普通文字仍不带 KaTeX/字体、SKILL、示例或 Git 仓库。

## 实测与验证

沿用私有《氧气》副本重新导出：59,813 字节、27 个文件。Windows CMD 在含中文与空格的路径执行 `--check` 成功（0.391 秒）；同次环境中 Python 服务就绪 0.359 秒，HTTP 返回新版目录按钮。上述为依赖已准备好的单次本机测量，不包含安装或浏览器绘制，也不能直接与 2.1.1 不同执行环境的启动计时比较。

- AiNiee 全套：282 passed（89.45 秒）。第一次受限执行有 1 项本机端口访问被系统禁止；允许测试连接本机服务后全套通过，未修改业务断言。
- 工作台最新 36 项 Python 测试对实际内置运行资源通过（32.710 秒），包括真实 Windows CMD、无依赖指引、macOS ZIP 执行位、迁移与中断恢复。初次兼容运行未向子进程传递 PYTHONPATH，且本机端口受限；修正测试环境后全套通过。
- 7 项 Node 前端逻辑测试通过；没有前端构建步骤。
- 新启动器集成回归先在旧导出因缺少 CMD 失败，合入后通过；既有无 Git 接收端正式提交 → JSON 回传 → 原项目导入 → 业务写回回归继续通过。
- skill ZIP 与 wheel 从中立目录解压后，均实际导出 27 文件精简包并通过接收端环境检查；wheel 含三个启动模板。完整 skill ZIP 为 259 个跟踪文件。
- build.py、build_release.py --check 与技能格式检查通过；独立只读审阅未发现可操作问题。

本轮浏览器自动检查因工具无法可靠识别 Windows 浏览器当前 URL 而停止，未完成桌面/窄屏视觉验收；只验证了服务返回的页面和静态响应式/无障碍代码。macOS 启动入口未在 macOS 真机运行，不声称完成该平台验收。

## 发布与更新范围

AiNiee Release 的 ZIP 是完整技能安装包，保留 SKILL；收件人的具体项目审核 ZIP 由新版重新导出。旧审核 ZIP 不会自动更新。上游已发布的 [0.2.0 演示审核包](https://github.com/YanagionSabigi/review-workbench/releases/download/v0.2.0/review-workbench-demo-0.2.0.zip) 使用公开示例且含公式，供独立体验；不代替 AiNiee 安装包，也不含用户书籍。已核对上游 Release 为正式发布且该附件存在。

私有《氧气》审核 ZIP、解压目录、测试日志与本机安装备份只在忽略的 local 目录中，不能上传为公开 Release 附件。此次仅更新用户自己的 fork 分支，不创建 PR，不向源 fork 的 upstream 推送。
