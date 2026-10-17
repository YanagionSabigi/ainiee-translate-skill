"""Portable Markdown serialization of the target book; never reparses source PDF."""
from __future__ import annotations

import html
from pathlib import Path
import re
import shutil

from .book_model import BookDocument, validate_book
from .artifact_io import safe_relative, sha256, write_json
from .pdf_protection import TOKEN, validate_protected_tokens


def validated_assets(book: BookDocument):
    root = Path(book['provenance']['work']).resolve()
    assets = {}
    for asset in book.get('assets', []):
        path = root / safe_relative(asset['path'])
        if not path.resolve().is_relative_to(root) or not path.is_file() or sha256(path) != asset['sha256']:
            raise ValueError(f'Missing or changed publication asset: {asset["id"]}')
        assets[asset['id']] = (path, f"assets/{asset['id']}{path.suffix.lower()}", asset)
    return assets


def _escape(text: str):
    escaped = html.escape(text, quote=False)
    escaped = re.sub(r'([\\`*_{}\[\]|])', r'\\\1', escaped)
    for tag, marker in (('i', '*'), ('b', '**')):
        escaped = escaped.replace(f'&lt;{tag}&gt;', marker).replace(f'&lt;/{tag}&gt;', marker)
    return escaped


def render_inline(block, assets):
    text = block.get('target_text', '')
    if block.get('unit_id') and not text.strip():
        raise ValueError('Missing target translation')
    expected = block.get('protected_tokens', [])
    if not block.get('diagnostic_missing') and validate_protected_tokens(block.get('source_text', ''), text, expected=expected):
        raise ValueError('Damaged protected translation tokens')
    def inline(match):
        node = block.get('inlines', {}).get(match[0])
        if node is None:
            raise ValueError('Unknown protected inline payload')
        kind = node['kind']
        if kind in ('literal','styled'):
            text=html.escape(node['text'],quote=False)
            text=re.sub(r'([\\`*_{}\[\]|])',r'\\\1',text)
            for style in node.get('styles',[]):
                tag={'bold':'strong','italic':'em','sup':'sup','sub':'sub','underline':'u','emphasis-dot':'u'}[style]
                text=f'<{tag}>'+text+f'</{tag}>'
            return text
        if kind == 'math':
            if node.get('verified') is True and node.get('tex'):
                return '$' + node['tex'] + '$'
            if node.get('fallback_reason') and node.get('asset_id') in assets:
                return f"![formula]({assets[node['asset_id']][1]})"
            raise ValueError('Formula requires source-verified TeX or evidenced image fallback')
        if kind == 'reference':
            return f'<a id="{node["ref_id"]}"></a>' + ', '.join(f'[{_escape(node.get("text","") or target)}](#{target})' for target in node['targets'])
        if kind == 'note':
            return f'<a id="{node["ref_id"]}"></a>[{node["number"]}](#{node["note_id"]})'
        if kind == 'code':
            fence = '`' * (max((len(m[0]) for m in re.finditer(r'`+', node['text'])), default=0) + 1)
            return fence + ' ' + node['text'] + ' ' + fence
        if kind == 'image' and node.get('asset_id') in assets:
            return f"![image]({assets[node['asset_id']][1]})"
        raise ValueError(f'Unsupported protected inline kind: {kind}')
    parts, last = [], 0
    for match in TOKEN.finditer(text):
        parts.extend([_escape(text[last:match.start()]), inline(match)])
        last = match.end()
    return ''.join(parts) + _escape(text[last:])


def _render_block(block, by_id, assets):
    kind = block['kind']
    if kind in ('paragraph', 'caption', 'table-cell', 'note','quote','verse'):
        return render_inline(block, assets)
    if kind == 'heading':
        return '#' * max(1, min(6, block.get('level', 2))) + ' ' + render_inline(block, assets)
    if kind == 'figure':
        if block.get('asset_id') not in assets:
            raise ValueError('Figure asset is missing')
        return f"![figure]({assets[block['asset_id']][1]})"
    if kind == 'formula':
        if block.get('verified') is True and block.get('tex'):
            return '$$\n' + block['tex'] + '\n$$'
        if block.get('fallback_reason') and block.get('asset_id') in assets:
            return f"![formula]({assets[block['asset_id']][1]})"
        raise ValueError('Formula requires verified TeX or source image fallback')
    if kind == 'table':
        rows = [[render_inline(by_id[cell], assets) for cell in row] for row in block['rows']]
        if not rows or any(len(row) != len(rows[0]) for row in rows):
            raise ValueError('Table must have nonempty rectangular rows')
        lines = ['| ' + ' | '.join(row) + ' |' for row in rows]
        lines.insert(1, '| ' + ' | '.join('---' for _ in rows[0]) + ' |')
        return '\n'.join(lines)
    if kind == 'code':
        code = block['code']
        fence = '`' * max(3, max((len(m[0]) + 1 for m in re.finditer(r'`+', code)), default=3))
        return fence + '\n' + code + '\n' + fence
    raise ValueError(f'Unsupported semantic block kind: {kind}')


def render_markdown(book: BookDocument) -> str:
    validate_book(book, require_translation=True)
    from .pdf_publication import compile_publication
    book = compile_publication(book)
    assets = validated_assets(book)
    by_id = {b['id']: b for b in book['blocks']}
    note_bodies = {bid for note in book.get('notes', []) for bid in note['block_ids']}
    cells = {cell for b in book['blocks'] if b['kind'] == 'table' for row in b['rows'] for cell in row}
    lines = ['<!-- DIAGNOSTIC DRAFT: incomplete translation -->'] if book.get('diagnostic_draft') else []
    def contents():
        return '\n\n'.join('  ' * (entry['level'] - 1) + f"[{_escape(entry['display_title'])}](#{entry['target']})" for entry in book['toc']['entries'])
    chapters = {chapter['id']: chapter for chapter in book['chapters']}
    for entry in book['publication_order']:
        if entry['kind'] == 'front-image':
            lines.append(f"![{entry['role']}]({assets[entry['asset_id']][1]})")
            continue
        if entry['kind'] == 'toc':
            lines.append(contents())
            continue
        chapter = chapters[entry['id']]
        lines.append(f'<a id="{chapter["id"]}"></a>')
        if not chapter.get('title_block_id'):
            lines.append('# ' + _escape(chapter.get('display_title') or chapter.get('title') or chapter['source_title']))
        def returns(ident):
            return ' '.join(f'[返回 {i+1}](#{rid})' for i,rid in enumerate(book.get('reference_returns',{}).get(ident,[])))
        if returns(chapter['id']): lines.append(returns(chapter['id']))
        for block in book['blocks']:
            if block['chapter_id'] == chapter['id'] and block['id'] not in note_bodies | cells:
                if book['toc']['placement'].get('before_block') == block['id']:
                    lines.append(contents())
                lines.extend([f'<a id="{block["id"]}"></a>', _render_block(block, by_id, assets)])
                if returns(block['id']): lines.append(returns(block['id']))
        for note in book.get('notes', []):
            if note['chapter_id'] == chapter['id']:
                body = '\n\n'.join(_render_block(by_id[bid], by_id, assets) for bid in note['block_ids'])
                lines.append(f'<a id="{note["id"]}"></a>' + str(note['number']) + '. ' + body + ' ' + ' '.join(f'[返回 {i+1}](#{rid})' for i,rid in enumerate(note['references'])))
    return '\n\n'.join(lines) + '\n'


def export_markdown(book: BookDocument, output_dir: Path, *, manifest=None, work=None) -> Path:
    from .rendering_view import rendering_view
    book=rendering_view(book,manifest=manifest,work=work,asset_dir=Path(output_dir)/'.render-assets')
    text = render_markdown(book)
    assets = validated_assets(book)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, relative, _ in assets.values():
        target = output_dir / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(path, target)
    name = 'book.draft.md' if book.get('diagnostic_draft') else 'book.md'
    output = output_dir / name
    output.write_text(text, encoding='utf8')
    if book.get('diagnostic_draft'):
        write_json(output_dir / 'missing-units.json', book.get('missing_units', []))
    return output
