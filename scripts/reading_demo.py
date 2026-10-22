"""Create/run an invented, offline proofreading project; never accesses an account.

Run from the repository: .venv/Scripts/python.exe scripts/reading_demo.py
Output defaults to local/reading-projects/offline-demo; refuses existing projects.
"""
import argparse
from pathlib import Path
import sys

REPO=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(REPO/'src'),str(REPO/'测试/夹具')]
from reading_sample import create_project
from ainiee_translate.artifact_io import write_json
from ainiee_translate.reading_round import freeze_round,revision,load_issues,load_round,read
from ainiee_translate.weread_notes import normalize_snapshot,merge_snapshot
from ainiee_translate.reading_match import match_issues,record_match_override
from ainiee_translate.reading_review import export_assessment_tasks,import_assessments
from ainiee_translate.reading_report import render_report
from ainiee_translate.reading_decisions import record_decisions,apply_decisions
from ainiee_translate.reading_finalization import record_reading_completion,finalize_round


def create_demo(root,*,finalize=False):
    root=Path(root)
    if root.exists(): raise FileExistsError('Choose a new project directory; existing evidence is preserved')
    create_project(root)
    rd=root/'work/reading/R0001'
    freeze_round(root/'cache.json',root/'reading.epub',root/'input/source.epub',storage_path='source.epub',round_dir=rd,
                 glossary_path=root/'glossary.json',prompt_path=root/'prompt.md')
    profile=dict(schema='weread-capabilities/1',verified=False,synthetic=True,blue_wave_style='invented-blue-wave',
                 deletion_semantics_verified=True,highlights_snapshot_complete=True,evidence_reference='self-authored fixture; no account evidence')
    write_json(root/'capabilities.synthetic.json',profile)
    quotes=['一盏安静的灯照着窗户。','前半句在这里结束。','一位仔细的读者看见 café 😀 和一条新路。',
            '河流记得每一块石头。','在这里结束。\n后半句从这里']
    marks=[dict(bookId='synthetic-book',bookmarkId=f'h{i}',markText=q,chapterUid=1,colorStyle=profile['blue_wave_style'],range='unverified') for i,q in enumerate(quotes)]
    marks.append(dict(bookId='synthetic-book',bookmarkId='other',markText='公式是 x² + y² = z²；参见注 [1]。',chapterUid=2,colorStyle='invented-orange'))
    thoughts=[{'review':dict(reviewId='r1',content='建议改为“一盏幽静的灯照着窗户。”',abstract=quotes[0],chapterUid=1)},
              {'review':dict(reviewId='r2',content='café 保留原拼写；emoji 不要丢失。',abstract=quotes[2],chapterUid=1)},
              {'review':dict(reviewId='r3',content='请核对强调。',abstract=quotes[2],chapterUid=1)}]
    def snapshot():
        return dict(schema='weread-snapshot/1',snapshot_id=revision(),book_id='synthetic-book',skill_version='synthetic',requests=[],
                    responses={'highlights':{'updated':marks},'reviews':[{'reviews':thoughts,'hasMore':0}]},
                    completeness=dict(reviews_complete=True,highlights_complete=False,deletion_semantics_verified=False))
    merge_snapshot(rd,normalize_snapshot(snapshot(),style_profile=profile))
    issues=match_issues(rd)
    for issue in issues['issues']:
        if issue['status']=='needs_location':
            record_match_override(rd,dict(issue_id=issue['issue_id'],annotation_revision=1,edition_id=load_round(rd)['edition_id'],
                  segments=issue['matching']['candidates'][0],actor='synthetic test fixture',evidence='Invented test explicitly selects first chapter; not account range verification'))
    tasks=export_assessment_tasks(rd,root/'cache.json'); rows=[]
    for task in tasks['issues']:
        parts=task['segments']; edits=[dict(segment_id=s['segment_id'],replacement_text=s['current_target_text']) for s in parts]
        a='\n'.join(e['replacement_text'] for e in edits)
        candidates=[dict(label='A',text=a,edits=edits)]
        row=dict(issue_id=task['issue_id'],annotation_revision=1,segments=parts,candidates=candidates,recommended_candidate='A',
                 recommended_text=a,rationale='自造测试：对照原句后保留当前译文。',uncertainties=[],
                 evidence=[dict(kind='epub',href=parts[0]['selection']['href'],observations='自造原文与译文逐段对照；并非账号或 PDF 原页实测')])
        if task['note']['excerpt']==quotes[0]:
            user='一盏幽静的灯照着窗户。'; ai='一盏灯静静地照着窗户。'; sid=parts[0]['segment_id']
            candidates.extend([dict(label='B',text=user,edits=[dict(segment_id=sid,replacement_text=user)]),
                               dict(label='C',text=ai,edits=[dict(segment_id=sid,replacement_text=ai)])])
            row.update(user_proposal=dict(review_id='r1',text=user),recommended_candidate='C',recommended_text=ai,
                       rationale='同意原译的搭配需要调整；“幽静”通常形容环境，因此提出第三种译法，用“静静地”表达 quiet 的安静氛围。',
                       uncertainties=['quiet 也可能包含微弱灯光的意象；结合上下文再决定。'])
        rows.append(row)
    import_assessments(rd,dict(task_revision=tasks['task_revision'],issues=rows))
    report=render_report(rd)
    if finalize:
        displayed=read(report.with_suffix('.json'))
        decisions=[]
        for entry in displayed['issues']:
            decisions.append(dict(issue_id=entry['issue_id'],action='accept',report_revision=displayed['report_revision'],
                  assessment_revision=entry['assessment_revision'],annotation_revision=1,
                  human_instruction='SYNTHETIC TEST: accept shown recommendation',human_reference='synthetic:reading_demo.py'))
        ds=record_decisions(rd,dict(decisions=decisions))
        result=apply_decisions(rd,root/'cache.json',decision_ids=[d['decision_id'] for d in ds['decisions']])
        if result['conflicts']: raise ValueError('Synthetic decisions conflicted')
        record_reading_completion(rd,human_instruction='SYNTHETIC TEST: whole book read',human_reference='synthetic:reading_demo.py')
        merge_snapshot(rd,normalize_snapshot(snapshot(),style_profile=profile))
        finalize_round(rd,root/'cache.json',output_dir=rd/'final',publication_context={})
    write_json(root/'project-index.json',dict(synthetic=True,round=str(rd.resolve()),report=str(report.resolve()),
                   account_validation=False,finalized=finalize))
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,default=REPO/'local/reading-projects/offline-demo')
    parser.add_argument('--finalize',action='store_true',help='Simulate explicit decisions then run actual export and official EPUBCheck')
    a=parser.parse_args()
    print(create_demo(a.output,finalize=a.finalize))
