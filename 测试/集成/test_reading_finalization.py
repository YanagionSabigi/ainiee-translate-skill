import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'单元'))
from test_reading_report import ready
from test_reading_decisions import prepare
from test_weread_notes import snapshot,merge

def closed(root,rd):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_finalization import record_reading_completion
    d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    record_reading_completion(rd,human_instruction='整本已读完',human_reference='chat:user:finished')
    merge(rd,snapshot())

@pytest.mark.parametrize('state',['needs_link','needs_location','deferred','stale','conflict','approved_pending_apply','needs_assessment','needs_approval','missing_unconfirmed'])
def test_whole_book_gate_has_no_stage_release(tmp_path,state):
    from ainiee_translate.reading_finalization import finalization_status,finalize_round
    from ainiee_translate.reading_round import load_issues
    from ainiee_translate.artifact_io import write_json
    root,rd,t=ready(tmp_path); closed(root,rd)
    issues=load_issues(rd); issues['issues'][0]['status']=state; write_json(rd/'issues.json',issues)
    assert any(state in b for b in finalization_status(rd,root/'cache.json')['blockers'])
    with pytest.raises(ValueError): finalize_round(rd,root/'cache.json',output_dir=rd/'final',publication_context={})
    assert not (rd/'final').exists()

def test_epubcheck_unavailable_is_not_final_pass(tmp_path,monkeypatch):
    import ainiee_translate.reading_finalization as mod
    root,rd,t=ready(tmp_path); closed(root,rd)
    monkeypatch.setattr(mod,'check_epub',lambda path:{'structure':{'status':'passed'},'epubcheck':{'status':'unavailable'}})
    with pytest.raises(ValueError,match='EPUBCheck'): mod.finalize_round(rd,root/'cache.json',output_dir=rd/'final',publication_context={})
    assert not (rd/'final').exists()

def test_sync_during_finalization_blocks_delivery(tmp_path,monkeypatch):
    import ainiee_translate.reading_finalization as mod
    root,rd,t=ready(tmp_path); closed(root,rd)
    def changed(path):
        merge(rd,snapshot())
        return {'structure':{'status':'passed'},'epubcheck':{'status':'passed'}}
    monkeypatch.setattr(mod,'check_epub',changed)
    with pytest.raises(ValueError,match='changed'): mod.finalize_round(rd,root/'cache.json',output_dir=rd/'final',publication_context={})
    assert not (rd/'final').exists()

def test_completion_requires_human_reference_and_final_sync(tmp_path):
    from ainiee_translate.reading_finalization import record_reading_completion,finalization_status
    root,rd,t=ready(tmp_path)
    with pytest.raises(ValueError): record_reading_completion(rd,human_instruction=' ',human_reference='chat')
    record_reading_completion(rd,human_instruction='整本读完',human_reference='chat:finished')
    assert 'final_complete_sync_required' in finalization_status(rd,root/'cache.json')['blockers']

def test_source_ocr_fix_reconciles_and_reopens_issues(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_finalization import finalization_status
    from ainiee_translate.reading_round import load_issues
    root,rd,t=ready(tmp_path); closed(root,rd)
    frozen=(rd/'edition/cache.frozen.json').read_bytes()
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].source_text='Reconciled source correction'
    cache_io.save_cache(p,root/'cache.json')
    assert finalization_status(rd,root/'cache.json')['blockers']
    assert load_issues(rd)['issues'][0]['status']=='stale'
    assert (rd/'edition/cache.frozen.json').read_bytes()==frozen
