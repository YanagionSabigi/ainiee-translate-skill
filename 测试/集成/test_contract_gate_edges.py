import copy,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'夹具'))
from v2_sample import make_bound
from ainiee_translate.pdf_bridge import contract


def test_no_publication_policy_cannot_pass_formal_gate(tmp_path):
    def adjust(book): book['structure_rules']={};book.pop('publication_input')
    book,target,cf,manifest,ctx=make_bound(tmp_path,adjust)
    with pytest.raises(ValueError,match='publication-input'): contract().validate_translation_binding(target,manifest,tmp_path)


def test_note_generated_list_items_stay_in_note_section(tmp_path):
    from ainiee_translate.book_pdf import export_template_sources
    from ainiee_translate.book_markdown import export_markdown
    def adjust(book):
        note=book['notes'][0]['blocks'][0]
        note.update(kind='ordered-list',items=[[{'text':'First item.'}],[{'text':'Second item.'}]])
        note.pop('inline')
    book,target,cf,manifest,ctx=make_bound(tmp_path/'work',adjust)
    tex=export_template_sources(target,tmp_path/'out',engine='latex',settings={},manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    assert tex.count('First item.')==1 and tex.index('section*{注释}')<tex.index('First item.')
    md=export_markdown(target,tmp_path/'md',manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    assert md.count('First item.')==1 and md.index('id="n1"')<md.index('First item.')
    assert '[返回 1](#cite1)' in md


def test_resource_hashes_frozen_and_changed_asset_rejected(tmp_path):
    import base64
    def adjust(book):
        (tmp_path/'figure.png').write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jM1sAAAAASUVORK5CYII='))
        book['chapters'][0]['blocks'].append({'id':'figure','kind':'figure','source_region':{'page':3,'bbox':[30,30,31,31]},'asset':{'id':'asset','path':'figure.png','alt':''}})
    book,target,cf,manifest,ctx=make_bound(tmp_path,adjust)
    assert book['chapters'][0]['blocks'][-1]['asset']['sha256']
    (tmp_path/'figure.png').write_bytes(b'changed')
    with pytest.raises(ValueError,match='resource'): contract().validate_translation_binding(target,manifest,tmp_path)


def test_table_backlinks_use_valid_xhtml_caption(tmp_path):
    import zipfile,xml.etree.ElementTree as ET
    from ainiee_translate.pdf_bridge import run_cli
    from ainiee_translate.artifact_io import write_json
    def adjust(book):
        book['chapters'][0]['blocks'][0]['inline'].append(dict(link='table',text='Table 1',id='table-ref',evidence='Synthetic table target'))
        book['chapters'][1]['blocks'].append(dict(id='table',kind='table',rows=[['Cell']],table_evidence='Synthetic table',provenance=[{'page':3,'bbox':[20,20,400,60]}]))
    book,target,cf,manifest,ctx=make_bound(tmp_path/'work',adjust)
    write_json(tmp_path/'target.json',target);write_json(tmp_path/'manifest.json',manifest)
    run_cli('build','--work',tmp_path/'work','--book',tmp_path/'target.json','--translation-manifest',tmp_path/'manifest.json','--output',tmp_path/'book.epub','--report-dir',tmp_path/'report')
    with zipfile.ZipFile(tmp_path/'book.epub') as z:
        root=ET.fromstring(z.read('EPUB/c2.xhtml'))
        table=root.find('.//{http://www.w3.org/1999/xhtml}table')
        assert table.find('{http://www.w3.org/1999/xhtml}a') is None
        assert table.find('{http://www.w3.org/1999/xhtml}caption/{http://www.w3.org/1999/xhtml}a') is not None


def test_template_and_markdown_preserve_table_caption(tmp_path):
    from ainiee_translate.book_pdf import export_template_sources
    from ainiee_translate.book_markdown import export_markdown
    def adjust(book):
        book['chapters'][1]['blocks'].append(dict(id='table',kind='table',rows=[['Cell']],
            inline=[{'text':'Table 1. Counts'}],table_evidence='Synthetic table',provenance=[{'page':3,'bbox':[20,20,400,60]}]))
    book,target,cf,manifest,ctx=make_bound(tmp_path/'work',adjust)
    tex=export_template_sources(target,tmp_path/'tex',engine='latex',settings={},manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    md=export_markdown(target,tmp_path/'md',manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    assert 'Table 1. Counts' in tex and 'Table 1. Counts' in md


def test_verified_native_styles_and_literal_markup_survive_templates(tmp_path):
    from ainiee_translate.book_pdf import export_template_sources
    from ainiee_translate.book_markdown import export_markdown
    def adjust(book):
        book['chapters'][0]['blocks'][0]['inline'] += [dict(text='2',styles=['sup']),dict(text='under',styles=['underline']),dict(text='<i>literal</i>')]
    book,target,cf,manifest,ctx=make_bound(tmp_path/'work',adjust)
    tex=export_template_sources(target,tmp_path/'tex',engine='latex',settings={},manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    md=export_markdown(target,tmp_path/'md',manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    assert r'\textsuperscript{2}' in tex and r'\underline{under}' in tex
    assert '<sup>2</sup>' in md and '&lt;i&gt;literal&lt;/i&gt;' in md
