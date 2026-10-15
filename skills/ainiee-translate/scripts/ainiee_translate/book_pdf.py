"""Optional, local book typesetting from the reviewed translated model."""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from .book_markdown import validated_assets
from .book_model import BookDocument
from .mineru_local import sha256, write_json
from .pdf_protection import TOKEN, validate_protected_tokens
from .pdf_publication import compile_publication

TEMPLATES = Path(__file__).parent / 'templates/book'


def _executable(name):
    path = os.environ.get('AINIEE_' + name.upper()) or shutil.which(name)
    if not path or not Path(path).is_file():
        raise FileNotFoundError(f'{name} unavailable; install locally or set AINIEE_{name.upper()}')
    return str(Path(path).resolve())


def _typst_math(formulas):
    """Use Pandoc's actual math parser/writer, never a textual TeX rewrite."""
    if not formulas:
        return {}
    try:
        exe = _executable('pandoc')
        probe = subprocess.run([exe, '--from=markdown', '--to=json'], input='', text=True,
                               encoding='utf8', capture_output=True, timeout=30)
        if probe.returncode or probe.stderr.strip():
            raise ValueError(probe.stderr)
        version = json.loads(probe.stdout)['pandoc-api-version']
        result = {}
        for tex in dict.fromkeys(formulas):
            doc = {'pandoc-api-version': version, 'meta': {}, 'blocks': [
                {'t': 'Para', 'c': [{'t': 'Math', 'c': [{'t': 'InlineMath'}, tex]}]}]}
            proc = subprocess.run([exe, '--from=json', '--to=typst', '--wrap=none'],
                                  input=json.dumps(doc), text=True, encoding='utf8',
                                  capture_output=True, timeout=30)
            converted = proc.stdout.strip()
            if proc.returncode or proc.stderr.strip() or not (converted.startswith('$') and converted.endswith('$')):
                raise ValueError(proc.stderr or 'Math writer did not produce a Typst equation')
            result[tex] = converted
        return result
    except (OSError, subprocess.SubprocessError, KeyError, json.JSONDecodeError, ValueError) as exc:
        raise ValueError(f'Pandoc Typst math conversion failed: {exc}') from exc


def _settings(book, overrides):
    settings = json.loads((TEMPLATES / 'book.defaults.yaml').read_text(encoding='utf8'))
    settings.update({k: v for k, v in book.get('metadata', {}).items() if k in ('title', 'author', 'language')})
    if not isinstance(overrides, dict) or set(overrides) - set(settings):
        raise ValueError('Unknown template setting')
    settings.update(overrides)
    for key, value in settings.items():
        if key in ('margin_mm', 'font_size'):
            lo, hi = (10, 40) if key == 'margin_mm' else (8, 18)
            if type(value) not in (int, float) or not lo <= value <= hi:
                raise ValueError(f'Invalid template setting: {key}')
        elif key in ('toc', 'page_numbers'):
            if type(value) is not bool:
                raise ValueError(f'Invalid template setting: {key}')
        elif not isinstance(value, str) or not value.strip() or len(value) > 500 or any(ord(c) < 32 for c in value):
            # Empty author/translator are useful for anonymous works.
            if not (key in ('author', 'translator') and value == ''):
                raise ValueError(f'Invalid template setting: {key}')
    if settings['page_size'] not in ('a4', 'a5', 'letter'):
        raise ValueError('Invalid template setting: page_size')
    if not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z]{4})?(?:-[A-Za-z]{2})?', settings['language']):
        raise ValueError('Invalid template setting: language')
    return settings


def _tex(text):
    escapes = {'\\': r'\textbackslash{}', '{': r'\{', '}': r'\}', '$': r'\$', '&': r'\&',
               '#': r'\#', '%': r'\%', '_': r'\_', '~': r'\textasciitilde{}', '^': r'\textasciicircum{}'}
    return ''.join(escapes.get(c, c) for c in text)


def _q(text):
    return json.dumps(text, ensure_ascii=False)


class _Renderer:
    def __init__(self, book, engine, assets, math):
        self.book, self.engine, self.assets, self.math = book, engine, assets, math
        self.blocks = {b['id']: b for b in book['blocks']}
        self.notes = {n['id']: n for n in book.get('notes', [])}
        self.toc = {e['target']: e for e in book['toc']['entries']}
        self.chapters = {c['id']: c for c in book['chapters']}
        self.code_files = {}

    def title_block(self, ident):
        block = self.blocks.get(ident)
        if block is None:
            block = self.blocks.get(self.chapters.get(ident, {}).get('title_block_id'))
        return block

    def title(self, ident, *, plain=False):
        block = self.title_block(ident)
        if block is None:
            text = self.toc[ident]['display_title']
            return re.sub(r'</?[ib]>', '', text) if plain else self.styled(text)
        if not plain: return self.inline(block, references=False)
        def literal(match):
            node = block['inlines'][match[0]]
            if node['kind'] == 'math': return node.get('tex') or '[formula]'
            if node['kind'] == 'image': return '[image]'
            if node['kind'] == 'note': return str(node['number'])
            return node['text']
        return re.sub(r'</?[ib]>', '', TOKEN.sub(literal, block['target_text']))

    def bookmark(self, ident):
        entry = self.toc.get(ident)
        if self.engine != 'latex' or not entry: return ''
        title = self.title(ident, plain=True)
        return r'\pdfbookmark[' + str(entry['level'] - 1) + ']{' + _tex(title) + '}{outline-' + ident + '}'

    def text(self, text):
        return _tex(text) if self.engine == 'latex' else '#text(' + _q(text) + ')'

    def styled(self, text, values=None):
        values = values or {}
        def literal(value):
            return ''.join(values[p] if p in values else self.text(p) if p else ''
                           for p in re.split(r'(\x00\d+\x00)', value))
        tags = {'<i>': (r'\textit{' if self.engine == 'latex' else '#emph['),
                '<b>': (r'\textbf{' if self.engine == 'latex' else '#strong[')}
        stack, parts = [], []
        for part in re.split(r'(<[ib]>|</[ib]>)', text):
            if part in tags:
                stack.append(part[1]); parts.append(tags[part])
            elif part in ('</i>', '</b>'):
                if not stack or stack.pop() != part[2]:
                    raise ValueError('Unbalanced translation style markup')
                parts.append('}' if self.engine == 'latex' else ']')
            else:
                parts.append(literal(part) if part else '')
        if stack:
            raise ValueError('Unbalanced translation style markup')
        return ''.join(parts)

    def anchor(self, ident):
        return r'\phantomsection\label{' + ident + '}' if self.engine == 'latex' else f'#metadata(none) <{ident}>'

    def link(self, ident, text):
        return r'\hyperref[' + ident + ']{' + text + '}' if self.engine == 'latex' else f'#link(<{ident}>)[{text}]'

    def image(self, asset_id, *, inline=False):
        if asset_id not in self.assets:
            raise ValueError('Missing template image asset')
        _, relative, asset = self.assets[asset_id]
        if asset['media_type'] not in ('image/png', 'image/jpeg', 'application/pdf'):
            raise ValueError('Template image requires reviewed PNG, JPEG or PDF asset')
        width = float(asset.get('width_em', 24))
        if not 0 < width <= 100: raise ValueError('Invalid template image width_em')
        if self.engine == 'latex':
            if inline:
                return r'\includegraphics[width=' + str(width) + r'em,height=1.5em,keepaspectratio]{' + relative + '}'
            size = r'\ifdim ' + str(width) + r'em>\linewidth\linewidth\else ' + str(width) + r'em\fi'
            return r'\begin{center}\includegraphics[width=' + size + r',height=.78\textheight,keepaspectratio]{' + relative + r'}\end{center}'
        if asset['media_type'] == 'application/pdf':
            raise ValueError('Typst template image requires reviewed PNG or JPEG')
        if inline:
            return '#box[#image(' + _q(relative) + f', width: {width}em, height: 1.5em, fit: "contain")]'
        # An automatic height avoids reserving a page-sized box for short figures.
        return '#context layout(size => align(center, image(' + _q(relative) + f', width: calc.min(size.width, {width} * text.size))))'

    def formula(self, node, display=False):
        if node.get('verified') is True and node.get('tex'):
            tex = node['tex']
            if self.engine == 'latex':
                return (r'\[' + tex + r'\]') if display else (r'\(' + tex + r'\)')
            converted = self.math[tex]
            return '#math.equation(block: true, (' + converted + ').body)' if display else converted
        if node.get('fallback_reason') and node.get('asset_id'):
            return self.image(node['asset_id'], inline=not display)
        raise ValueError('Formula requires verified TeX or evidenced image fallback')

    def inline(self, block, *, references=True):
        text = block.get('target_text', '')
        if '\x00' in text: raise ValueError('NUL is not valid publication text')
        if not block.get('diagnostic_missing') and validate_protected_tokens(
                block.get('source_text', ''), text, expected=block.get('protected_tokens', [])):
            raise ValueError('Damaged protected translation tokens')
        parts, last = [], 0
        # Styles may wrap protected inlines, so keep placeholders until styling.
        values = {}
        for position, match in enumerate(TOKEN.finditer(text)):
            node = block.get('inlines', {}).get(match[0])
            if node is None:
                raise ValueError('Unknown protected inline payload')
            kind = node['kind']
            if kind == 'math': value = self.formula(node)
            elif kind == 'literal': value = self.text(node['text'])
            elif kind == 'code':
                value = r'\texttt{' + _tex(node['text'].expandtabs(4)).replace(' ', r'\ ') + '}' if self.engine == 'latex' else '#raw(' + _q(node['text']) + ')'
            elif kind == 'image': value = self.image(node['asset_id'], inline=True)
            elif kind == 'note':
                value = (self.anchor(node['ref_id']) if references else '') + self.link(node['note_id'], str(node['number']))
                value = r'\textsuperscript{' + value + '}' if self.engine == 'latex' else '#super[' + value + ']'
            else: raise ValueError(f'Unsupported protected inline kind: {kind}')
            # NUL is forbidden by validated text inputs to the source serializer.
            marker = f'\x00{position}\x00'; values[marker] = value
            parts.extend([text[last:match.start()], marker]); last = match.end()
        parts.append(text[last:])
        return self.styled(''.join(parts), values)

    def block(self, block):
        kind = block['kind']
        if kind in ('paragraph', 'note', 'table-cell'): return self.inline(block)
        if kind == 'caption':
            text = self.inline(block)
            return r'\begin{center}\small\color{rptext}' + text + r'\end{center}' if self.engine == 'latex' else '#align(center)[#text(size: .9em, fill: text-color)[' + text + ']]'
        if kind == 'heading':
            level = max(1, min(6, block.get('level', 2)))
            text = self.inline(block)
            if self.engine == 'latex':
                cmd = ['chapter', 'section', 'subsection', 'subsubsection', 'paragraph', 'subparagraph'][level - 1]
                return '\\' + cmd + '*{' + text + '}\n' + self.anchor(block['id']) + self.bookmark(block['id'])
            chapter = next(c for c in self.book['chapters'] if c['id'] == block['chapter_id'])
            mapped = block['id'] in self.toc or (chapter.get('title_block_id') == block['id'] and chapter['id'] in self.toc)
            return f'#heading(level: {level}, outlined: false, bookmarked: {str(mapped).lower()})[{text}] <{block["id"]}>'
        if kind == 'formula': return self.formula(block, display=True)
        if kind == 'figure': return self.image(block['asset_id'])
        if kind == 'code':
            code = block['code']
            if self.engine == 'typst': return '#raw(' + _q(code) + ', block: true)'
            relative = f'code/{block["id"]}.txt'
            self.code_files[relative] = code
            return r'\VerbatimInput[fontsize=\small,breaklines=true,breakanywhere=true]{' + relative + '}'
        if kind == 'table':
            rows = block['rows']
            if not rows or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
                raise ValueError('Table must have nonempty rectangular rows')
            cells = [[self.inline(self.blocks[c]) for c in row] for row in rows]
            n = len(rows[0])
            # A repeated visual header must not duplicate a semantic note target.
            repeat_header = not any(node.get('kind') == 'note' for c in rows[0]
                                    for node in self.blocks[c].get('inlines', {}).values())
            if self.engine == 'latex':
                col = r'>{\raggedright\arraybackslash}p{\dimexpr(\linewidth-' + str(2 * n) + r'\tabcolsep)/' + str(n) + r'\relax}'
                header = ' & '.join(cells[0]) + r'\\\midrule'
                return (r'\begin{longtable}{' + col * n + '}\n' + r'\toprule ' + header + '\n' + r'\endfirsthead' + '\n' +
                        (r'\toprule ' + header + '\n' if repeat_header else '') + r'\endhead' + '\n' + '\n'.join(' & '.join(r) + r'\\' for r in cells[1:]) +
                        '\n' + r'\bottomrule\end{longtable}')
            header = ', '.join('[' + c + ']' for c in cells[0])
            tail = ',\n'.join('[' + c + ']' for row in cells[1:] for c in row)
            return f'#table(columns: ({", ".join(["1fr"] * n)},), inset: 6pt, stroke: .5pt + overlay-color,\n table.header(repeat: {str(repeat_header).lower()}, {header}),\n{tail})'
        raise ValueError(f'Unsupported template block: {kind}')

    def contents(self, settings):
        if not settings['toc']: return ''
        if self.engine == 'latex':
            lines = [r'\chapter*{目录}']
            for e in self.book['toc']['entries']:
                lines.append(r'\noindent\hspace*{' + str((e['level'] - 1) * 1.5) + 'em}' + self.link(e['target'], self.title(e['target'])) + r'\dotfill\pageref{' + e['target'] + r'}\par')
            return '\n'.join(lines) + '\n' + r'\clearpage'
        return '#heading(level: 1, outlined: false)[目录]\n' + '\n\n'.join(
            '#block(width: 100%)[#h(' + str(e['level'] - 1) + 'em)' + self.link(e['target'], self.title(e['target'])) +
            f'#h(1fr)#context counter(page).at(<{e["target"]}>).first()]' for e in self.book['toc']['entries']) + '\n#pagebreak()'

    def body(self, settings):
        lines = []
        excluded = {b for n in self.notes.values() for b in n['block_ids']}
        excluded |= {c for b in self.book['blocks'] if b['kind'] == 'table' for r in b['rows'] for c in r}
        chapters = {c['id']: c for c in self.book['chapters']}
        pagebreak = r'\clearpage' if self.engine == 'latex' else '#pagebreak(weak: true)'
        for item in self.book['publication_order']:
            if item['kind'] == 'front-image': lines.extend([self.image(item['asset_id']), pagebreak]); continue
            if item['kind'] == 'toc': lines.append(self.contents(settings)); continue
            ch = chapters[item['id']]
            lines.append(pagebreak)
            if not ch.get('title_block_id'):
                heading = self.text(ch['display_title'])
                lines.append(r'\chapter*{' + heading + '}' if self.engine == 'latex' else '#heading(level: 1, outlined: false, bookmarked: ' + str(ch['id'] in self.toc).lower() + ')[' + heading + ']')
                lines.append(self.anchor(ch['id']) + self.bookmark(ch['id']))
            for block in self.book['blocks']:
                if block['chapter_id'] != ch['id'] or block['id'] in excluded: continue
                if self.book['toc']['placement'].get('before_block') == block['id']: lines.append(self.contents(settings))
                if block['kind'] != 'heading': lines.append(self.anchor(block['id']))
                lines.append(self.block(block))
                if block['id'] == ch.get('title_block_id'):
                    lines.append(self.anchor(ch['id']) + self.bookmark(ch['id']))
            if ch['note_order']:
                lines.append(r'\Needspace{5\baselineskip}\section*{注释}' if self.engine == 'latex' else '#heading(level: 2, outlined: false)[注释]')
            for nid in ch['note_order']:
                note = self.notes[nid]
                bodies = [self.block(self.blocks[b]) for b in note['block_ids']]
                lines.append(self.anchor(nid) + self.text(str(note['number']) + '. ') + bodies[0])
                lines.extend(bodies[1:])
                lines.append(' '.join(self.link(rid, self.text('返回 ' + str(i + 1))) for i, rid in enumerate(note['references'])))
        return '\n\n'.join(lines)


def export_template_sources(book: BookDocument, output_dir: Path, *, engine: str, settings: dict) -> Path:
    if engine not in ('latex', 'typst'): raise ValueError('Unknown template engine')
    settings = _settings(book, settings)
    for block in book['blocks']:
        if not block.get('diagnostic_missing') and validate_protected_tokens(
                block.get('source_text', ''), block.get('target_text', ''), expected=block.get('protected_tokens', [])):
            raise ValueError('Damaged protected translation tokens')
    book = compile_publication(book)
    assets = validated_assets(book)
    formulas = []
    for block in book['blocks']:
        for node in [block] + list(block.get('inlines', {}).values()):
            if node.get('kind') in ('math', 'formula') and node.get('verified') is True and node.get('tex'):
                formulas.append(node['tex'])
    renderer = _Renderer(book, engine, assets, _typst_math(formulas) if engine == 'typst' else {})
    body = renderer.body(settings)
    suffix = '.tex' if engine == 'latex' else '.typ'
    template = (TEMPLATES / engine / ('book' + suffix)).read_text(encoding='utf8')
    raw = dict(settings)
    for key, value in settings.items():
        if isinstance(value, str): raw[key] = renderer.text(value) if engine == 'latex' else _q(value)
        elif isinstance(value, bool): raw[key] = str(value).lower()
        else: raw[key] = str(value)
    # Font names and language are command arguments, not body content.
    if engine == 'latex':
        for key in ('font_latin', 'font_cjk', 'font_mono', 'page_size'): raw[key] = _tex(settings[key])
        raw['page_size'] += 'paper'
    else:
        language = settings['language'].split('-')
        raw['typst_language'] = _q(language[0])
        raw['typst_region'] = next((_q(part.upper()) for part in language[1:] if len(part) == 2), 'none')
    raw['body'] = body
    has_cover = any(e.get('role') == 'cover' for e in book['publication_order'])
    raw['title_page'] = '' if has_cover else (r'\makecover' if engine == 'latex' else '#book-cover(title, author, translator)\n#pagebreak()')
    raw['draft'] = ('DIAGNOSTIC DRAFT — incomplete translation\n' if book.get('diagnostic_draft') else '')
    raw['page_numbering'] = (r'\pagestyle{empty}\fancypagestyle{plain}{\fancyhf{}\renewcommand{\headrulewidth}{0pt}}' if not settings['page_numbers'] else '') if engine == 'latex' else ('"1"' if settings['page_numbers'] else 'none')
    def bind(match):
        if match[1] not in raw: raise ValueError('Unresolved template parameter')
        return raw[match[1]]
    template = re.sub(r'@@(\w+)@@', bind, template)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for path, relative, _ in assets.values():
        target = output_dir / relative; target.parent.mkdir(parents=True, exist_ok=True); shutil.copyfile(path, target)
    for relative, code in renderer.code_files.items():
        target = output_dir / relative; target.parent.mkdir(parents=True, exist_ok=True); target.write_text(code, encoding='utf8', newline='')
    if engine == 'latex': shutil.copytree(TEMPLATES / 'latex/rosepine', output_dir / 'rosepine', dirs_exist_ok=True)
    source = output_dir / ('book.draft' + suffix if book.get('diagnostic_draft') else 'book' + suffix)
    source.write_text(template, encoding='utf8')
    write_json(output_dir / 'book.settings.json', settings)
    write_json(output_dir / 'source-manifest.json', dict(engine=engine, source_sha256=book['source_sha256'],
               source_file_sha256=sha256(source), reference_commit='c717041d54b5eb5f5f153b97a3a606c147e37402'))
    if book.get('diagnostic_draft'): write_json(output_dir / 'missing-units.json', book['missing_units'])
    return source


def compile_book_pdf(source: Path, *, engine: str, output_path: Path) -> dict:
    if engine not in ('latex', 'typst'): raise ValueError('Unknown template engine')
    source, output = Path(source).resolve(), Path(output_path).resolve()
    if not source.is_file(): raise ValueError('Template source does not exist')
    log = source.with_suffix('.compile.log'); report_path = source.with_suffix('.compile.json')
    report = dict(status='failed', engine=engine, log=str(log), output=str(output))
    logs = []
    try:
        exe = _executable('xelatex' if engine == 'latex' else 'typst')
        env = os.environ.copy(); env.update(openin_any='p', openout_any='p')
        with tempfile.TemporaryDirectory(prefix='.compile-', dir=source.parent) as stage:
            stage = Path(stage); pdf = stage / 'compiled.pdf'
            if engine == 'latex':
                args = [exe, '-no-shell-escape', '-interaction=nonstopmode', '-halt-on-error', '-file-line-error',
                        '-jobname=compiled', '-output-directory=' + stage.name, source.name]
            else: args = [exe, 'compile', '--root', str(source.parent), str(source), str(pdf)]
            for _ in range(3 if engine == 'latex' else 1):
                proc = subprocess.run(args, cwd=source.parent, env=env, text=True, encoding='utf8', errors='replace',
                                      capture_output=True, timeout=180)
                logs.append(proc.stdout + proc.stderr)
                if proc.returncode: break
            if engine == 'latex' and (stage / 'compiled.log').exists(): logs.append((stage / 'compiled.log').read_text(encoding='utf8', errors='replace'))
            # Check only the final pass for rerun/undefined-reference diagnostics.
            final = logs[-1] if logs else ''
            bad = re.search(r'Missing character:|Overfull \\[hv]box|undefined references|Reference .* undefined|warning:', final, re.I)
            if proc.returncode == 0 and pdf.is_file() and pdf.read_bytes().startswith(b'%PDF-') and not bad:
                output.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(pdf, output)
                report.update(status='passed', sha256=sha256(output))
            else: report['diagnostic'] = (bad[0] if bad else 'Compiler failed or produced no PDF')
    except FileNotFoundError as exc: report.update(status='unavailable', diagnostic=str(exc))
    except (OSError, subprocess.SubprocessError) as exc: report['diagnostic'] = str(exc); logs.append(str(exc))
    log.write_text('\n\n'.join(logs) or report.get('diagnostic', ''), encoding='utf8')
    write_json(report_path, report)
    return report
