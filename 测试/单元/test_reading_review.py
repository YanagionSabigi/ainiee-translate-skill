import copy
from pathlib import Path
import pytest
from test_reading_match import setup_round

def tasks_for(root,rd):
    from ainiee_translate.reading_match import match_issues
    from ainiee_translate.reading_review import export_assessment_tasks
    match_issues(rd)
    return export_assessment_tasks(rd,root/'cache.json')

def result_for(tasks, text='一盏宁静的灯照着窗户。'):
    task=tasks['issues'][0]
    sid=task['segments'][0]['segment_id']
    return dict(schema='reading-assessments/1',task_revision=tasks['task_revision'],
                issues=[dict(issue_id=task['issue_id'],annotation_revision=task['annotation_revision'],
                             segments=task['segments'],candidates=[
                                 {'label':'A','text':task['segments'][0]['current_target_text'],
                                  'edits':[{'segment_id':sid,'replacement_text':task['segments'][0]['current_target_text']}]},
                                 {'label':'C','text':text,'edits':[{'segment_id':sid,'replacement_text':text}]}],
                             recommended_candidate='C',recommended_text=text,rationale='更自然，仍有拟人语气。',uncertainties=[],
                             evidence=[{'kind':'epub','href':'OEBPS/c1.xhtml','observations':'对照原文 quiet，保留意象'}])])

def test_tasks_include_frozen_and_current_context(tmp_path):
    from ainiee_translate import cache_io
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。')
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].translated_text='当前工作译文'
    cache_io.save_cache(p,root/'cache.json')
    t=tasks_for(root,rd); row=t['issues'][0]
    assert row['selected_reading_text']=='一盏安静的灯照着窗户。'
    assert row['segments'][0]['current_target_text']=='当前工作译文'
    assert row['segments'][0]['source_text']=='A quiet lamp lights the window.'
    assert row['context']

def test_assessment_rejects_fabricated_b_and_stale_input(tmp_path):
    from ainiee_translate.reading_review import import_assessments
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。'); t=tasks_for(root,rd)
    r=result_for(t); r['issues'][0]['candidates'][1]['label']='B'
    with pytest.raises(ValueError): import_assessments(rd,r)
    r=result_for(t); r['issues'][0]['annotation_revision']=99
    with pytest.raises(ValueError): import_assessments(rd,r)
    good=import_assessments(rd,result_for(t))
    assert good['issues'][0]['recommended_text']=='一盏宁静的灯照着窗户。'

def test_expanded_findings_have_independent_ids(tmp_path):
    from ainiee_translate.reading_review import import_assessments
    from ainiee_translate.reading_round import load_issues
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。'); t=tasks_for(root,rd)
    r=result_for(t); r['expanded_findings']=[dict(origin_issue_id=t['issues'][0]['issue_id'],
         problem_key='similar-metaphor',segment_id='source.epub#1',note='另一个拟人句也请核查')]
    import_assessments(rd,r); import_assessments(rd,r)
    issues=load_issues(rd)['issues']
    assert len(issues)==2 and issues[1]['origin_issue_id']==issues[0]['issue_id']
    assert issues[1]['status']=='needs_assessment'

def test_unknown_source_does_not_get_fake_pdf_evidence(tmp_path):
    from ainiee_translate import cache_io
    from ainiee_translate.reading_review import import_assessments
    from reading_sample import create_project
    from test_reading_round import freeze
    from test_weread_notes import merge,snapshot,mark
    root=create_project(tmp_path); rd=root/'work/reading/R0001'
    p=cache_io.load_cache(root/'cache.json'); p.files['source.epub'].items[1].extra['ainiee_pdf']={'unit_id':'u1','document_id':'doc'}
    cache_io.save_cache(p,root/'cache.json')
    freeze(root); merge(rd,snapshot([mark()]))
    t=tasks_for(root,rd); r=result_for(t)
    with pytest.raises(ValueError, match='PDF'): import_assessments(rd,r)

def test_explicit_partial_user_proposal_can_form_full_segment_b(tmp_path):
    from ainiee_translate.reading_review import import_assessments
    from test_weread_notes import merge,snapshot,thought
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。')
    merge(rd,snapshot(reviews=[thought(text='把安静改为柔和')]))
    t=tasks_for(root,rd); r=result_for(t)
    row=r['issues'][0]; row['candidates'][1].update(label='B',text='一盏柔和的灯照着窗户。',edits=[dict(segment_id='source.epub#2',replacement_text='一盏柔和的灯照着窗户。')])
    row.update(recommended_candidate='B',recommended_text='一盏柔和的灯照着窗户。',
               user_proposal=dict(review_id='r',text='柔和',segment_id='source.epub#2',start=2,end=4,source_excerpt='安静'))
    assert import_assessments(rd,r)['issues'][0]['recommended_candidate']=='B'
