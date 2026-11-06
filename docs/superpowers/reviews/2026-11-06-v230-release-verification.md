# v2.3.0 发布候选验收

目标是用户的 fork `YanagionSabigi/ainiee-translate-skill`，不创建 PR、不向 upstream 推送。版本 `2.3.0`，包含已验收术语表与原 template checkout 的出版升级和四套 PDF 模板；原 checkout 文件及暂存状态保留。

- 完整 Python 测试：334 passed in 221.93s，退出码 0，含本机回环服务测试。
- 前端：17 passed，0 failed。
- `build.py --check`、`build_release.py` 和 `build_release.py --check` 通过。
- 真实 wheel 红验证先确认原 package-data 漏掉全部四个 main.tex，补齐后 ZIP／wheel 均实际包含四套 TeX/PDF、Schema、MathTranslations 和 Rosé Pine 的许可文件。
- 四套独立示例分别编译两遍，book 各 10 页、article 各 4 页；无缺字、溢出或未解析引用。对随包 PDF 的 28 页完成渲染浏览。
- 发布包含 308 个技能文件，逐项 SHA-256 与 manifest 一致。解包后的技能实际创建 A 模式空分类 module、读取政策快照成功。
- 独立模板／出版组件审核已完成；漏署名与陈旧说明已经补正，私人样书名称已从发行说明移除，缺失审阅链接和不适用测试命令已修复。

资源：`dist/ainiee-translate-v2.3.0.zip`、`dist/ainiee_translate-2.3.0-py3-none-any.whl`、`dist/release-manifest.json`、`dist/SHA256SUMS`，四者随 GitHub Release 发布。完整日志、导入哈希、PDF 渲染及本机安装备份保存在工作区忽略的 `local/`。

这些新模板是独立可编辑素材，不声称已替换自动导出器；原自动 LaTeX／Typst 路径继续保留。字体与编译器不捆绑发布。

## 发布与本机安装结果

已合并 main 并推送用户 fork，同时同步已有 release 更新入口。`v2.3.0` 标签指向合并提交 `63c1835da097e0c9e372f99e4b1bcaf0d7781c07`；发布时远端 main、release 和标签的目标一致。随后仅补记本节及计划状态，不改发布代码或技能资产。

正式 Release：[v2.3.0](https://github.com/YanagionSabigi/ainiee-translate-skill/releases/tag/v2.3.0)，非草稿、非预发行。四个资产下载回读后与本地核验文件逐字节一致。

本机 Codex 的 AiNiee-translate 技能已用最终 ZIP 更新到 2.3.0，308 个文件与发布 manifest 的 SHA-256 一致。旧技能完整移至本工作区 `local/skill-backups/`，没有删除。实际安装目录的 module 创建／加载、默认 D 空分类和内置出版组件定位冒烟通过；执行回执在 `local/v230-installed-receipt.json`。

没有创建 PR，没有向 upstream 推送；原 template checkout 的文件和暂存状态仍保留。
