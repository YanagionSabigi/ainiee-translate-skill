"""Invented bilingual EPUB with repeat/Unicode/cross-paragraph test cases."""
from pathlib import Path
import zipfile
from ainiee_translate.cache_io import save_cache
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheProject import CacheProject
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheFile import CacheFile
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheItem import CacheItem

SOURCES = [
    'The river remembers every stone.',
    'A quiet lamp lights the window.',
    'The first half ends here.',
    'The next half begins here.',
    'The river remembers every stone.',
    'A <i>careful</i> reader sees café 😀 and a new path.',
    'The formula is x² + y² = z²; see note [1].',
    '[1] This is an invented note, not a quotation.',
]
TARGETS = [
    '河流记得每一块石头。',
    '一盏安静的灯照着窗户。',
    '前半句在这里结束。',
    '后半句从这里开始。',
    '河流记得每一块石头。',
    '一位<i>仔细</i>的读者看见 café 😀 和一条新路。',
    '公式是 x² + y² = z²；参见注 [1]。',
    '[1] 这是自造脚注，并非引文。',
]

def epub(path, texts):
    with zipfile.ZipFile(path, 'w') as z:
        z.writestr('mimetype', 'application/epub+zip', compress_type=zipfile.ZIP_STORED)
        z.writestr('META-INF/container.xml', '<?xml version="1.0"?><container xmlns="urn:oasis:names:tc:opendocument:xmlns:container" version="1.0"><rootfiles><rootfile full-path="OEBPS/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
        z.writestr('OEBPS/package.opf', '''<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">urn:uuid:ce507821-47cc-493d-a681-08b9ef37a401</dc:identifier><dc:title>AiNiee 校对测试 2026</dc:title><dc:language>zh-CN</dc:language><meta property="dcterms:modified">2026-10-18T00:00:00Z</meta></metadata><manifest><item id="c1" href="c1.xhtml" media-type="application/xhtml+xml"/><item id="c2" href="c2.xhtml" media-type="application/xhtml+xml"/><item id="nav" href="nav.xhtml" media-type="application/xhtml+xml" properties="nav"/></manifest><spine><itemref idref="c1"/><itemref idref="c2"/></spine></package>''')
        for ch, subset in [(1, texts[:4]), (2, texts[4:])]:
            body = ''.join(f'<p id="p{i}">{t}</p>' for i, t in enumerate(subset))
            z.writestr(f'OEBPS/c{ch}.xhtml', f'<html xmlns="http://www.w3.org/1999/xhtml" lang="zh-CN"><head><title>同名章节</title></head><body><h1>同名章节</h1>{body}</body></html>')
        z.writestr('OEBPS/nav.xhtml', '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="zh-CN"><head><title>目录</title></head><body><nav epub:type="toc"><h1>目录</h1><ol><li><a href="c1.xhtml">同名章节</a></li><li><a href="c2.xhtml">同名章节</a></li></ol></nav></body></html>')

def create_project(root):
    root = Path(root); root.mkdir(parents=True, exist_ok=True)
    (root / 'input').mkdir(exist_ok=True)
    epub(root / 'input/source.epub', SOURCES)
    epub(root / 'reading.epub', TARGETS)
    items = [CacheItem(text_index=i+1, source_text=s, translated_text=t, translation_status=2,
                       extra={'item_id': 'c1' if i < 4 else 'c2', 'tag_type': 'p',
                              'original_html': f'<p id="p{i % 4}">{s}</p>'})
             for i, (s, t) in enumerate(zip(SOURCES, TARGETS))]
    project = CacheProject(project_id='synthetic-reading-2026', project_type='Epub',
                           input_path=str(root / 'input'),
                           files={'source.epub': CacheFile(storage_path='source.epub', file_project_type='Epub', items=items)})
    save_cache(project, str(root / 'cache.json'))
    (root / 'glossary.json').write_text('{}', encoding='utf8')
    (root / 'prompt.md').write_text('忠实清楚；保留强调、公式和脚注。', encoding='utf8')
    return root
