import copy
import pytest
from test_reading_report import ready

def prepare(root,rd,**overrides):
    from ainiee_translate.reading_report import render_report
    from ainiee_translate.reading_round import read
    report_path=render_report(rd)
    report=read(report_path.with_suffix('.json'))
    row=report['issues'][0]
    d=dict(issue_id=row['issue_id'],action='accept',report_revision=report['report_revision'],
           assessment_revision=row['assessment_revision'],annotation_revision=row['annotation_revision'],
           human_instruction='接受 1',human_reference='chat:user:accept-1')
    d.update(overrides)
    return dict(schema='reading-decisions/1',decisions=[d])

def test_accept_uses_displayed_recommendation(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate import cache_io
    root,rd,t=ready(tmp_path)
    d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    assert d['selected_text']=='一盏宁静的灯照着窗户。'
    assert apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])['applied']==1
    assert cache_io.load_cache(root/'cache.json').files['source.epub'].items[1].translated_text=='一盏宁静的灯照着窗户。'

@pytest.mark.parametrize('action', ['candidate','keep','defer','custom'])
def test_choose_b_keep_defer_custom(tmp_path,action):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate.reading_round import load_issues
    root,rd,t=ready(tmp_path)
    opts=dict(action=action,candidate='A')
    if action=='custom': opts.update(selected_text='自定的一盏灯。',edits=[dict(segment_id='source.epub#2',replacement_text='自定的一盏灯。')])
    d=record_decisions(rd,prepare(root,rd,**opts))['decisions'][0]
    if action in ('keep','defer'):
        assert load_issues(rd)['issues'][0]['status']==('kept' if action=='keep' else 'deferred')
    else:
        assert apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])['applied']==1

def test_discussion_without_human_instruction_is_not_approval(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions
    root,rd,t=ready(tmp_path)
    with pytest.raises(ValueError): record_decisions(rd,prepare(root,rd,human_instruction=''))

def test_changed_assessment_rejects_old_approval(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions
    from ainiee_translate.reading_review import import_assessments
    from test_reading_review import result_for
    root,rd,t=ready(tmp_path); old=prepare(root,rd)
    import_assessments(rd,result_for(t,'一盏柔和的灯照着窗户。'))
    with pytest.raises(ValueError): record_decisions(rd,old)

def test_cross_round_short_number_rejected(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions
    root,rd,t=ready(tmp_path)
    with pytest.raises(ValueError): record_decisions(rd,prepare(root,rd,issue_id='1'))

def test_retry_after_cache_write_recovers_once(tmp_path,monkeypatch):
    import ainiee_translate.reading_decisions as mod
    from ainiee_translate.reading_round import load_issues
    root,rd,t=ready(tmp_path); d=mod.record_decisions(rd,prepare(root,rd))['decisions'][0]
    original=mod._save_transaction
    def crash(rd,txn):
        if txn['state']=='cache_written': raise RuntimeError('crash after cache')
        return original(rd,txn)
    monkeypatch.setattr(mod,'_save_transaction',crash)
    with pytest.raises(RuntimeError): mod.apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    monkeypatch.setattr(mod,'_save_transaction',original)
    assert mod.recover_transactions(rd,root/'cache.json')['recovered']==1
    assert load_issues(rd)['issues'][0]['status']=='applied'
    assert mod.apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])['applied']==0

def test_recover_before_cache_write(tmp_path,monkeypatch):
    import ainiee_translate.reading_decisions as mod
    from ainiee_translate import cache_io
    from ainiee_translate.reading_round import load_issues
    root,rd,t=ready(tmp_path); d=mod.record_decisions(rd,prepare(root,rd))['decisions'][0]
    def crash(*args,**kw): raise RuntimeError('before cache')
    monkeypatch.setattr(cache_io,'apply_writeback',crash)
    with pytest.raises(RuntimeError): mod.apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    assert mod.recover_transactions(rd,root/'cache.json')['recovered']==1
    assert load_issues(rd)['issues'][0]['status']=='approved_pending_apply'

def test_undo_preserves_later_edits(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions,undo_transaction
    from ainiee_translate import cache_io
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    result=apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='后来的修改'
    cache_io.save_cache(p,root/'cache.json')
    undo=undo_transaction(rd,root/'cache.json',transaction_id=result['transaction_ids'][0],human_instruction='撤回这次修改；chat:user:undo')
    assert undo['conflicts']==1
    assert cache_io.load_cache(root/'cache.json').files['source.epub'].items[1].translated_text=='后来的修改'
