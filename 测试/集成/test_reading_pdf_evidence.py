import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'单元'))
from test_reading_report import ready
from test_reading_decisions import prepare

def test_changed_pdf_unit_requires_new_target_proof(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_finalization import finalization_status
    from reading_sample import create_project
    from ainiee_translate.reading_round import freeze_round
    from ainiee_translate.reading_match import match_issues
    from ainiee_translate.reading_review import export_assessment_tasks,import_assessments
    from ainiee_translate.artifact_io import sha256
    from test_reading_review import result_for
    from test_weread_notes import merge,snapshot
    import pymupdf
    root=create_project(tmp_path); rd=root/'work/reading/R0001'
    doc=pymupdf.open(); page=doc.new_page(); page.insert_text((50,50),'A quiet lamp lights the window.'); doc.save(root/'input/source.pdf'); doc.close()
    p=cache_io.load_cache(root/'cache.json'); it=p.files['source.epub'].items[1]
    it.extra['ainiee_pdf']={'unit_id':'unit-2','document_id':'synthetic-pdf','source_refs':[{'page':1}],
                          'proofreading':{'status':'passed','independent':True,'target_sha256':'old'}}
    cache_io.save_cache(p,root/'cache.json')
    freeze_round(root/'cache.json',root/'reading.epub',root/'input/source.pdf',storage_path='source.epub',round_dir=rd,glossary_path=root/'glossary.json',prompt_path=root/'prompt.md')
    merge(rd,snapshot()); match_issues(rd); t=export_assessment_tasks(rd,root/'cache.json'); result=result_for(t)
    result['issues'][0]['evidence']=[dict(kind='pdf',pdf_sha256=sha256(root/'input/source.pdf'),pages=[1],observations='Synthetic fixture, not human page observation')]
    import_assessments(rd,result)
    d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    it=cache_io.load_cache(root/'cache.json').files['source.epub'].items[1]
    assert 'proofreading' not in it.extra['ainiee_pdf']
    assert it.extra['ainiee_pdf']['proofreading_history']
    assert 'unit-2' in finalization_status(rd,root/'cache.json')['changed_pdf_unit_ids']

def test_preserve_source_proof_uses_effective_source_target(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.pdf_bridge import contract
    from ainiee_translate.reading_finalization import finalization_status
    root,rd,t=ready(tmp_path); p=cache_io.load_cache(root/'cache.json'); it=p.files['source.epub'].items[0]
    it.translation_status=7; it.translated_text=''
    it.extra['ainiee_pdf']={'unit_id':'preserved','translation_policy':'preserve_source',
        'proofreading':{'status':'passed','independent':True,'target_sha256':contract().content_digest(it.source_text)}}
    cache_io.save_cache(p,root/'cache.json')
    assert 'preserved' not in finalization_status(rd,root/'cache.json')['changed_pdf_unit_ids']
