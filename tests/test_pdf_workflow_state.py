import importlib
import json

import pytest

from test_pdf_publication_input import source, reviewed_plan


def workflow():
    assert importlib.util.find_spec('ainiee_translate.pdf'), 'PDF workflow is not implemented'
    return importlib.import_module('ainiee_translate.pdf')


def test_unreviewed_input_cannot_extract(tmp_path, source, monkeypatch):
    api = workflow()
    from ainiee_translate.pdf_publication import inspect_pdf
    work = tmp_path / 'work'; inspect_pdf(source, work)
    def forbidden(*args, **kwargs):
        pytest.fail('unreviewed input reached extraction')
    monkeypatch.setattr(api, 'extract_bundle', forbidden)
    with pytest.raises(ValueError, match='review'):
        api.extract_work(work)


def test_draft_requires_extraction_and_never_overwrites_review(tmp_path):
    api = workflow(); work = tmp_path / 'work'; work.mkdir()
    with pytest.raises((ValueError, FileNotFoundError)):
        api.draft_work(work)
    review = {'reviewed': False, 'private_work': 'preserve manually recorded evidence'}
    (work / 'publication.review.json').write_text(json.dumps(review))
    assert api.draft_work(work) == review
    assert json.loads((work / 'publication.review.json').read_text()) == review


def test_nested_semantic_image_body_is_included_in_review_inventory(tmp_path):
    api = workflow()
    from test_mineru_local import middle, bundle
    from ainiee_translate.mineru_local import import_bundle
    document = middle(True)
    path = bundle(tmp_path, document, assets={'images/figure.png': b'fixture resource'})
    manifest = import_bundle(path, tmp_path / 'raw')
    candidates = api.extraction_candidates(tmp_path, {'imports': [{'root': 'raw', 'manifest': manifest,
        'page_map': [{'input_page_idx': 0, 'source_page_idx': 0, 'bbox': [0, 0, 400, 600], 'role': 'content'}]}]})
    assert [c['block']['type'] for c in candidates] == ['text', 'image', 'image_body']


def test_expected_page_missing_from_middle_blocks_review(tmp_path):
    api = workflow()
    from test_mineru_local import middle, bundle
    from ainiee_translate.mineru_local import import_bundle
    manifest = import_bundle(bundle(tmp_path, middle()), tmp_path / 'raw')
    with pytest.raises(ValueError, match='page|coverage'):
        api.extraction_candidates(tmp_path, {'imports': [{'root': 'raw', 'manifest': manifest,
            'page_map': [{'input_page_idx': 0, 'source_page_idx': 0}, {'input_page_idx': 1, 'source_page_idx': 1}]}]})
