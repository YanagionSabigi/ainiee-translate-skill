import importlib
import zipfile
import os
from pathlib import Path

import pytest

from test_book_markdown import translated_book


def checker():
    assert importlib.util.find_spec('ainiee_translate.book_check'), 'EPUB checks are not implemented'
    return importlib.import_module('ainiee_translate.book_check')


def test_unavailable_epubcheck_is_not_passed(tmp_path, translated_book):
    api = checker()
    from ainiee_translate.book_epub import export_epub
    path = export_epub(translated_book, tmp_path / 'book.epub')
    result = api.check_epub(path, epubcheck_jar=tmp_path / 'missing.jar')
    assert result['structure']['status'] == 'passed'
    assert result['epubcheck']['status'] == 'unavailable'


@pytest.mark.skipif(not os.environ.get('EPUBCHECK_JAR'), reason='official EPUBCheck is optional')
def test_official_epubcheck_accepts_published_notes_and_math(tmp_path, translated_book):
    api = checker()
    from ainiee_translate.book_epub import export_epub
    path = export_epub(translated_book, tmp_path / 'official.epub')
    result = api.check_epub(path, epubcheck_jar=Path(os.environ['EPUBCHECK_JAR']))
    assert result['epubcheck']['status'] == 'passed', result


@pytest.mark.parametrize('mutation', ['broken_link', 'duplicate_id', 'absolute_link', 'duplicate_member', 'missing_asset'])
def test_invalid_epub_packages_fail_structure_checks(tmp_path, translated_book, mutation):
    api = checker()
    from ainiee_translate.book_epub import export_epub
    source = export_epub(translated_book, tmp_path / 'original.epub')
    broken = tmp_path / 'broken.epub'
    with zipfile.ZipFile(source) as z, zipfile.ZipFile(broken, 'w') as out:
        for info in z.infolist():
            if mutation == 'missing_asset' and info.filename.endswith('figure1.png'): continue
            data = z.read(info)
            if info.filename == 'EPUB/ch1.xhtml':
                if mutation == 'broken_link': data = data.replace(b'#note1', b'#absent')
                if mutation == 'absolute_link': data = data.replace(b'#note1', b'file:///private/secret')
                if mutation == 'duplicate_id': data = data.replace(b'id="p1"', b'id="heading1"')
            out.writestr(info, data)
        if mutation == 'duplicate_member':
            with pytest.warns(UserWarning): out.writestr('mimetype', 'application/epub+zip')
    result = api.check_epub(broken)
    assert result['structure']['status'] == 'failed'
    assert result['structure']['issues']
