"""Independent EPUB 3 publisher. Only publication resources enter the archive."""
from __future__ import annotations

from datetime import datetime, timezone
import html
import os
from pathlib import Path
import tempfile
import zipfile

from lxml import etree

from .book_markdown import validated_assets
from .pdf_publication import compile_publication
from .pdf_protection import TOKEN, validate_protected_tokens

XHTML = 'http://www.w3.org/1999/xhtml'
EPUB = 'http://www.idpf.org/2007/ops'
OPF = 'http://www.idpf.org/2007/opf'
DC = 'http://purl.org/dc/elements/1.1/'


def _text(value):
    return html.escape(str(value), quote=True)


def _styled(text):
    value = _text(text)
    for tag in ('i', 'b'):
        value = value.replace(f'&lt;{tag}&gt;', f'<{tag}>').replace(f'&lt;/{tag}&gt;', f'</{tag}>')
    return value


def _image(asset_id, assets, *, alt='image'):
    if asset_id not in assets:
        raise ValueError('Missing publication image asset')
    _, relative, asset = assets[asset_id]
    width = asset.get('width_em', 20)
    if type(width) not in (int, float) or not 0 < width <= 100:
        raise ValueError('Image needs a finite relative reading width')
    return f'<img src="{_text(relative)}" alt="{_text(alt)}" style="width: {width}em; max-width: 100%;"/>'


def _math(node, assets, *, display=False):
    if node.get('verified') is True and node.get('tex'):
        try:
            from latex2mathml.converter import convert
            return convert(node['tex'], display='block' if display else 'inline')
        except (ImportError, Exception) as exc:
            if not node.get('fallback_reason') or node.get('asset_id') not in assets:
                raise ValueError('Verified TeX could not be serialized as offline MathML; provide an evidenced source crop fallback') from exc
    if node.get('fallback_reason') and node.get('asset_id') in assets:
        return _image(node['asset_id'], assets, alt='formula')
    raise ValueError('Formula needs verified TeX or an exact source image fallback')


def _inline(block, assets):
    text = block.get('target_text', '')
    if block.get('unit_id') and not text.strip():
        raise ValueError('Missing target translation')
    if not block.get('diagnostic_missing') and validate_protected_tokens(block.get('source_text', ''), text, expected=block.get('protected_tokens', [])):
        raise ValueError('Damaged inline structure tokens')
    parts, last = [], 0
    for match in TOKEN.finditer(text):
        parts.append(_styled(text[last:match.start()]))
        node = block.get('inlines', {}).get(match[0])
        if node is None:
            raise ValueError('Unknown inline payload')
        kind = node['kind']
        if kind == 'literal': value = _text(node['text'])
        elif kind == 'math': value = _math(node, assets)
        elif kind == 'code': value = '<code>' + _text(node['text']) + '</code>'
        elif kind == 'image': value = _image(node['asset_id'], assets)
        elif kind == 'note':
            value = (f'<a class="noteref" epub:type="noteref" role="doc-noteref" '
                     f'id="{_text(node["ref_id"])}" href="#{_text(node["note_id"])}">{node["number"]}</a>')
        else: raise ValueError(f'Unsupported inline kind: {kind}')
        parts.append(value); last = match.end()
    parts.append(_styled(text[last:]))
    return ''.join(parts)


def _block(block, blocks, assets):
    bid, kind = _text(block['id']), block['kind']
    if kind in ('paragraph', 'note', 'caption', 'heading', 'table-cell'):
        tag = 'h' + str(max(1, min(6, block.get('level', 2)))) if kind == 'heading' else 'p'
        return f'<{tag} id="{bid}" class="{kind}">{_inline(block, assets)}</{tag}>'
    if kind == 'figure':
        return f'<div id="{bid}" class="figure">{_image(block["asset_id"], assets, alt="figure")}</div>'
    if kind == 'formula':
        return f'<div id="{bid}" class="formula">{_math(block, assets, display=True)}</div>'
    if kind == 'code':
        return f'<pre id="{bid}"><code>{_text(block["code"])}</code></pre>'
    if kind == 'table':
        rows = block['rows']
        if not rows or any(len(r) != len(rows[0]) for r in rows):
            raise ValueError('Table requires rectangular semantic cells')
        content = ''.join('<tr>' + ''.join(f'<td id="{_text(cell)}">{_inline(blocks[cell], assets)}</td>' for cell in row) + '</tr>' for row in rows)
        return f'<table id="{bid}"><tbody>{content}</tbody></table>'
    raise ValueError(f'Unsupported semantic block: {kind}')


def _toc(book, *, visible):
    entries = book['toc']['entries']
    if visible:
        return '<div id="contents"><h1>Contents</h1>' + ''.join(
            f'<div class="contents-level-{e["level"]}"><a href="{e["chapter_id"]}.xhtml#{e["target"]}">{_text(e["display_title"])}</a></div>' for e in entries) + '</div>'
    out, children = [], []
    for entry in entries:
        link = f'<a href="{entry["chapter_id"]}.xhtml#{entry["target"]}">{_text(entry["display_title"])}</a>'
        if entry['level'] == 1:
            if children: out[-1] += '<ol>' + ''.join(children) + '</ol>'; children = []
            if out: out[-1] += '</li>'
            out.append('<li>' + link)
        else:
            children.append('<li>' + link + '</li>')
    if children: out[-1] += '<ol>' + ''.join(children) + '</ol>'
    if out: out[-1] += '</li>'
    return '<nav epub:type="toc" id="toc"><h1>Contents</h1><ol>' + ''.join(out) + '</ol></nav>'


def _xhtml(title, body, language):
    value = (f'<?xml version="1.0" encoding="utf-8"?><!DOCTYPE html>'
             f'<html xmlns="{XHTML}" xmlns:epub="{EPUB}" lang="{_text(language)}" xml:lang="{_text(language)}">'
             f'<head><title>{_text(title)}</title><link rel="stylesheet" type="text/css" href="book.css"/></head>'
             f'<body>{body}</body></html>')
    etree.fromstring(value.encode(), etree.XMLParser(resolve_entities=False, no_network=True))
    return value.encode('utf8')


def export_epub(book, output_path: Path) -> Path:
    book = compile_publication(book)
    assets = validated_assets(book)
    blocks = {b['id']: b for b in book['blocks']}
    notes = {n['id']: n for n in book['notes']}
    note_bodies = {bid for n in notes.values() for bid in n['block_ids']}
    cells = {cell for b in blocks.values() if b['kind'] == 'table' for row in b['rows'] for cell in row}
    language, title = book['metadata'].get('language'), book['metadata'].get('title')
    if not language or not title:
        raise ValueError('EPUB requires title and language metadata')
    documents = {}
    placement = book['toc']['placement']
    for chapter in book['chapters']:
        body = f'<section id="{chapter["id"]}" epub:type="chapter">'
        if book.get('diagnostic_draft'): body += '<p>DIAGNOSTIC DRAFT: incomplete translation</p>'
        if not chapter.get('title_block_id'): body += '<h1>' + _text(chapter['display_title']) + '</h1>'
        for block in book['blocks']:
            if block['chapter_id'] == chapter['id'] and block['id'] not in note_bodies | cells:
                if placement.get('before_block') == block['id']:
                    body += _toc(book, visible=True)
                body += _block(block, blocks, assets)
        if chapter['note_order']:
            body += '<section epub:type="endnotes" class="notes"><h2>Notes</h2>'
            for nid in chapter['note_order']:
                note = notes[nid]
                body += f'<aside id="{nid}" epub:type="endnote" role="doc-endnote"><p>{note["number"]}.</p>'
                body += ''.join(_block(blocks[bid], blocks, assets) for bid in note['block_ids'])
                body += ''.join(f'<a href="#{rid}" role="doc-backlink">↩</a> ' for rid in note['references']) + '</aside>'
            body += '</section>'
        body += '</section>'
        documents[chapter['id']] = (chapter['id'] + '.xhtml', _xhtml(chapter['display_title'], body, language))
    for entry in book['publication_order']:
        if entry['kind'] == 'front-image':
            documents[entry['id']] = (entry['id'] + '.xhtml', _xhtml(entry['role'], '<div class="front-image">' + _image(entry['asset_id'], assets, alt=entry['role']) + '</div>', language))
        elif entry['kind'] == 'toc':
            documents['visible-toc'] = ('toc.xhtml', _xhtml('Contents', _toc(book, visible=True), language))
    documents['navigation'] = ('nav.xhtml', _xhtml('Contents', _toc(book, visible=False), language))
    package = etree.Element(f'{{{OPF}}}package', nsmap={None: OPF, 'dc': DC}, version='3.0', attrib={'unique-identifier': 'book-id'})
    metadata = etree.SubElement(package, f'{{{OPF}}}metadata')
    for name, value in [('identifier', book['metadata'].get('identifier') or 'urn:sha256:' + book['source_sha256']), ('title', title), ('language', language)]:
        e = etree.SubElement(metadata, f'{{{DC}}}{name}'); e.text = value
        if name == 'identifier': e.set('id', 'book-id')
    etree.SubElement(metadata, f'{{{OPF}}}meta', property='dcterms:modified').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
    manifest = etree.SubElement(package, f'{{{OPF}}}manifest')
    for did, (filename, content) in documents.items():
        props = (['nav'] if did == 'navigation' else []) + (['mathml'] if b'<math' in content else [])
        item = etree.SubElement(manifest, f'{{{OPF}}}item', id=did, href=filename, attrib={'media-type': 'application/xhtml+xml'})
        if props: item.set('properties', ' '.join(props))
    etree.SubElement(manifest, f'{{{OPF}}}item', id='book-style', href='book.css', attrib={'media-type': 'text/css'})
    for aid, (_, relative, asset) in assets.items():
        item = etree.SubElement(manifest, f'{{{OPF}}}item', id='asset-' + aid, href=relative, attrib={'media-type': asset['media_type']})
        if asset.get('role') == 'cover': item.set('properties', 'cover-image')
    spine = etree.SubElement(package, f'{{{OPF}}}spine')
    for entry in book['publication_order']: etree.SubElement(spine, f'{{{OPF}}}itemref', idref=entry['id'])
    output_path = Path(output_path); output_path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix='.epub-', suffix='.epub', dir=output_path.parent); os.close(fd)
    try:
        with zipfile.ZipFile(temp, 'w', zipfile.ZIP_DEFLATED) as z:
            z.writestr('mimetype', b'application/epub+zip', compress_type=zipfile.ZIP_STORED)
            z.writestr('META-INF/container.xml', b'<?xml version="1.0"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>')
            z.writestr('EPUB/package.opf', etree.tostring(package, xml_declaration=True, encoding='utf-8'))
            z.writestr('EPUB/book.css', Path(__file__).with_name('assets').joinpath('book.css').read_bytes())
            for filename, content in documents.values(): z.writestr('EPUB/' + filename, content)
            for path, relative, _ in assets.values(): z.write(path, 'EPUB/' + relative)
        from .book_check import check_epub
        result = check_epub(Path(temp))
        if result['structure']['status'] != 'passed':
            raise ValueError('EPUB structure check failed: ' + '; '.join(result['structure']['issues']))
        os.replace(temp, output_path)
    finally:
        Path(temp).unlink(missing_ok=True)
    return output_path
