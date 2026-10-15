"""Reviewed fixture through the public parse/write/polish/audit/export boundaries."""
import json
import os
from pathlib import Path
import subprocess
import sys

from test_pdf_book_model import reviewed_work
from test_pdf_publication_input import source


def test_reviewed_pdf_translation_roundtrip_to_md_and_epub(tmp_path, source, reviewed_work):
    from ainiee_translate import parse, cache_io, batch, polish, audit, export, verify
    from ainiee_translate.glossary import load_locked
    from ainiee_translate.book_check import check_epub
    review_path = reviewed_work / 'publication.review.json'
    review = json.loads(review_path.read_text(encoding='utf8'))
    review['chapters'][0]['display_title'] = '参考文献'
    review_path.write_text(json.dumps(review, ensure_ascii=False), encoding='utf8')
    cache = tmp_path / 'cache.json'
    parse.main(['--input', str(source), '--pdf-work', str(reviewed_work), '--out', str(cache)])
    locked = tmp_path / 'glossary.locked.json'; locked.write_text('{"characters":[],"terms":[]}', encoding='utf8')
    schema = tmp_path / 'glossary.schema.json'; schema.write_text('{"type":"object","required":["terms","characters"]}')
    terms = load_locked(str(locked), schema_path=str(schema))
    rows = batch.read_batch(cache_io.load_cache(str(cache)))
    translations = [{'text_index': r['text_index'], 'translated_text': f'这是第 {n} 处独立译文。'} for n, r in enumerate(rows, 1)]
    assert batch.validate(rows, translations)['ok']
    assert batch.write_back(str(cache), translations).applied == 2
    polished = [{'text_index': r['text_index'], 'polished_text': r['translated_text'].replace('独立译文', '核验译文')} for r in translations]
    assert polish.write_polished(str(cache), polished).applied == 2
    checked = verify._items_for_check(str(cache))
    assert verify.check_items(checked, terms) == []
    assert not audit.audit_items(checked)
    project = cache_io.load_cache(str(cache))
    export.export_project(project, str(tmp_path / 'out'), str(source), formats=['md', 'epub'], cache_root=tmp_path)
    md = next((tmp_path / 'out').rglob('book.md'))
    epub = next((tmp_path / 'out').rglob('book.epub'))
    assert '第 1 处核验译文' in md.read_text(encoding='utf8')
    assert check_epub(epub)['structure']['status'] == 'passed'


def test_bundle_exposes_pdf_cli_and_matches_canonical_source(tmp_path):
    repo = Path(__file__).resolve().parents[1]
    env = {**os.environ, 'PYTHONPATH': str(repo / 'skills/ainiee-translate/scripts'), 'PYTHONUTF8': '1'}
    result = subprocess.run([sys.executable, '-m', 'ainiee_translate.pdf', '--help'], env=env, cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    assert 'normalize' in result.stdout
    result = subprocess.run([sys.executable, str(repo / 'build.py'), '--check'], cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr


def test_epub_only_draft_writes_missing_unit_report(tmp_path, source, reviewed_work):
    from ainiee_translate import parse, cache_io, export
    review_path = reviewed_work / 'publication.review.json'
    review = json.loads(review_path.read_text(encoding='utf8'))
    review['chapters'][0]['display_title'] = '参考文献'
    review_path.write_text(json.dumps(review), encoding='utf8')
    cache = tmp_path / 'cache.json'
    parse.main(['--input', str(source), '--pdf-work', str(reviewed_work), '--out', str(cache)])
    export.export_project(cache_io.load_cache(str(cache)), str(tmp_path / 'draft'), str(source), formats=['epub'], allow_partial=True, cache_root=tmp_path)
    report = next((tmp_path / 'draft').rglob('missing-units.json'))
    assert len(json.loads(report.read_text(encoding='utf8'))) == 2
