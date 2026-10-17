import importlib
import json

import pytest

from ainiee_translate import batch, cache_io, polish, audit

TOKENS = ['⟦AT:math:m1⟧', '⟦AT:note:n1⟧']
SOURCE = 'Formula ⟦AT:math:m1⟧ and note ⟦AT:note:n1⟧.'


def protection():
    assert importlib.util.find_spec('ainiee_translate.pdf_protection'), 'PDF structure protection is not implemented'
    return importlib.import_module('ainiee_translate.pdf_protection')


@pytest.mark.parametrize('bad', [
    '公式和注。', '⟦AT:math:m1⟧ ⟦AT:math:m1⟧ ⟦AT:note:n1⟧',
    '⟦AT:math:m2⟧ ⟦AT:note:n1⟧', '⟦AT:note:n1⟧ ⟦AT:math:m1⟧',
    '⟦AT:math:m1⟧ ⟦AT:note:n1⟧ ⟦AT:code:unknown⟧',
])
def test_structure_tokens_cannot_be_forced_through(tmp_path, make_project, bad):
    p = make_project(sources=[SOURCE]); item = p.files['a.txt'].items[0]
    item.extra['ainiee_pdf'] = {'version': 1, 'unit_id': 'u1', 'chapter_id': 'ch1', 'protected_tokens': TOKENS}
    path = str(tmp_path / 'cache.json'); cache_io.save_cache(p, path)
    result = batch.write_back(path, [{'text_index': 1, 'translated_text': bad}], force=True, allow_tag_mismatch=True)
    assert result.applied == 0 and result.rejected
    result = polish.write_polished(path, [{'text_index': 1, 'polished_text': bad}], force=True)
    assert result.applied == 0
    assert cache_io.load_cache(path).files['a.txt'].items[0].translation_status == 0


def test_complete_tokens_write_normally_and_old_projects_are_unchanged(tmp_path, make_project):
    p = make_project(sources=[SOURCE]); item = p.files['a.txt'].items[0]
    path = str(tmp_path / 'old.json'); cache_io.save_cache(p, path)
    assert batch.write_back(path, [{'text_index': 1, 'translated_text': '普通旧项目。'}]).applied == 1
    item.extra['ainiee_pdf'] = {'version': 1, 'protected_tokens': TOKENS}
    cache_io.save_cache(p, path)
    assert batch.write_back(path, [{'text_index': 1, 'translated_text': '公式 ⟦AT:math:m1⟧ 和注 ⟦AT:note:n1⟧。'}]).applied == 1
    assert not list(tmp_path.glob('*.tmp.*'))


def test_literal_token_collision_is_escaped_and_recorded():
    api = protection()
    text, mapping = api.escape_collisions('Literal ⟦AT:math:m1⟧ plus ⟦AT:math:m1⟧')
    assert text.count('⟦AT:literal:') == 2
    assert len(mapping) == 2
    assert all(value['text'] == '⟦AT:math:m1⟧' for value in mapping.values())


def test_validate_and_audit_use_pdf_metadata():
    row = {'text_index': 1, 'source_text': SOURCE, 'extra': {'ainiee_pdf': {'protected_tokens': TOKENS}}}
    assert not batch.validate([row], [{'text_index': 1, 'translated_text': '坏译文。'}])['ok']
    report = audit.audit_items([{**row, 'translated_text': '坏译文。', 'translation_status': 1}])
    assert report['structure_tokens']['count'] == 1


def test_batch_splits_preserve_chapter_and_readonly_context_metadata(make_project, tmp_path):
    p = make_project(2)
    for n, item in enumerate(p.files['a.txt'].items, 1):
        item.extra['ainiee_pdf'] = {'chapter_id': f'ch{n}', 'protected_tokens': []}
    assert len(batch.chapters(p)) == 2
    batch.split_project(p, 1, str(tmp_path / 'batches'), 1)
    rows = json.loads((tmp_path / 'batches/grp_1_src.json').read_text())
    assert rows[0]['extra']['ainiee_pdf']['chapter_id'] == 'ch1'


def test_optional_project_glossary_schema_blocks_invalid_load(tmp_path):
    from ainiee_translate.glossary import load_locked
    glossary = tmp_path / 'locked.json'; glossary.write_text('{}')
    schema = tmp_path / 'schema.json'; schema.write_text(json.dumps({'type': 'object', 'required': ['terms']}))
    with pytest.raises(ValueError, match='schema|Schema'):
        load_locked(str(glossary), schema_path=str(schema))
