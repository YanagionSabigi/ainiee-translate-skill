import copy
import importlib
import json
import os
from pathlib import Path

import pytest

from test_book_markdown import translated_book


def api():
    assert importlib.util.find_spec('ainiee_translate.book_pdf'), 'Template publisher is not implemented'
    return importlib.import_module('ainiee_translate.book_pdf')


@pytest.fixture
def math_converter(tmp_path, monkeypatch):
    # A deterministic subprocess contract; real Pandoc acceptance is separate.
    def convert(formulas):
        assert all(isinstance(tex, str) for tex in formulas)
        return {tex: '$ x^2 $' for tex in formulas}
    module = api()
    monkeypatch.setattr(module, '_typst_math', convert)


def test_both_templates_preserve_reviewed_notes_and_math(tmp_path, translated_book, math_converter):
    original = copy.deepcopy(translated_book)
    for engine, suffix in [('latex', '.tex'), ('typst', '.typ')]:
        source = api().export_template_sources(translated_book, tmp_path / engine, engine=engine, settings={})
        text = source.read_text(encoding='utf8')
        assert source.suffix == suffix
        for value in ['第一章', '斜体正文', '图注文字', '表格单元', '注释正文', 'ref-p1-1', 'ref-p1-2', 'note1']:
            assert value in text
        assert text.count('注释正文') == 1
        assert text.index('目录') < text.index('斜体正文') < text.index('注释正文')
        assert ('x^2' in text) if engine == 'latex' else ('$ x^2 $' in text)
        assert (source.parent / 'assets/figure1.png').is_file()
        assert str(tmp_path) not in text
        report = json.loads((source.parent / 'source-manifest.json').read_text())
        assert report['source_sha256'] == translated_book['source_sha256']
        assert report['engine'] == engine
    assert translated_book == original


@pytest.mark.parametrize('engine', ['latex', 'typst'])
def test_settings_escaping_and_breakable_long_tables(tmp_path, translated_book, math_converter, engine):
    book = copy.deepcopy(translated_book)
    cell = next(b for b in book['blocks'] if b['id'] == 'cell1')
    cell['target_text'] = r'中文，Latin 100% & #_{} $ \\ [x] <b>加粗</b>'
    table = next(b for b in book['blocks'] if b['id'] == 'table1')
    table['rows'] *= 100
    source = api().export_template_sources(book, tmp_path / engine, engine=engine,
                                         settings={'title': '题目 # [] 100%', 'author': '作者', 'translator': '译者', 'page_size': 'a5'})
    text = source.read_text(encoding='utf8')
    assert '作者' in text and '译者' in text and 'a5' in text.lower()
    if engine == 'latex':
        assert r'\begin{longtable}' in text and r'100\%' in text and r'\textbf{加粗}' in text
    else:
        assert '#table(' in text and '#strong[' in text and '#text("' in text
    # longtable contains a second header definition for continuation pages.
    assert text.count('中文，Latin') == (101 if engine == 'latex' else 100)


@pytest.mark.parametrize('settings', [{'unknown': True}, {'margin_mm': -1}, {'font_size': 0}, {'page_size': 'random'}, {'toc': 'yes'}])
def test_invalid_settings_leave_no_output(tmp_path, translated_book, settings):
    out = tmp_path / 'out'
    with pytest.raises(ValueError, match='setting'):
        api().export_template_sources(translated_book, out, engine='latex', settings=settings)
    assert not out.exists()


def test_damaged_tokens_fail_before_source_creation(tmp_path, translated_book):
    translated_book['blocks'][1]['target_text'] = '遗漏公式和注释'
    with pytest.raises(ValueError, match='token'):
        api().export_template_sources(translated_book, tmp_path / 'out', engine='latex', settings={})
    assert not (tmp_path / 'out').exists()


def test_missing_compiler_is_unavailable_and_preserves_previous_pdf(tmp_path, monkeypatch):
    module = api()
    monkeypatch.setenv('AINIEE_TYPST', str(tmp_path / 'absent-compiler.exe'))
    source = tmp_path / 'book.typ'; source.write_text('Example')
    output = tmp_path / 'book.pdf'; output.write_bytes(b'previous result')
    report = module.compile_book_pdf(source, engine='typst', output_path=output)
    assert report['status'] == 'unavailable'
    assert output.read_bytes() == b'previous result'
    assert Path(report['log']).is_file()


def test_template_delimiters_in_metadata_remain_literal(tmp_path, translated_book):
    text = api().export_template_sources(translated_book, tmp_path / 'latex', engine='latex',
                                        settings={'title': '书名 @@body@@'}).read_text(encoding='utf8')
    assert '书名 @@body@@' in text
    assert text.count('注释正文') == 1


def test_failed_compile_cannot_publish_stale_pdf(tmp_path, monkeypatch):
    import subprocess
    module = api()
    source = tmp_path / 'book.tex'; source.write_text('Broken')
    output = tmp_path / 'book.pdf'; output.write_bytes(b'previous result')
    monkeypatch.setattr(module, '_executable', lambda name: 'fake-compiler')
    monkeypatch.setattr(module.subprocess, 'run', lambda *a, **kw: subprocess.CompletedProcess(a[0], 1, 'ERROR', ''))
    result = module.compile_book_pdf(source, engine='latex', output_path=output)
    assert result['status'] == 'failed'
    assert output.read_bytes() == b'previous result'
    assert 'ERROR' in Path(result['log']).read_text()


def test_typst_math_uses_real_pandoc_ast_and_rejects_warning(monkeypatch):
    import subprocess
    module = api(); calls = []
    monkeypatch.setattr(module, '_executable', lambda name: 'pandoc')
    def run(argv, **kwargs):
        calls.append(argv)
        if '--to=json' in argv:
            return subprocess.CompletedProcess(argv, 0, '{"pandoc-api-version":[1,23,1]}', '')
        ast = json.loads(kwargs['input'])
        assert ast['blocks'][0]['c'][0]['t'] == 'Math'
        assert ast['blocks'][0]['c'][0]['c'][1] == r'\frac{a}{b}'
        return subprocess.CompletedProcess(argv, 0, '$ frac(a,b) $', 'WARNING math cannot be represented')
    monkeypatch.setattr(module.subprocess, 'run', run)
    with pytest.raises(ValueError, match='Pandoc'):
        module._typst_math([r'\frac{a}{b}'])
    assert any('--to=typst' in argv for argv in calls)


@pytest.fixture
def template_project(tmp_path, translated_book, make_project):
    from ainiee_translate.pdf_cache import book_to_cache_file
    book = copy.deepcopy(translated_book)
    for b in book['blocks']: b['source_refs'] = []
    cf = book_to_cache_file(book, storage_path='sample.pdf')
    by_unit = {b['unit_id']: b for b in book['blocks'] if b.get('unit_id')}
    for item in cf.items:
        item.translated_text = by_unit[item.extra['ainiee_pdf']['unit_id']]['target_text']
        item.translation_status = 1
    (tmp_path / 'book.source.json').write_text(json.dumps(book), encoding='utf8')
    project = make_project(); project.files = {'sample.pdf': cf}
    return project


def test_export_sources_and_each_requested_pdf(tmp_path, template_project, math_converter, monkeypatch):
    from ainiee_translate.export import export_project
    calls = []
    def compile(source, *, engine, output_path):
        assert source.is_file()
        calls.append(engine); output_path.write_bytes(b'%PDF-test')
        return {'status': 'passed'}
    monkeypatch.setattr(api(), 'compile_book_pdf', compile)
    export_project(template_project, str(tmp_path / 'out'), '.', formats=['latex', 'typst', 'pdf'],
                   cache_root=tmp_path, book_settings={'title': '配置书名'})
    assert calls == ['latex', 'typst']
    for engine in calls:
        assert (tmp_path / 'out/sample' / engine / 'book.pdf').exists()
        suffix = '.tex' if engine == 'latex' else '.typ'
        assert '配置书名' in (tmp_path / 'out/sample' / engine / ('book' + suffix)).read_text(encoding='utf8')


def test_requested_pdf_failure_is_not_success(tmp_path, template_project, monkeypatch):
    from ainiee_translate.export import export_project
    monkeypatch.setattr(api(), 'compile_book_pdf', lambda *args, **kwargs: {'status': 'unavailable', 'diagnostic': 'xelatex absent'})
    with pytest.raises(ValueError, match='unavailable|absent'):
        export_project(template_project, str(tmp_path / 'out'), '.', formats=['pdf'],
                       pdf_engines=['latex'], cache_root=tmp_path)


@pytest.mark.parametrize('engine', ['latex', 'typst'])
def test_reviewed_section_links_and_page_number_setting(tmp_path, translated_book, math_converter, engine):
    book = copy.deepcopy(translated_book)
    book['provenance']['bookmarks'].append({'bookmark_index': 1, 'source_title': 'Section', 'source_page_idx': 1})
    book['toc']['entries'].append({'bookmark_index': 1, 'target': 'section-two', 'level': 2})
    book['blocks'].insert(2, {'id': 'section-two', 'kind': 'heading', 'level': 2, 'chapter_id': 'ch1',
                             'unit_id': 'usection', 'source_text': 'Section', 'target_text': '第二节'})
    text = api().export_template_sources(book, tmp_path / engine, engine=engine,
                                        settings={'page_numbers': False}).read_text(encoding='utf8')
    assert '第二节' in text and 'section-two' in text
    if engine == 'latex':
        assert r'\pageref{section-two}' in text and r'\pagestyle{empty}' in text
        assert r'\pdfbookmark[1]{第二节}' in text
        assert r'\Needspace' in text
    else:
        assert 'counter(page).at(<section-two>)' in text and 'numbering: none' in text
        assert 'bookmarked: true' in text


@pytest.mark.parametrize('engine', ['latex', 'typst'])
def test_table_note_anchor_is_not_repeated_in_continuation_header(tmp_path, translated_book, math_converter, engine):
    book = copy.deepcopy(translated_book)
    cell = next(b for b in book['blocks'] if b['id'] == 'cell1')
    tok = '⟦AT:note:table⟧'
    cell.update(source_text=tok, target_text=tok, protected_tokens=[tok], inlines={tok: {'kind': 'note', 'note_id': 'note1'}})
    # Distinct body cells; only the first (header) cell contains a note.
    for i in range(100):
        book['blocks'].append(dict(id=f'row{i}', kind='table-cell', chapter_id='ch1', unit_id=f'ur{i}',
                                   source_text='body', target_text=f'第 {i} 行'))
    next(b for b in book['blocks'] if b['id'] == 'table1')['rows'] = [['cell1']] + [[f'row{i}'] for i in range(100)]
    text = api().export_template_sources(book, tmp_path / engine, engine=engine, settings={}).read_text(encoding='utf8')
    assert text.count('label{ref-cell1-0}') == 1 if engine == 'latex' else 'table.header(repeat: false,' in text


@pytest.mark.parametrize('engine', ['latex', 'typst'])
def test_math_title_uses_structured_contents_without_internal_markers(tmp_path, translated_book, math_converter, engine):
    heading = translated_book['blocks'][0]; token = '⟦AT:math:heading⟧'
    heading.update(source_text='Title ' + token, target_text='标题 ' + token, protected_tokens=[token],
                   inlines={token: {'kind': 'math', 'verified': True, 'tex': 'x^2'}})
    text = api().export_template_sources(translated_book, tmp_path / engine, engine=engine, settings={}).read_text(encoding='utf8')
    assert 'AT:math:heading' not in text
    assert text.count('x^2') >= 2


@pytest.mark.parametrize('engine', ['latex', 'typst'])
def test_inline_formula_image_respects_relative_size(tmp_path, translated_book, math_converter, engine):
    node = translated_book['blocks'][1]['inlines']['⟦AT:math:m1⟧']
    node.clear(); node.update(kind='math', asset_id='figure1', fallback_reason='exact reviewed source crop')
    translated_book['assets'][0]['width_em'] = 2
    text = api().export_template_sources(translated_book, tmp_path / engine, engine=engine, settings={}).read_text(encoding='utf8')
    paragraph = text[text.index('斜体正文'):text.index('ref-p1-1')]
    if engine == 'latex': assert 'width=2.0em' in paragraph and 'center' not in paragraph
    else: assert '#box[' in paragraph and '2.0em' in paragraph


def test_typst_language_and_region_are_separate(tmp_path, translated_book, math_converter):
    text = api().export_template_sources(translated_book, tmp_path / 'typst', engine='typst',
                                        settings={'language': 'zh-Hans-CN'}).read_text(encoding='utf8')
    assert 'lang: "zh", region: "CN"' in text
    assert 'lang: "zh-Hans-CN"' not in text


def test_latex_code_preserves_indentation_blank_lines_and_delimiters(tmp_path, translated_book):
    code = 'if ready:\n    call()\n\n    print("100% {x} \\\\end{Verbatim}")\n'
    translated_book['blocks'].append(dict(id='literal-code', kind='code', chapter_id='ch1', code=code))
    source = api().export_template_sources(translated_book, tmp_path / 'latex', engine='latex', settings={})
    assert (source.parent / 'code/literal-code.txt').read_text(encoding='utf8') == code
    assert r'\VerbatimInput' in source.read_text(encoding='utf8')
