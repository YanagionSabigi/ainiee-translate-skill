import copy
import importlib
import zipfile

from lxml import etree
import pytest

from test_book_markdown import translated_book


def publisher():
    assert importlib.util.find_spec('ainiee_translate.book_epub'), 'EPUB publisher is not implemented'
    return importlib.import_module('ainiee_translate.book_epub')


@pytest.fixture
def publication_book(translated_book):
    book = copy.deepcopy(translated_book)
    book['chapters'].insert(0, {'id': 'preface', 'source_title': 'Preface', 'display_title': '前言'})
    book['blocks'].insert(0, {'id': 'preface-body', 'kind': 'paragraph', 'chapter_id': 'preface',
                              'unit_id': 'upreface', 'source_text': 'Preface body', 'target_text': '前言正文'})
    for role, page in [('cover', 0), ('back-cover', 9)]:
        image = copy.deepcopy(book['assets'][0])
        image.update(id=role, role=role, source_page_idx=page)
        book['assets'].append(image)
    book['provenance']['publication_roles'] = [{'source_page_idx': 0, 'role': 'cover'}, {'source_page_idx': 9, 'role': 'back-cover'}]
    return book


def test_frontmatter_and_toc_keep_reviewed_order(tmp_path, publication_book):
    path = publisher().export_epub(publication_book, tmp_path / 'book.epub')
    with zipfile.ZipFile(path) as z:
        assert z.infolist()[0].filename == 'mimetype'
        assert z.infolist()[0].compress_type == zipfile.ZIP_STORED
        opf = etree.fromstring(z.read('EPUB/package.opf'))
        ns = {'o': 'http://www.idpf.org/2007/opf'}
        assert opf.xpath('//o:spine/o:itemref/@idref', namespaces=ns) == ['cover-page', 'back-cover-page', 'preface', 'visible-toc', 'ch1']
        visible = etree.fromstring(z.read('EPUB/toc.xhtml'))
        assert not visible.xpath('//*[local-name()="ol"]')
        assert visible.xpath('//*[local-name()="a"]/@href') == ['ch1.xhtml#ch1']
        nav = etree.fromstring(z.read('EPUB/nav.xhtml'))
        assert nav.xpath('//*[local-name()="a"]/@href') == ['ch1.xhtml#ch1']
        assert b'\xe7\xac\xac\xe4\xb8\x80\xe7\xab\xa0' in z.read('EPUB/nav.xhtml')
        assert opf.xpath('count(//o:item[contains(@properties,"cover-image")])', namespaces=ns) == 1
        assert b'preface-body' in z.read('EPUB/preface.xhtml')


def test_repeated_note_has_all_backlinks(tmp_path, translated_book):
    path = publisher().export_epub(translated_book, tmp_path / 'book.epub')
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read('EPUB/ch1.xhtml'))
        ns = {'e': 'http://www.idpf.org/2007/ops'}
        refs = root.xpath('//*[@e:type="noteref"]', namespaces=ns)
        assert [r.xpath('string()') for r in refs] == ['1', '1']
        assert len({r.get('id') for r in refs}) == 2
        note = root.xpath('//*[@id="note1"]')[0]
        assert note.xpath('.//*[local-name()="a"]/@href') == ['#' + r.get('id') for r in refs]
        assert '注释正文' in ''.join(note.itertext())
        assert len(root.xpath('//*[local-name()="math"]')) == 1
        assert len(root.xpath('//*[@id="note-body1"]')) == 1


def test_notes_reset_per_chapter_and_deep_headings_stay_in_body(tmp_path, translated_book):
    book = copy.deepcopy(translated_book)
    book['chapters'].append({'id': 'ch2', 'display_title': '第二章', 'source_title': 'Two'})
    book['blocks'].extend([
        {'id': 'deep', 'kind': 'heading', 'level': 4, 'chapter_id': 'ch2', 'unit_id': 'udeep', 'source_text': 'Deep', 'target_text': '深层标题'},
        {'id': 'second', 'kind': 'paragraph', 'chapter_id': 'ch2', 'unit_id': 'usecond', 'source_text': '⟦AT:note:n2⟧', 'target_text': '⟦AT:note:n2⟧',
         'protected_tokens': ['⟦AT:note:n2⟧'], 'inlines': {'⟦AT:note:n2⟧': {'kind': 'note', 'note_id': 'note2'}}},
        {'id': 'body2', 'kind': 'paragraph', 'chapter_id': 'ch2', 'unit_id': 'unote2', 'source_text': 'Note two', 'target_text': '第二章注释'},
    ])
    book['notes'].append({'id': 'note2', 'chapter_id': 'ch2', 'block_ids': ['body2'], 'original_label': '*', 'association_evidence': 'self-authored'})
    path = publisher().export_epub(book, tmp_path / 'book.epub')
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read('EPUB/ch2.xhtml'))
        assert root.xpath('string(//*[@role="doc-noteref"])') == '1'
        assert root.xpath('string(//*[local-name()="h4"])') == '深层标题'
        assert b'deep' not in z.read('EPUB/nav.xhtml')


def test_markdown_shares_reviewed_publication_order(tmp_path, publication_book):
    from ainiee_translate.book_markdown import render_markdown
    text = render_markdown(publication_book)
    assert text.index('assets/cover.png') < text.index('assets/back-cover.png') < text.index('前言正文') < text.index('[第一章](#ch1)') < text.index('# 第一章')


def test_table_notes_follow_reading_order_not_cell_definition_order(tmp_path, translated_book):
    book = copy.deepcopy(translated_book)
    cell = next(b for b in book['blocks'] if b['id'] == 'cell1')
    token = '⟦AT:note:table⟧'
    cell.update(source_text=token, target_text=token, protected_tokens=[token], inlines={token: {'kind': 'note', 'note_id': 'table-note'}})
    book['blocks'].append({'id': 'table-note-body', 'kind': 'paragraph', 'chapter_id': 'ch1', 'unit_id': 'utablenote', 'source_text': 'Table note', 'target_text': '表格注释'})
    book['notes'].append({'id': 'table-note', 'chapter_id': 'ch1', 'block_ids': ['table-note-body'], 'original_label': 'a', 'association_evidence': 'self-authored'})
    table = next(b for b in book['blocks'] if b['id'] == 'table1'); book['blocks'].remove(table); book['blocks'].insert(0, table)
    path = publisher().export_epub(book, tmp_path / 'book.epub')
    with zipfile.ZipFile(path) as z:
        root = etree.fromstring(z.read('EPUB/ch1.xhtml'))
        refs = root.xpath('//*[@role="doc-noteref"]')
        assert [''.join(r.itertext()) for r in refs] == ['1', '2', '2']


def test_only_reachable_publication_assets_enter_epub(tmp_path, translated_book):
    from ainiee_translate.mineru_local import sha256
    private = tmp_path / 'private-review.txt'; private.write_text('UNPUBLISHED REVIEW CONTENT')
    translated_book['assets'].append({'id': 'unreferenced-review', 'path': private.name, 'sha256': sha256(private), 'media_type': 'text/plain'})
    path = publisher().export_epub(translated_book, tmp_path / 'book.epub')
    with zipfile.ZipFile(path) as z:
        assert not any('unreferenced-review' in name for name in z.namelist())
        assert b'UNPUBLISHED REVIEW CONTENT' not in b''.join(z.read(name) for name in z.namelist())


@pytest.mark.parametrize('mutation', ['missing_bookmark', 'unresolved_note', 'orphan_note', 'duplicate_id', 'missing_asset', 'bad_toc_position'])
def test_unresolved_structure_cannot_publish(tmp_path, translated_book, mutation):
    api = publisher(); book = copy.deepcopy(translated_book)
    if mutation == 'missing_bookmark': book['provenance']['bookmarks'] = []
    if mutation == 'unresolved_note': book['notes'][0]['association_evidence'] = ''
    if mutation == 'orphan_note': book['notes'][0]['id'] = 'unreferenced'
    if mutation == 'duplicate_id': book['blocks'][1]['id'] = book['blocks'][0]['id']
    if mutation == 'missing_asset': book['assets'][0]['path'] = 'missing.png'
    if mutation == 'bad_toc_position': book['toc']['placement'] = {'before': 'nonexistent'}
    with pytest.raises(ValueError):
        api.export_epub(book, tmp_path / 'out.epub')
    assert not (tmp_path / 'out.epub').exists()

