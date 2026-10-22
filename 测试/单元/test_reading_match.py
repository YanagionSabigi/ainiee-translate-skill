import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).parents[1]/'夹具'))
from reading_sample import create_project
from test_reading_round import freeze
from test_weread_notes import snapshot,mark,merge

def setup_round(tmp_path,text):
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    merge(rd,snapshot([mark(text=text)])); return root,rd

def test_duplicate_text_remains_ambiguous(tmp_path):
    from ainiee_translate.reading_match import match_issues
    _,rd=setup_round(tmp_path,'河流记得每一块石头。')
    issue=match_issues(rd)['issues'][0]
    assert issue['status']=='needs_location'
    assert len(issue['matching']['candidates'])==2

def test_cross_paragraph_match_keeps_each_segment(tmp_path):
    from ainiee_translate.reading_match import match_issues
    _,rd=setup_round(tmp_path,'在这里结束。\n后半句从这里')
    issue=match_issues(rd)['issues'][0]
    assert issue['status']=='needs_assessment'
    assert [x['segment_id'] for x in issue['matching']['selected']]==['source.epub#3','source.epub#4']

def test_cross_paragraph_without_remote_separator(tmp_path):
    from ainiee_translate.reading_match import match_issues
    _,rd=setup_round(tmp_path,'在这里结束。后半句从这里')
    issue=match_issues(rd)['issues'][0]
    assert issue['status']=='needs_assessment'
    assert len(issue['matching']['selected'])==2

def test_unicode_offsets_are_local_and_reversible():
    from ainiee_translate.reading_match import normalize_with_offsets
    text='<i>cafe\u0301</i>&nbsp;😀  路'
    norm, offsets=normalize_with_offsets(text)
    assert norm=='café 😀 路'
    assert text[slice(*offsets[3])]=='e\u0301'
    assert text[slice(*offsets[4])]=='&nbsp;'
    assert text[slice(*offsets[5])]=='😀'

def test_round_edition_not_current_cache_used_for_selection(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_match import match_issues
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。')
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='后来改变'
    cache_io.save_cache(p,root/'cache.json')
    assert match_issues(rd)['issues'][0]['matching']['selected'][0]['segment_id']=='source.epub#2'

def test_explicit_location_override_validates_edition(tmp_path):
    from ainiee_translate.reading_match import match_issues,record_match_override
    from ainiee_translate.reading_round import load_round
    _,rd=setup_round(tmp_path,'河流记得每一块石头。'); i=match_issues(rd)['issues'][0]
    m=dict(issue_id=i['issue_id'],annotation_revision=1,edition_id='wrong',
           segments=i['matching']['candidates'][0],actor='human',evidence='用户明确选择第一章')
    with pytest.raises(ValueError): record_match_override(rd,m)
    m['edition_id']=load_round(rd)['edition_id']; m['segments'][0]['end']=99999
    with pytest.raises(ValueError): record_match_override(rd,m)
    m['segments']=i['matching']['candidates'][1]
    assert record_match_override(rd,m)['issues'][0]['status']=='needs_assessment'

def test_same_item_duplicate_units_keep_resolvable_alternatives(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_match import match_issues,record_match_override
    from ainiee_translate.reading_round import load_round
    from test_weread_notes import merge,snapshot,mark
    root=create_project(tmp_path); p=cache_io.load_cache(root/'cache.json')
    for pos in (0,4):
        it=p.files['source.epub'].items[pos]; it.extra.update(item_id='c1',original_html='<p>The river remembers every stone.</p>')
    cache_io.save_cache(p,root/'cache.json'); freeze(root); rd=root/'work/reading/R0001'
    merge(rd,snapshot([mark(text='河流记得每一块石头。')]))
    i=match_issues(rd)['issues'][0]
    assert i['status']=='needs_location' and len(i['matching']['candidates'])>=2
    record_match_override(rd,dict(issue_id=i['issue_id'],annotation_revision=1,edition_id=load_round(rd)['edition_id'],
                                 segments=i['matching']['candidates'][0],actor='synthetic-explicit-choice',evidence='Synthetic actor reviewed the first candidate in its context'))

def test_explicit_thought_link_survives_unchanged_resync(tmp_path):
    from ainiee_translate.reading_match import record_match_override,_candidates
    from ainiee_translate.reading_round import load_round,load_issues
    from test_weread_notes import merge,snapshot,mark,thought
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    merge(rd,snapshot([mark(),mark('other',style=4)],[thought()]))
    i=load_issues(rd)['issues'][0]
    record_match_override(rd,dict(issue_id=i['issue_id'],annotation_revision=1,edition_id=load_round(rd)['edition_id'],
              segments=_candidates(rd,i)[0],linked_review_ids=['r'],discarded_review_ids=[],
              actor='synthetic-human-confirmation',evidence='Synthetic user explicitly confirms this thought belongs to the blue highlight'))
    merge(rd,snapshot([mark(),mark('other',style=4)],[thought()]))
    i=load_issues(rd)['issues'][0]
    assert i['annotation_revision']==1 and i['status']=='needs_assessment'
    assert [t['review_id'] for t in i['note']['thoughts']]==['r']


def test_thought_links_can_be_resolved_in_two_steps(tmp_path):
    from ainiee_translate.reading_match import record_match_override,_candidates
    from ainiee_translate.reading_round import load_round,load_issues
    from test_weread_notes import thought
    root=create_project(tmp_path); freeze(root); rd=root/'work/reading/R0001'
    def sync():
        return merge(rd,snapshot([mark(),mark('other',style=4)],[thought('r'),thought('s')]))
    sync()
    for review_id in ('r','s'):
        i=load_issues(rd)['issues'][0]
        record_match_override(rd,dict(issue_id=i['issue_id'],annotation_revision=1,edition_id=load_round(rd)['edition_id'],
              segments=_candidates(rd,i)[0],linked_review_ids=[review_id],
              actor='synthetic-human-confirmation',evidence='Synthetic confirmation of one thought at a time'))
    i=sync()['issues'][0]
    assert i['annotation_revision']==1 and i['status']=='needs_assessment'
    assert [t['review_id'] for t in i['note']['thoughts']]==['r','s']
