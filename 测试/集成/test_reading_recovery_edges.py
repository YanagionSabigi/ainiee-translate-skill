import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'单元'))
from test_reading_report import ready
from test_reading_decisions import prepare

def test_recovery_does_not_reproject_older_apply_after_undo(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions,undo_transaction,recover_transactions
    from ainiee_translate.reading_round import load_issues
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    a=apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    undo_transaction(rd,root/'cache.json',transaction_id=a['transaction_ids'][0],human_instruction='撤回；chat:test')
    assert recover_transactions(rd,root/'cache.json')['recovered']==0
    assert load_issues(rd)['issues'][0]['status']=='needs_assessment'

def test_same_target_approval_is_idempotent_but_other_decision_conflicts(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    root,rd,t=ready(tmp_path)
    first=record_decisions(rd,prepare(root,rd))['decisions'][0]
    identical=record_decisions(rd,prepare(root,rd))['decisions'][0]
    result=apply_decisions(rd,root/'cache.json',decision_ids=[first['decision_id'],identical['decision_id']])
    assert result['applied']==2 and result['conflicts']==0

def test_conflict_can_be_resolved_by_fresh_assessment_and_explicit_keep(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_review import export_assessment_tasks,import_assessments
    from ainiee_translate.reading_finalization import finalization_status
    from test_reading_review import result_for
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='另一位译者的版本'
    cache_io.save_cache(p,root/'cache.json')
    assert apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])['conflicts']==1
    tasks=export_assessment_tasks(rd,root/'cache.json'); import_assessments(rd,result_for(tasks))
    record_decisions(rd,prepare(root,rd,action='keep',human_instruction='保留当前工作译文；关闭冲突'))
    assert not any(b.startswith('transaction:') for b in finalization_status(rd,root/'cache.json')['blockers'])

def test_unrelated_decisions_can_apply_despite_conflict(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_match import match_issues
    from ainiee_translate.reading_review import export_assessment_tasks,import_assessments
    from ainiee_translate.reading_report import render_report
    from ainiee_translate.reading_round import read
    from test_weread_notes import merge,snapshot,mark
    from test_reading_review import result_for
    root,rd,t=ready(tmp_path)
    merge(rd,snapshot([mark(),mark('second','前半句在这里结束。')]))
    match_issues(rd); tasks=export_assessment_tasks(rd,root/'cache.json')
    rows=[]
    for task in tasks['issues']:
        row=result_for(dict(issues=[task],task_revision=tasks['task_revision']))['issues'][0]
        rows.append(row)
    import_assessments(rd,dict(task_revision=tasks['task_revision'],issues=rows))
    report=read(render_report(rd).with_suffix('.json'))
    ds=record_decisions(rd,dict(decisions=[dict(issue_id=i['issue_id'],action='accept',report_revision=report['report_revision'],assessment_revision=i['assessment_revision'],annotation_revision=i['annotation_revision'],human_instruction='接受这两项',human_reference='synthetic:test') for i in report['issues']]))['decisions']
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='并发修改'
    cache_io.save_cache(p,root/'cache.json')
    result=apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id'] for d in ds])
    assert result['applied']==1 and result['conflicts']==1

@pytest.mark.parametrize('action',['keep','defer'])
def test_new_keep_or_defer_supersedes_old_accept(tmp_path,action):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate import cache_io
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    record_decisions(rd,prepare(root,rd,action=action,human_instruction='保留或搁置当前译文'))
    assert apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])['applied']==0
    assert cache_io.load_cache(root/'cache.json').files['source.epub'].items[1].translated_text=='一盏安静的灯照着窗户。'

def test_recovery_records_old_write_without_closing_new_annotation(tmp_path,monkeypatch):
    import ainiee_translate.reading_decisions as mod
    from ainiee_translate.reading_round import load_issues
    from test_weread_notes import merge,snapshot,thought
    root,rd,t=ready(tmp_path); d=mod.record_decisions(rd,prepare(root,rd))['decisions'][0]
    original=mod._save_transaction
    def crash(rd,txn):
        if txn['state']=='cache_written': raise RuntimeError('crash')
        return original(rd,txn)
    monkeypatch.setattr(mod,'_save_transaction',crash)
    with pytest.raises(RuntimeError): mod.apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    monkeypatch.setattr(mod,'_save_transaction',original)
    merge(rd,snapshot(reviews=[thought(text='新的意见，请重新核查')]))
    mod.recover_transactions(rd,root/'cache.json')
    i=load_issues(rd)['issues'][0]
    assert i['annotation_revision']==2 and i['status']=='stale'

def test_applied_target_changed_by_other_writer_reopens(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_finalization import finalization_status
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_round import load_issues
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='后来另改'
    cache_io.save_cache(p,root/'cache.json')
    assert any('stale' in b for b in finalization_status(rd,root/'cache.json')['blockers'])
    assert load_issues(rd)['issues'][0]['status']=='stale'

def test_same_text_reparsed_to_different_item_is_rejected(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].extra['item_id']='a-reparsed-different-chapter'
    cache_io.save_cache(p,root/'cache.json')
    assert apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])['applied']==0

def test_different_issues_with_overlapping_edits_do_not_overwrite(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_review import export_assessment_tasks,import_assessments
    from ainiee_translate.reading_match import match_issues
    from ainiee_translate.reading_report import render_report
    from ainiee_translate.reading_round import read
    from ainiee_translate import cache_io
    from test_weread_notes import merge,snapshot,mark
    from test_reading_review import result_for
    root,rd,t=ready(tmp_path); merge(rd,snapshot([mark(),mark('second','安静')]))
    match_issues(rd); tasks=export_assessment_tasks(rd,root/'cache.json')
    rows=[result_for(dict(issues=[task],task_revision=tasks['task_revision']),text=('一盏宁静的灯照着窗户。' if pos==0 else '另一套修改'))['issues'][0] for pos,task in enumerate(tasks['issues'])]
    import_assessments(rd,dict(task_revision=tasks['task_revision'],issues=rows)); report=read(render_report(rd).with_suffix('.json'))
    ds=record_decisions(rd,dict(decisions=[dict(issue_id=i['issue_id'],action='accept',report_revision=report['report_revision'],assessment_revision=i['assessment_revision'],annotation_revision=1,human_instruction='接受这两条',human_reference='synthetic:test') for i in report['issues']]))['decisions']
    result=apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id'] for d in ds])
    assert result['applied']==1 and result['conflicts']==1
    assert cache_io.load_cache(root/'cache.json').files['source.epub'].items[1].translated_text=='一盏宁静的灯照着窗户。'
