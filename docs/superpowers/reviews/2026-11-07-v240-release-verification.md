# v2.4.0 发布验收

目标为用户 fork `YanagionSabigi/ainiee-translate-skill`。用户明确要求将
template 合并到 main、同步本机技能、推送并发布；不创建 PR。

- template 原基线为 2.2.0。合并保留 main 的 2.3.0 术语表、出版组件、
  参考模板许可与署名，再纳入本轮已确认的模板、预览和 LaTeX 规则。
- 合并结果完整 Python 回归：334 passed in 211.79s，退出码 0。
  允许本机回环连接后完成测试；原受限环境下的进度服务连接错误未被跳过。
- 前端测试：17 passed，0 failed。
- `build.py --check`、`build_release.py`、`build_release.py --check` 通过。
- wheel 内 37 个模板资源逐字节匹配源码；技能 ZIP 含 LaTeX 规则与
  2.3.0 的通用术语表模块。独立 wheel 路径可导入并定位内置出版组件。
- ZIP 共 314 个技能文件；ZIP、wheel 的 SHA-256 与 release manifest 一致。
- TeX 来源及 PDF 保持本轮已编译验收的版本：三级列表、Dawn Overlay
  浅米粉色陈述底色、白底选项、数译简洁样式。现有预览和分页压力样例
  已检查真实页面、引用、QED、Dawn／白底的同文同分页。

发布资产为技能 ZIP、Python wheel、release-manifest.json、SHA256SUMS。
字体、XeLaTeX 与私人运行目录不随发布包分发。可编辑模板仍独立使用，
不声称已经替换自动导出器；Typst 本轮没有新增模板。

本机安装前将完整旧技能备份到工作区忽略的 `local/skill-backups/`，
安装后按发布 manifest 验证全部文件，再测试实际安装的 module 与 publisher。
安装回执及远程发布回读结果保存在工作区 `local/`。
