import importlib

import pytest

from test_pdf_book_model import reviewed_work
from test_pdf_publication_input import source


def cache_api():
    assert importlib.util.find_spec('ainiee_translate.pdf_cache'), 'structured cache mapping is not implemented'
    return importlib.import_module('ainiee_translate.pdf_cache')


def test_duplicate_sentences_use_distinct_unit_ids(reviewed_work, tmp_path):
    api = cache_api()
    from ainiee_translate.book_model import normalize_book
    from ainiee_translate import cache_io
    from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheProject import CacheProject
    book = normalize_book(reviewed_work)
    cf = api.book_to_cache_file(book, storage_path='source.pdf')
    assert cf.items[0].source_text == cf.items[1].source_text
    assert cf.items[0].extra['ainiee_pdf']['unit_id'] != cf.items[1].extra['ainiee_pdf']['unit_id']
    for item, ti, text in zip(cf.items, [200, 100], ['第一处。', '第二处。']):
        item.text_index = ti; item.translation_status = 1; item.translated_text = text
    cf.items.reverse()
    path = tmp_path / 'cache.json'; cache_io.save_cache(CacheProject(files={'source.pdf': cf}), str(path))
    restored = cache_io.load_cache(str(path)).files['source.pdf']
    target = api.apply_cache_to_book(book, restored)
    assert [b['target_text'] for b in target['blocks']] == ['第一处。', '第二处。']
    assert target['translation_complete'] is True
    assert book['translation_complete'] is False and all('target_text' not in b for b in book['blocks'])


def test_untranslated_or_wrong_source_cache_cannot_publish(reviewed_work):
    api = cache_api()
    from ainiee_translate.book_model import normalize_book
    book = normalize_book(reviewed_work); cf = api.book_to_cache_file(book, storage_path='source.pdf')
    with pytest.raises(ValueError, match='translation|untranslated'):
        api.apply_cache_to_book(book, cf)
    partial = api.apply_cache_to_book(book, cf, allow_partial=True)
    assert len(partial['missing_units']) == 2 and partial['diagnostic_draft'] is True
    cf.extra['ainiee_pdf']['source_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='source'):
        api.apply_cache_to_book(book, cf, allow_partial=True)

