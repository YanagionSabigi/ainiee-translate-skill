# EPUB 排版参照

先打开 [reference.epub](reference.epub)。这是原创演示，沿用 `assets/book.css`，不增加另一套样式。它从本目录的作者定义 `source.json` 构建，不经过 OCR，也不能作为 PDF 提取、跨页接段或书签识别已经正确的证据。

当前供用户审阅：结构和内容对账已通过。已知现有封面样式在 epub.js 滚动模式会缩小，分页模式完整显示；本次仅按用户反馈将表格整体居中，封面样式未改，不能视为跨阅读器全面验收。

## 应当看到什么

| 项目 | 期望 |
| --- | --- |
| 封面 | 最前方一张完整封面；仅演示素材，不用于填补真实书籍缺失封面 |
| 目录 | 封面之后，两个章、三个下属节；可见目录和导航目标一致 |
| 标题 | 两章独立 XHTML；章标题 1.9em，小节 1.4em，正文 1em |
| 正文插图 | 一张流程图；第一章 `joined-paragraph` 的完整段落及注号之后、`next-paragraph` 之前 |
| 图注 | 图片下方，87.5% 字号，与图片合为一个 figure；正文中不重复 |
| 引文 | 一段由引导语识别，一段显式 quote；仿宋、90% 字号、#79a88a；缺字体时回退衬线 |
| 注释 | 两条注释、两处引用；每章各显示一个“返回原文”；第二章重新从 1 编号 |
| 表格 | 第二章一张整体居中的真实三列表格，表头加三个数据行 |

第一章图片块在输入中故意放在提及段落前，构建后必须移动到完整段落之后。这演示的是**已正确恢复自然段后**的图片定位：真实 PDF 中应先将跨页句段合并为同一 paragraph，再设置 `after_block`。自然段可跨阅读器屏幕；“段后放图”不等于强制一屏容纳整段。

## 重建与核对

```powershell
python assets/template/epub/reference-book/build_example.py
python publication_skill/scripts/pdf_to_epub.py check assets/template/epub/reference-book/reference.epub
```

重建仅需原技能运行环境；素材已附带，无需安装字体或图像生成依赖。示例源 JSON 是手写的 normalized 数据参照；真实转换仍须从源绑定的 `review.json` 执行 normalize，不得照搬示例的 reviewed 标志、空提取记录或已编译 publication 对象跳过审校。

`conversion-report.json` 记录实际图位、注释映射、资源哈希和阅读顺序。独立审核结果与实际阅读器验证范围见 原出版组件的 `docs/audit-20261105.md`。
