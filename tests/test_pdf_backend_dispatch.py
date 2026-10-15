import json

import pytest

from test_pdf_book_model import reviewed_work
from test_pdf_publication_input import source


def test_mineru_failure_never_calls_babeldoc(tmp_path, monkeypatch):
    from ainiee_translate.parse import parse_input
    monkeypatch.setenv('AINIEE_REPO', str(tmp_path))
    pdf = tmp_path / 'source.pdf'; pdf.write_bytes(b'synthetic')
    with pytest.raises(ValueError, match='inspect|prepare|review'):
        parse_input(str(pdf))


def test_new_pdf_imports_reviewed_book_and_preserves_existing_cache(reviewed_work, source, tmp_path):
    from ainiee_translate.book_model import normalize_book
    from ainiee_translate.parse import main
    normalize_book(reviewed_work)
    path = tmp_path / 'cache.json'
    args = ['--input', str(source), '--out', str(path), '--pdf-work', str(reviewed_work)]
    main(args)
    before = path.read_bytes()
    with pytest.raises((ValueError, FileExistsError), match='exist|overwrite'):
        main(args)
    assert path.read_bytes() == before


def test_legacy_cache_uses_legacy_backend(tmp_path, make_project, monkeypatch):
    from ainiee_translate import export
    p = make_project(storage='legacy.pdf'); written = []
    monkeypatch.setenv('AINIEE_REPO', str(tmp_path))
    monkeypatch.setattr(export, '_export_via_ainiee', lambda project, *args: written.append(project))
    export.export_project(p, str(tmp_path / 'out'), str(tmp_path))
    assert written == [p]
