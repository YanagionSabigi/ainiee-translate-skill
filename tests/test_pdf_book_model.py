import copy
import importlib
import json

import pytest

from test_mineru_local import middle, bundle
from test_pdf_publication_input import source, reviewed_plan


def model():
    assert importlib.util.find_spec('ainiee_translate.book_model'), 'book model is not implemented'
    return importlib.import_module('ainiee_translate.book_model')


@pytest.fixture
def reviewed_work(tmp_path, source):
    from ainiee_translate.mineru_local import import_bundle, digest, write_json, sha256
    from ainiee_translate.pdf import draft_work
    from ainiee_translate.pdf_publication import inspect_pdf, prepare_extraction_inputs
    work = tmp_path / 'work'; inspect_pdf(source, work)
    plan = reviewed_plan(source); write_json(work / 'publication-input.json', plan)
    inputs = prepare_extraction_inputs(source, plan, work)
    document = middle()
    original = document['pages'][0]['blocks'][0]
    second = copy.deepcopy(original); second['index'] = 1
    document['pages'][0]['blocks'].append(second)
    path = bundle(tmp_path, document); imported = work / 'imports' / sha256(path)
    manifest = import_bundle(path, imported)
    extraction = dict(schema='ainiee-pdf-extraction/1', source_sha256=sha256(source),
                      publication_input_sha256=digest(plan), status='completed', imports=[
                          {**inputs[0], 'bundle': str(path), 'root': str(imported.relative_to(work)), 'manifest': manifest}])
    write_json(work / 'extraction.json', extraction)
    review = draft_work(work)
    review.update(reviewed=True, evidence='Self-authored paragraphs checked in source fixture',
                  metadata={'title': 'Fixture Book', 'language': 'zh'},
                  chapters=[{'id': 'chapter-1', 'source_title': 'References', 'title': 'References'}],
                  blocks=[{'id': f'p{i}', 'kind': 'paragraph', 'chapter_id': 'chapter-1',
                           'raw_ids': [row['raw_id']], 'source_text': 'An original paragraph.'}
                          for i, row in enumerate(review['candidates'])],
                  toc={'source': 'pdf-bookmarks', 'evidence': 'Verified fixture bookmark',
                       'placement': {'before': 'chapter-1'}, 'entries': [
                           {'bookmark_index': 0, 'target': 'chapter-1', 'level': 1}]})
    write_json(work / 'publication.review.json', review)
    return work


def test_unknown_semantic_block_requires_resolution(reviewed_work):
    api = model()
    from ainiee_translate.mineru_local import write_json
    path = reviewed_work / 'publication.review.json'; review = json.loads(path.read_text())
    review['blocks'].pop()
    write_json(path, review)
    with pytest.raises(ValueError, match='coverage|semantic|unaccounted'):
        api.normalize_book(reviewed_work)


def test_structure_review_does_not_finish_translation(reviewed_work):
    book = model().normalize_book(reviewed_work)
    assert book['schema'] == 'ainiee-book/1'
    assert book['source_structure_reviewed'] is True
    assert book['translation_complete'] is False
    assert len({b['unit_id'] for b in book['blocks']}) == 2
    assert all(b['source_refs'][0]['source_page_idx'] == 1 for b in book['blocks'])
    assert book['toc']['entries'][0]['source_title'] == 'References'


@pytest.mark.parametrize('mutation', ['unreviewed', 'raw_changed', 'source_changed', 'plan_changed', 'missing_note_evidence'])
def test_stale_or_unreviewed_structure_is_rejected(reviewed_work, mutation):
    api = model()
    from ainiee_translate.mineru_local import write_json
    path = reviewed_work / 'publication.review.json'; review = json.loads(path.read_text())
    if mutation == 'unreviewed': review['reviewed'] = False
    if mutation == 'raw_changed':
        imp = json.loads((reviewed_work / 'extraction.json').read_text(encoding='utf8'))['imports'][0]
        (reviewed_work / imp['root'] / imp['manifest']['middle_json']).write_text('{}')
    if mutation == 'source_changed': review['source_sha256'] = '0' * 64
    if mutation == 'plan_changed':
        p = reviewed_work / 'publication-input.json'; d = json.loads(p.read_text()); d['evidence'] += ' changed'; write_json(p, d)
    if mutation == 'missing_note_evidence': review['notes'] = [{'id': 'n1', 'chapter_id': 'chapter-1', 'block_ids': ['p0']}]
    write_json(path, review)
    with pytest.raises(ValueError):
        api.normalize_book(reviewed_work)

