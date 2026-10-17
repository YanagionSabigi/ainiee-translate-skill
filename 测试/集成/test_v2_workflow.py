import copy
import json
from pathlib import Path
import sys
import zipfile
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'夹具'))
from v2_sample import make_bound
from ainiee_translate.pdf_bridge import contract,run_cli


def test_real_cli_build_and_source_state_isolation(tmp_path):
    book,target,cf,manifest,context=make_bound(tmp_path/'work')
    work=tmp_path/'work'; reports=tmp_path/'reports'
    before={p.name:p.read_bytes() for p in work.glob('*.json')}
    from ainiee_translate.artifact_io import write_json
    write_json(tmp_path/'target.json',target); write_json(tmp_path/'manifest.json',manifest)
    epub=tmp_path/'book.epub'
    run_cli('build','--work',work,'--book',tmp_path/'target.json','--translation-manifest',tmp_path/'manifest.json','--output',epub,'--report-dir',reports)
    assert all((work/name).read_bytes()==data for name,data in before.items())
    run_cli('check',epub,'--output',reports/'check.json')
    with zipfile.ZipFile(epub) as z:
        first=z.read('EPUB/c1.xhtml').decode(); second=z.read('EPUB/c2.xhtml').decode()
        assert first.count('一条注释。')==1 and '一条注释。' not in second
        assert 'c2.xhtml#rnote2' in first
        assert 'c1.xhtml#cite1' in first and 'id="cite1"' in first
        assert 'c1.xhtml#n1' in second
    assert (reports/'publication-state.json').exists()


@pytest.mark.parametrize('mutation',['target','raw','review','prompt','cache','proof','old_revision','structure'])
def test_publication_rejects_stale_evidence(tmp_path,mutation):
    book,target,cf,manifest,ctx=make_bound(tmp_path)
    if mutation=='target': target['chapters'][0]['title']='篡改'
    elif mutation in ('raw','review'): (tmp_path/(mutation+'.json')).write_text('{}')
    elif mutation in ('prompt','cache','proof'):
        path=ctx[{'prompt':'prompt_path','cache':'cache_path','proof':'review_path'}[mutation]]; path.write_text('{}')
    elif mutation=='old_revision': target['revision']+=1
    elif mutation=='structure': target['chapters'][0]['blocks'][0]['inline'][1]['note']='absent'
    with pytest.raises(ValueError): contract().validate_translation_binding(target,manifest,tmp_path)


def test_late_source_correction_preserves_unaffected_units(tmp_path):
    from ainiee_translate.pdf_cache import reconcile_cache,apply_cache_to_book
    book,target,cf,manifest,ctx=make_bound(tmp_path)
    unit=next(u for u in book['units'] if u['block_id']=='p1' and u['source_text']=='Three objects.')
    changed=contract().revise_source(tmp_path,[{'unit_id':unit['unit_id'],'source_sha256':unit['source_sha256'],'text':'Seven objects.','evidence':'Synthetic OCR correction checked against self-authored source'}])
    fresh=reconcile_cache(changed,cf)
    affected=next(i for i in fresh.items if i.extra['ainiee_pdf']['unit_id']==unit['unit_id'])
    assert affected.translation_status==0 and not affected.translated_text
    unaffected=next(i for i in fresh.items if i.source_text=='Three objects.')
    assert unaffected.translated_text=='三个物体。' and unaffected.extra['ainiee_pdf']['proofreading']
    assert fresh.extra['ainiee_pdf']['historical_units']
    with pytest.raises(ValueError,match='Incomplete'): apply_cache_to_book(changed,fresh)


def test_templates_and_markdown_use_same_bound_book(tmp_path):
    from ainiee_translate.book_pdf import export_template_sources
    from ainiee_translate.book_markdown import export_markdown
    book,target,cf,manifest,ctx=make_bound(tmp_path/'work')
    tex=export_template_sources(target,tmp_path/'tex',engine='latex',settings={},manifest=manifest,work=tmp_path/'work')
    text=tex.read_text(encoding='utf8')
    assert '三个物体。' in text and text.count('一条注释。')==1
    assert 'label{rnote1}' in text and 'label{rnote2}' in text
    assert 'hyperref[cite1]' in text
    md=export_markdown(target,tmp_path/'md',manifest=manifest,work=tmp_path/'work').read_text(encoding='utf8')
    assert '三个物体。' in md and md.count('一条注释。')==1
