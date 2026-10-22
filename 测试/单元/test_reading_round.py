import hashlib
from pathlib import Path
import sys
import pytest
sys.path.insert(0, str(Path(__file__).parents[1] / '夹具'))
from reading_sample import create_project, epub, TARGETS
from ainiee_translate import cache_io

def freeze(root, **kw):
    from ainiee_translate.reading_round import freeze_round
    args = dict(storage_path='source.epub', round_dir=root/'work/reading/R0001',
                glossary_path=root/'glossary.json', prompt_path=root/'prompt.md')
    args.update(kw)
    return freeze_round(root/'cache.json', root/'reading.epub', root/'input/source.epub', **args)

def test_freeze_preserves_exact_epub_and_cache(tmp_path):
    from ainiee_translate.reading_round import load_round, load_segments
    root = create_project(tmp_path)
    before = (root/'cache.json').read_bytes()
    r = freeze(root)
    rd = root/'work/reading/R0001'
    assert r['edition_id'] == hashlib.sha256((root/'reading.epub').read_bytes()).hexdigest()
    assert (rd/'edition/cache.frozen.json').read_bytes() == before
    p = cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[0].translated_text='后来'
    cache_io.save_cache(p, root/'cache.json')
    assert (rd/'edition/cache.frozen.json').read_bytes() == before
    assert load_segments(rd)[0]['target_text'] == '河流记得每一块石头。'
    assert load_round(rd)['book_id'] is None
    with pytest.raises((ValueError, FileExistsError)): freeze(root)

@pytest.mark.parametrize('kind', ['wrong_book', 'storage', 'empty', 'different_translation'])
def test_wrong_epub_or_book_rejected(tmp_path, kind):
    root = create_project(tmp_path)
    if kind in ('wrong_book','different_translation'):
        epub(root/'reading.epub', ['完全不同的译本']*8)
    if kind == 'empty':
        p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[2].translated_text=''
        cache_io.save_cache(p, root/'cache.json')
    with pytest.raises(ValueError): freeze(root, **({'storage_path':'other.epub'} if kind=='storage' else {}))

def test_epub_spine_and_duplicate_paragraphs(tmp_path):
    from ainiee_translate.reading_round import load_segments
    root=create_project(tmp_path); freeze(root)
    ss=load_segments(root/'work/reading/R0001')
    assert [x['href'] for x in ss[0]['locators']] == ['OEBPS/c1.xhtml', 'OEBPS/c2.xhtml']
    assert ss[0]['segment_id'] != ss[4]['segment_id']
    assert ss[5]['locators'][0]['spine_index']==1

def test_pdf_unit_ids_retained(tmp_path):
    from ainiee_translate.reading_round import load_segments
    root=create_project(tmp_path); p=cache_io.load_cache(root/'cache.json')
    for i,it in enumerate(p.files['source.epub'].items):
        it.extra['ainiee_pdf']={'unit_id':f'u{i}', 'document_id':'doc', 'provenance':{'physical_page':1}}
    cache_io.save_cache(p, root/'cache.json'); freeze(root)
    assert load_segments(root/'work/reading/R0001')[0]['unit_id']=='u0'

def test_pdf_inline_fragments_share_rendered_paragraph(tmp_path):
    import zipfile
    from ainiee_translate.reading_round import load_segments
    root=create_project(tmp_path)
    path=root/'reading.epub'
    with zipfile.ZipFile(path) as z: files={n:z.read(n) for n in z.namelist()}
    files['OEBPS/c1.xhtml']=files['OEBPS/c1.xhtml'].replace(b'</p><p id="p1">',b'<sup>1</sup>')
    with zipfile.ZipFile(path,'w') as z:
        for n,data in files.items(): z.writestr(n,data)
    p=cache_io.load_cache(root/'cache.json')
    for i,it in enumerate(p.files['source.epub'].items):
        it.extra['ainiee_pdf']={'unit_id':f'u{i}','document_id':'doc','source_refs':[{'page':12}],
                              'slot_path':['chapters',0,'blocks',0,'inline',i,'text']}
    cache_io.save_cache(p,root/'cache.json'); freeze(root)
    ss=load_segments(root/'work/reading/R0001')
    assert ss[1]['locators'][0]['text_start']>0
    assert ss[1]['provenance'][0]['page']==12

def test_scope_omissions_require_edition_and_cache_evidence(tmp_path):
    from ainiee_translate.artifact_io import sha256,write_json
    from ainiee_translate.reading_round import freeze_round,load_segments
    root=create_project(tmp_path); p=cache_io.load_cache(root/'cache.json')
    p.files['source.epub'].items[7].translated_text='原项目另行交付的附录'
    p.files['source.epub'].items[7].extra['ainiee_pdf']={'unit_id':'appendix'}
    cache_io.save_cache(p,root/'cache.json')
    scope=dict(schema='reading-scope/1',cache_sha256=sha256(root/'cache.json'),epub_sha256='wrong',
               omitted_units={'appendix':'原项目已明确另行交付附录'},evidence_reference='local existing publication policy')
    write_json(root/'scope.json',scope)
    kwargs=dict(storage_path='source.epub',round_dir=root/'work/reading/R0001',glossary_path=root/'glossary.json',prompt_path=root/'prompt.md',scope_path=root/'scope.json')
    with pytest.raises(ValueError): freeze_round(root/'cache.json',root/'reading.epub',root/'input/source.epub',**kwargs)
    scope['epub_sha256']=sha256(root/'reading.epub'); write_json(root/'scope.json',scope)
    freeze_round(root/'cache.json',root/'reading.epub',root/'input/source.epub',**kwargs)
    assert load_segments(root/'work/reading/R0001')[7]['mapping_status']=='outside_reading_edition'
