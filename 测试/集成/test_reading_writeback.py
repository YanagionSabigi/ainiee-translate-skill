import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).parents[1]/'单元'))
from test_reading_report import ready
from test_reading_decisions import prepare

def test_concurrent_writer_rejected_inside_lock(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    root,rd,t=ready(tmp_path); d=record_decisions(rd,prepare(root,rd))['decisions'][0]
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='同时修改'
    cache_io.save_cache(p,root/'cache.json')
    r=apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id']])
    assert r['conflicts']==1
    assert cache_io.load_cache(root/'cache.json').files['source.epub'].items[1].translated_text=='同时修改'

def test_new_same_issue_decision_supersedes_old_accept(tmp_path):
    from ainiee_translate.reading_decisions import record_decisions,apply_decisions
    from ainiee_translate import cache_io
    root,rd,t=ready(tmp_path)
    first=record_decisions(rd,prepare(root,rd))['decisions'][0]
    second=record_decisions(rd,prepare(root,rd,action='custom',selected_text='另一个版本',
            edits=[dict(segment_id='source.epub#2',replacement_text='另一个版本')]))['decisions'][0]
    r=apply_decisions(rd,root/'cache.json',decision_ids=[first['decision_id'],second['decision_id']])
    assert r['applied']==1 and r['conflicts']==1
    assert cache_io.load_cache(root/'cache.json').files['source.epub'].items[1].translated_text=='另一个版本'

def test_shared_cas_gate_cannot_be_forced(tmp_path):
    from ainiee_translate import cache_io
    root,rd,t=ready(tmp_path)
    r=cache_io.apply_writeback(str(root/'cache.json'),[{'text_index':2,'text':'unsafe'}],2,lambda x:x['text'],
         force=True,expected_source_sha256={},expected_target_sha256={})
    assert r.applied==0 and r.rejected[0]['reason']=='stale_source'
