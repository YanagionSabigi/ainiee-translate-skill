# 微信读书兼容示例

[打开 compatible.epub](compatible.epub)。这是原创合成内容，由 `source.json` 和生产构建/修复命令生成，不含《区判》正文或账号资料。通用封面、图文排版参照仍见 [reference-book](../reference-book/README.md)。

示例有两章、两个下属节。第一章在已有“第二节”前分成两个文件，TOC条目不增加；同一注释在分片两侧各被引用一次，章末注释有两个“返回原文”，其中一个跨文件。第二章重新从1编号。引文与右对齐署名在同一无灰底容器，淡绿仿宋样式保留；表格单元格的底色保留。

重建时先构建正文，在临时原稿中加入作者定义的灰底容器，再通过 `repair(... plain_callouts=True, split_at=...)` 生成最终示例。临时原稿不交付，输出不含本机路径。小示例故意主动分片以演示关系，不证明微信读书的大小阈值。

```powershell
python assets/template/epub/weread-compat/build_example.py
python publication_skill/scripts/pdf_to_epub.py check assets/template/epub/weread-compat/compatible.epub
```

应核对：nav与NCX同序同层级；目录只有两章和两个节，没有注号；引用1有两处返回，第二章重置1；引文及署名连续保留；语义表格可读。源稿是作者定义的 normalized 数据，真实PDF仍须源文审校。

本示例的本地检查和独立审核见 原出版组件的 `docs/weread-example-audit.md`。原书《区判》的手机结果不替代这个示例的手机导入结果。
