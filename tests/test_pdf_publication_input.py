import importlib
import json

import pymupdf
import pytest


def publication():
    assert importlib.util.find_spec('ainiee_translate.pdf_publication'), 'PDF publication preparation is not implemented'
    return importlib.import_module('ainiee_translate.pdf_publication')


@pytest.fixture
def source(tmp_path):
    path = tmp_path / '中文 original.pdf'
    with pymupdf.open() as doc:
        for i in range(3):
            page = doc.new_page(width=400, height=600)
            page.insert_text((30, 50), ['COVER', 'Bibliography kept', 'BACK COVER'][i])
            if i == 1:
                page.insert_text((30, 450), 'PRIVATE INDEX EXCLUDED')
        doc.set_toc([[1, 'References', 2]])
        doc.save(path)
    return path


def reviewed_plan(source):
    from ainiee_translate.mineru_local import sha256
    return {'schema': 'ainiee-publication-input/1', 'source_sha256': sha256(source),
            'reviewed': True, 'evidence': 'Self-authored fixture checked against page layout',
            'pages': [{'page': 1, 'role': 'cover', 'evidence': 'fixture front'},
                      {'page': 2, 'role': 'content', 'evidence': 'mixed page', 'regions': [
                          {'bbox': [0, 0, 400, 200], 'role': 'bibliography', 'evidence': 'upper references only'}]},
                      {'page': 3, 'role': 'back-cover', 'evidence': 'fixture rear'}]}


def test_mixed_page_keeps_bibliography_only(tmp_path, source):
    api = publication()
    plan = reviewed_plan(source)
    inputs = api.prepare_extraction_inputs(source, plan, tmp_path / 'work')
    assert len(inputs) == 1
    assert inputs[0]['page_map'] == [{'input_page_idx': 0, 'source_page_idx': 1,
                                     'bbox': [0, 0, 400, 200], 'role': 'bibliography'}]
    with pymupdf.open(inputs[0]['input_path']) as doc:
        assert len(doc) == 1
        assert tuple(doc[0].rect) == (0, 0, 400, 200)
        assert not doc[0].get_text()  # Raster crop has no hidden excluded text layer.
        image = doc.extract_image(doc[0].get_images()[0][0])
        assert image['height'] < image['width']
    assert source.read_bytes().find(b'') == 0


@pytest.mark.parametrize('mutation', ['hash', 'unreviewed', 'missing_evidence', 'bad_box', 'unknown_role', 'missing_page', 'overlap'])
def test_invalid_plan_cannot_prepare(tmp_path, source, mutation):
    api = publication()
    plan = reviewed_plan(source)
    if mutation == 'hash': plan['source_sha256'] = '0' * 64
    if mutation == 'unreviewed': plan['reviewed'] = False
    if mutation == 'missing_evidence': plan['pages'][0]['evidence'] = ''
    if mutation == 'bad_box': plan['pages'][1]['regions'][0]['bbox'] = [-1, 0, 500, 700]
    if mutation == 'unknown_role': plan['pages'][0]['role'] = 'guess'
    if mutation == 'missing_page': plan['pages'].pop()
    if mutation == 'overlap': plan['pages'][1]['regions'] *= 2
    with pytest.raises(ValueError):
        api.prepare_extraction_inputs(source, plan, tmp_path / 'work')
    assert not list((tmp_path / 'work').rglob('*.pdf'))


def test_inspection_records_unreviewed_plan_and_bookmarks(tmp_path, source):
    api = publication()
    work = tmp_path / 'work'
    inspection = api.inspect_pdf(source, work)
    assert inspection['bookmarks'][0]['source_title'] == 'References'
    assert inspection['bookmarks'][0]['source_page_idx'] == 1
    plan = json.loads((work / 'publication-input.json').read_text())
    assert plan['reviewed'] is False and len(plan['pages']) == 3
    plan = reviewed_plan(source)
    (work / 'publication-input.json').write_text(json.dumps(plan))
    api.inspect_pdf(source, work)
    assert json.loads((work / 'publication-input.json').read_text()) == plan


def test_source_and_derivative_hashes_are_distinct(tmp_path, source):
    api = publication()
    from ainiee_translate.mineru_local import sha256
    inputs = api.prepare_extraction_inputs(source, reviewed_plan(source), tmp_path / 'work')
    assert inputs[0]['source_sha256'] == sha256(source)
    assert inputs[0]['input_sha256'] == sha256(inputs[0]['input_path'])
    assert inputs[0]['input_sha256'] != inputs[0]['source_sha256']


def test_same_preparation_reuses_bytes_and_changed_plan_invalidates(tmp_path, source):
    api = publication()
    plan = reviewed_plan(source); work = tmp_path / 'work'
    a = api.prepare_extraction_inputs(source, plan, work)
    b = api.prepare_extraction_inputs(source, plan, work)
    assert a == b
    plan['pages'][1]['regions'][0]['bbox'][3] = 250
    c = api.prepare_extraction_inputs(source, plan, work)
    assert c[0]['input_path'] != a[0]['input_path']

