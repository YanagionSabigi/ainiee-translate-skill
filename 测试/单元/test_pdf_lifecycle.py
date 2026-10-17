import copy
import json
from pathlib import Path
import pytest

from ainiee_translate import pdf_cache


def test_cache_rejects_legacy_pdf_model():
    with pytest.raises(ValueError, match='epub-book/2'):
        pdf_cache.book_to_cache_file({'schema': 'ainiee-book/1'}, storage_path='a.pdf')


def test_glossary_schema_is_required_and_invalid_table_rejected(tmp_path):
    from ainiee_translate.pdf_review import load_review_config
    prompt = tmp_path / 'prompt.txt'
    prompt.write_text('Translate faithfully', encoding='utf8')
    glossary = tmp_path / 'glossary.json'
    glossary.write_text('{"terms": "broken"}', encoding='utf8')
    with pytest.raises(ValueError, match='glossary'):
        load_review_config(prompt, glossary)


def test_issues_group_by_cause_and_revision_decisions(tmp_path):
    from ainiee_translate.pdf_issues import issue_ledger, render_issue_summary, decide_issue
    book = {'document_id': 'doc', 'revision': 2}
    ledger = issue_ledger(book, [
        {'id': 'R1', 'kind': 'semantic_reference', 'cause': 'duplicate equation', 'location': 'p.3', 'ref_id': 'r1'},
        {'id': 'R2', 'kind': 'semantic_reference', 'cause': 'duplicate equation', 'location': 'p.4', 'ref_id': 'r2'},
        {'id': 'A1', 'kind': 'missing_asset', 'cause': 'missing figure', 'location': 'p.5'},
    ])
    report = render_issue_summary(ledger)
    assert report.count('duplicate equation') == 1
    assert 'R1' in report and 'R2' in report
    with pytest.raises(ValueError, match='semantic'):
        decide_issue(ledger, 'A1', action='plain_text', reason='approved', actor='human', book=book)
    changed = decide_issue(ledger, 'R1', action='plain_text', reason='ambiguous targets', actor='human', book=book)
    assert 'R1' not in render_issue_summary(changed)
    with pytest.raises(ValueError, match='revision'):
        decide_issue(changed, 'R2', action='plain_text', reason='approved', actor='human', book={**book, 'revision': 3})
