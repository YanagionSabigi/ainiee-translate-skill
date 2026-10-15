// Original Typst layout; palette follows the attributed Rosé Pine Dawn reference.
#let title = @@title@@
#let author = @@author@@
#let translator = @@translator@@
#let text-color = rgb("575168")
#let pine-color = rgb("286983")
#let rose-color = rgb("d7827e")
#let overlay-color = rgb("f2e9e1")
#set document(title: title, author: author)
#set page(paper: @@page_size@@, margin: @@margin_mm@@mm, numbering: @@page_numbering@@)
#set text(font: (@@font_latin@@, @@font_cjk@@), size: @@font_size@@pt, lang: @@typst_language@@, region: @@typst_region@@, fill: text-color)
#set par(justify: true, leading: .65em, spacing: .7em)
#show raw: set text(font: @@font_mono@@)
#show link: set text(fill: rgb("b4637a"))
#show heading.where(level: 1): it => {
  v(1em)
  text(size: 1.8em, weight: "bold", fill: pine-color, it.body)
  v(.4em)
  line(length: 100%, stroke: 1.5pt + rose-color)
  v(.8em)
}
#show heading.where(level: 2): set text(size: 1.3em, fill: pine-color)
#let book-cover(title, author, translator) = {
  set page(fill: rgb("faf4ed"), numbering: none)
  line(length: 100%, stroke: 1.5pt + rose-color)
  v(1fr)
  align(center)[
    #text(size: 28pt, weight: "bold", title)
    #v(1em)
    #text(size: 16pt, fill: rgb("907aa9"), translator)
    #v(1em)
    #line(length: 55%, stroke: 1pt + rose-color)
    #v(1em)
    #text(size: 14pt, fill: pine-color, author)
  ]
  v(1fr)
  line(length: 100%, stroke: 1.5pt + pine-color)
}
@@title_page@@
@@draft@@
@@body@@
