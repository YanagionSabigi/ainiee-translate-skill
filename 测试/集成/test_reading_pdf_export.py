"""Final orchestration with real PDF contract/export; only compiler/checker stubbed."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'夹具'))
sys.path.insert(0,str(Path(__file__).parents[1]/'单元'))
from v2_sample import make_bound
from test_weread_notes import merge,snapshot

def test_pdf_export_options_do_not_enter_manifest_context(tmp_path,monkeypatch):
    from ainiee_translate import cache_io,book_pdf
    from ainiee_translate.export import export_project
    from ainiee_translate.reading_round import freeze_round
    from ainiee_translate.reading_finalization import record_reading_completion,finalize_round
    import ainiee_translate.reading_finalization as finalization
    work=tmp_path/'work'; book,target,cf,manifest,context=make_bound(work)
    project=cache_io.load_cache(work/'cache.json'); project.project_id='synthetic-pdf-reading'
    project.files['source.pdf'].extra['ainiee_pdf']['book_source']='book.source.json'
    cache_io.save_cache(project,work/'cache.json')
    export_project(project,str(tmp_path/'baseline'),str(work),formats=['epub'],cache_root=work,publication_context=context)
    reading=next((tmp_path/'baseline').rglob('book.epub')); rd=work/'reading/R0001'
    freeze_round(work/'cache.json',reading,work/'source.pdf',storage_path='source.pdf',round_dir=rd,glossary_path=work/'glossary.json',prompt_path=work/'prompt.txt')
    record_reading_completion(rd,human_instruction='SYNTHETIC: whole book read',human_reference='synthetic:test')
    merge(rd,snapshot([]))
    def compile_stub(source,*,engine,output_path):
        Path(output_path).write_bytes(b'%PDF-synthetic-compiler-output')
        return {'status':'passed'}
    monkeypatch.setattr(book_pdf,'compile_book_pdf',compile_stub)
    monkeypatch.setattr(finalization,'check_epub',lambda path:{'structure':{'status':'passed'},'epubcheck':{'status':'passed'}})
    result=finalize_round(rd,work/'cache.json',output_dir=rd/'final',publication_context={**context,'formats':['pdf'],'pdf_engines':['latex'],'book_settings':{}})
    assert result['validation_mode']=='synthetic'
    assert (rd/'final/latex.pdf').read_bytes()==b'%PDF-synthetic-compiler-output'
    assert (rd/'final/book.epub').is_file()
