import copy
import importlib
import re
import shutil

import pytest


def markdown():
    assert importlib.util.find_spec('ainiee_translate.book_markdown'), 'structured Markdown export is not implemented'
    return importlib.import_module('ainiee_translate.book_markdown')


@pytest.fixture
def translated_book(tmp_path):
    from ainiee_translate.mineru_local import sha256
    import base64
    image = tmp_path / 'figure.png'
    image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jM1sAAAAASUVORK5CYII='))
    math = '⟦AT:math:m1⟧'; n1 = '⟦AT:note:n1a⟧'; n2 = '⟦AT:note:n1b⟧'
    text = f'<i>原文</i> {math} {n1} {n2}'
    return {'schema': 'ainiee-book/1', 'source_sha256': 'a' * 64,
            'source_structure_reviewed': True, 'translation_complete': True,
            'metadata': {'title': '测试书', 'language': 'zh', 'identifier': 'urn:uuid:90a10560-e1e6-42d2-b4b8-20ace7c09796'},
            'chapters': [{'id': 'ch1', 'source_title': 'Chapter', 'display_title': '第一章', 'title_block_id': 'heading1'}],
            'blocks': [
                {'id': 'heading1', 'kind': 'heading', 'level': 1, 'chapter_id': 'ch1', 'source_text': 'Chapter', 'target_text': '第一章', 'unit_id': 'u0'},
                {'id': 'p1', 'kind': 'paragraph', 'chapter_id': 'ch1', 'source_text': text,
                 'target_text': text.replace('原文', '斜体正文'), 'unit_id': 'u1',
                 'protected_tokens': [math, n1, n2], 'inlines': {
                     math: {'kind': 'math', 'tex': 'x^2', 'verified': True, 'width_em': 2},
                     n1: {'kind': 'note', 'note_id': 'note1'}, n2: {'kind': 'note', 'note_id': 'note1'}}},
                {'id': 'fig1', 'kind': 'figure', 'chapter_id': 'ch1', 'asset_id': 'figure1'},
                {'id': 'caption1', 'kind': 'caption', 'chapter_id': 'ch1', 'source_text': 'Figure', 'target_text': '图注文字', 'unit_id': 'u2'},
                {'id': 'note-body1', 'kind': 'paragraph', 'chapter_id': 'ch1', 'source_text': 'Note', 'target_text': '注释正文', 'unit_id': 'u3'},
                {'id': 'cell1', 'kind': 'table-cell', 'chapter_id': 'ch1', 'source_text': 'Cell', 'target_text': '表格单元', 'unit_id': 'u4'},
                {'id': 'table1', 'kind': 'table', 'chapter_id': 'ch1', 'rows': [['cell1']]},
            ],
            'notes': [{'id': 'note1', 'chapter_id': 'ch1', 'block_ids': ['note-body1'],
                       'original_label': '*', 'association_evidence': 'Self-authored repeated note'}],
            'assets': [{'id': 'figure1', 'path': 'figure.png', 'sha256': sha256(image), 'media_type': 'image/png', 'width_em': 10}],
            'toc': {'source': 'pdf-bookmarks', 'evidence': 'self-authored source position',
                    'placement': {'before': 'ch1'}, 'entries': [{'bookmark_index': 0, 'target': 'ch1', 'level': 1, 'source_title': 'Chapter'}]},
            'provenance': {'work': str(tmp_path), 'bookmarks': [{'bookmark_index': 0, 'source_title': 'Chapter', 'source_page_idx': 0}]},
            'issues': []}


def test_relocated_export_keeps_asset_links(tmp_path, translated_book):
    api = markdown()
    path = api.export_markdown(translated_book, tmp_path / 'out')
    moved = tmp_path / 'moved'; shutil.move(str(path.parent), moved)
    text = (moved / path.name).read_text(encoding='utf8')
    assert text.count('斜体正文') == 1 and '*斜体正文*' in text
    assert text.count('注释正文') == 1 and text.count('[^note1]') == 3
    assert '$x^2$' in text and '| 表格单元 |' in text
    assert '图注文字' in text
    for link in re.findall(r'!\[[^\]]*\]\(([^)]+)\)', text):
        assert (moved / link).is_file()
    assert str(tmp_path) not in text


def test_untranslated_units_are_not_silently_filled(translated_book):
    api = markdown(); book = copy.deepcopy(translated_book)
    book['blocks'][1].pop('target_text'); book['translation_complete'] = False
    with pytest.raises(ValueError, match='translation'):
        api.render_markdown(book)


def test_missing_asset_is_rejected_before_publication(tmp_path, translated_book):
    api = markdown(); (tmp_path / 'figure.png').unlink()
    with pytest.raises(ValueError, match='asset'):
        api.export_markdown(translated_book, tmp_path / 'out')
    assert not (tmp_path / 'out/book.md').exists()
