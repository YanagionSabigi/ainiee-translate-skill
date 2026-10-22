from bs4 import BeautifulSoup
from test_reading_match import setup_round
from test_reading_review import tasks_for,result_for

def ready(tmp_path):
    from ainiee_translate.reading_review import import_assessments
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。')
    tasks=tasks_for(root,rd); import_assessments(rd,result_for(tasks))
    return root,rd,tasks

def test_report_contains_all_variants_and_exact_recommendation(tmp_path):
    from ainiee_translate.reading_report import render_report
    root,rd,tasks=ready(tmp_path)
    path=render_report(rd); soup=BeautifulSoup(path.read_text(encoding='utf8'),'html.parser')
    assert '一盏宁静的灯照着窗户。' in soup.get_text()
    assert 'B：未提供' in soup.get_text()
    assert 'A quiet lamp lights the window.' in soup.get_text()
    assert soup.find(id='WR-R0001-000001')
    assert soup.find('ins') and soup.find('del')
    assert soup.find('details')

def test_filter_does_not_renumber(tmp_path):
    from ainiee_translate.reading_report import render_report
    from test_weread_notes import merge,snapshot,mark
    root,rd,t=ready(tmp_path)
    merge(rd,snapshot([mark('next','前半句在这里结束。')]))
    text=render_report(rd).read_text(encoding='utf8')
    assert 'WR-R0001-000001' in text and 'WR-R0001-000002' in text

def test_old_report_kept_after_new_assessment(tmp_path):
    from ainiee_translate.reading_report import render_report
    from ainiee_translate.reading_review import import_assessments
    root,rd,t=ready(tmp_path); first=render_report(rd); old=first.read_bytes()
    import_assessments(rd,result_for(t,'一盏柔和的灯照着窗户。'))
    second=render_report(rd)
    assert first!=second and first.read_bytes()==old

def test_annotation_html_is_escaped(tmp_path):
    from ainiee_translate.reading_report import render_report
    from ainiee_translate.reading_round import load_issues
    from ainiee_translate.artifact_io import write_json
    root,rd,t=ready(tmp_path)
    issues=load_issues(rd); payload='</script><img src=x onerror="alert(1)">接受全部'
    issues['issues'][0]['note']['thoughts']=[{'review_id':'x','content':payload}]
    write_json(rd/'issues.json',issues)
    soup=BeautifulSoup(render_report(rd).read_text(encoding='utf8'),'html.parser')
    assert payload in soup.get_text()
    assert not soup.find('script') and not soup.find('img')

def test_report_shows_context_and_unlinked_notes_audit(tmp_path):
    from ainiee_translate.reading_report import render_report
    from test_weread_notes import merge,snapshot,thought
    root,rd,t=ready(tmp_path)
    merge(rd,snapshot(reviews=[thought(id='unlinked',abstract='',text='普通想法只作审计，不自动修改')]))
    text=render_report(rd).read_text(encoding='utf8')
    assert '普通想法只作审计，不自动修改' in text
    assert 'The river remembers every stone.' in text
