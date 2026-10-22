import copy
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'夹具'))
from reading_sample import create_project
from test_reading_round import freeze

PROFILE=dict(schema='weread-capabilities/1', verified=False, synthetic=True, blue_wave_style=17,
             deletion_semantics_verified=True, highlights_snapshot_complete=True, evidence_reference='invented fixture')

def snapshot(highlights=None, reviews=None, **kw):
    from ainiee_translate.reading_round import revision
    d=dict(schema='weread-snapshot/1',snapshot_id=revision(),book_id='b',skill_version='test',requests=[],
           responses={'highlights':{'updated':highlights if highlights is not None else [mark()]},
                      'reviews':[{'reviews':reviews or [],'hasMore':0}]},
           completeness={'reviews_complete':True,'highlights_complete':False,'deletion_semantics_verified':False})
    d.update(kw); return d

def mark(id='h',text='一盏安静的灯照着窗户。',style=17):
    return dict(bookId='b',bookmarkId=id,chapterUid=1,markText=text,range='1-12',colorStyle=style,type=1)

def thought(id='r',text='这里不通顺',**kw):
    r=dict(reviewId=id,content=text,abstract='一盏安静的灯照着窗户。',chapterUid=1,range='1-12'); r.update(kw)
    return {'review':r}

def merge(rd,s,profile=None):
    from ainiee_translate.weread_notes import normalize_snapshot,merge_snapshot
    return merge_snapshot(rd,normalize_snapshot(s,style_profile=profile or PROFILE))

def test_blue_style_requires_verified_profile():
    from ainiee_translate.weread_notes import normalize_snapshot
    with pytest.raises(ValueError): normalize_snapshot(snapshot(),style_profile={**PROFILE,'synthetic':False})
    assert not normalize_snapshot(snapshot([mark(style='17')]),style_profile=PROFILE)['notes']

def test_blue_without_thought_is_issue(tmp_path):
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    issues=merge(rd,snapshot())['issues']
    assert issues[0]['note']['thoughts']==[]
    assert issues[0]['issue_id']=='WR-R0001-000001'

def test_other_colors_excluded():
    from ainiee_translate.weread_notes import normalize_snapshot
    assert not normalize_snapshot(snapshot([mark(style=4)]),style_profile=PROFILE)['notes']

def test_ambiguous_thought_link_retained(tmp_path):
    from ainiee_translate.weread_notes import normalize_snapshot
    n=normalize_snapshot(snapshot([mark('a'),mark('b')],[thought()]),style_profile=PROFILE)
    assert len(n['unlinked_reviews'])==1
    assert all(note['needs_link'] for note in n['notes'])
    assert all(not note['thoughts'] for note in n['notes'])

def test_repeat_sync_keeps_ids(tmp_path):
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    first=merge(rd,snapshot(reviews=[thought('r'),thought('s')]))
    second=merge(rd,snapshot(reviews=[thought('s'),thought('r')]))
    assert len(second['issues'])==1
    assert second['issues'][0]['annotation_revision']==1
    assert second['issues'][0]['issue_id']==first['issues'][0]['issue_id']

def test_edit_reopens_without_reusing_approval(tmp_path):
    from ainiee_translate.artifact_io import write_json
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    i=merge(rd,snapshot(reviews=[thought()]))
    i['issues'][0].update(status='approved_pending_apply',current_assessment_revision='old')
    write_json(rd/'issues.json',i)
    new=merge(rd,snapshot(reviews=[thought(text='改了想法')]))['issues'][0]
    assert new['annotation_revision']==2
    assert new['current_assessment_revision'] is None
    assert new['status']=='stale'
    assert new['history'][-1]['status']=='approved_pending_apply'

def test_partial_snapshot_does_not_delete(tmp_path):
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    merge(rd,snapshot())
    s=snapshot([]); s['completeness']['reviews_complete']=False
    assert merge(rd,s)['issues'][0]['status']=='missing_unconfirmed'

def test_confirmed_delete_does_not_undo_applied_edit(tmp_path):
    from ainiee_translate.artifact_io import write_json
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    i=merge(rd,snapshot()); i['issues'][0]['status']='applied'; write_json(rd/'issues.json',i)
    assert merge(rd,snapshot([]))['issues'][0]['status']=='remote_deleted'
    assert (root/'cache.json').read_bytes()==(rd/'edition/cache.frozen.json').read_bytes()

def test_color_change_is_out_of_scope_not_deleted(tmp_path):
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    merge(rd,snapshot())
    assert merge(rd,snapshot([mark(style=4)]))['issues'][0]['status']=='out_of_scope'

def test_other_color_duplicate_does_not_steal_thought():
    from ainiee_translate.weread_notes import normalize_snapshot
    n=normalize_snapshot(snapshot([mark(),mark('orange',style=4)],[thought()]),style_profile=PROFILE)
    assert n['notes'][0]['needs_link']
    assert not n['notes'][0]['thoughts']

def test_confirmed_tombstone_survives_partial_sync(tmp_path):
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    merge(rd,snapshot()); merge(rd,snapshot([]))
    s=snapshot([]); s['completeness']['reviews_complete']=False
    assert merge(rd,s)['issues'][0]['status']=='remote_deleted'
