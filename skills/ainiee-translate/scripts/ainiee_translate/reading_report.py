"""Offline HTML plus immutable machine-readable record of exactly what was shown."""
import copy
from difflib import SequenceMatcher
import html
import json
from pathlib import Path
from string import Template
from .reading_round import (load_round,load_issues,load_segments,round_lock,read,child,record,revision,immutable,save_state)

STATES=dict(needs_link='待关联',needs_location='待定位',needs_assessment='待辨析',needs_approval='待批准',
            deferred='搁置',approved_pending_apply='待执行',applied='已应用',kept='保留现译',remote_deleted='远端已删除',
            missing_unconfirmed='缺失待确认',stale='过期',conflict='冲突',out_of_scope='已改为其他颜色')


def esc(value):
    return html.escape(str(value if value is not None else ''))


def formatted(value):
    # Only canonical emphasis marks are generated as markup; all other content is data.
    out=esc(value)
    for tag in ('i','b'):
        out=out.replace(f'&lt;{tag}&gt;',f'<{tag}>').replace(f'&lt;/{tag}&gt;',f'</{tag}>')
    return out


def diff(before,after):
    result=[]
    for kind,a,b,c,d in SequenceMatcher(None,before,after,autojunk=False).get_opcodes():
        if kind=='equal': result.append(esc(before[a:b]))
        else:
            if a!=b: result.append('<del>'+esc(before[a:b])+'</del>')
            if c!=d: result.append('<ins>'+esc(after[c:d])+'</ins>')
    return ''.join(result)


def long_text(value,*,title,focus=0):
    if len(value)<=180: return '<p>'+formatted(value)+'</p>'
    left=max(0,focus-55); right=min(len(value),max(focus+110,left+165))
    preview=('…' if left else '')+value[left:right]+('…' if right<len(value) else '')
    return '<p>'+formatted(preview)+'</p><details><summary>'+esc(title)+'</summary><p>'+formatted(value)+'</p></details>'


def render_report(round_dir, *, output_path=None):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir); ss={s['segment_id']:s for s in load_segments(round_dir)}
        rev=revision(); rows=[]; shown=[]
        snapshot=read(child(round_dir,f"snapshots/{r['latest_snapshot_id']}.json")) if r.get('latest_snapshot_id') else {}
        book_title=snapshot.get('responses',{}).get('highlights',{}).get('book',{}).get('title') or r['storage_path']
        for issue in issues['issues']:
            assessment=None; context=[]
            arev=issue.get('current_assessment_revision')
            if arev:
                assessments=read(child(round_dir,f'assessments/{arev}.json'))
                assessment=next(a for a in assessments['issues'] if a['issue_id']==issue['issue_id'])
                tasks=read(child(round_dir,f"tasks/{assessments['task_revision']}.json"))
                context=next(t.get('context',[]) for t in tasks['issues'] if t['issue_id']==issue['issue_id'])
            entry=copy.deepcopy(issue); entry['assessment']=copy.deepcopy(assessment)
            entry['assessment_revision']=arev; shown.append(entry)
            selected=(issue.get('matching') or {}).get('selected') or []
            parts=assessment['segments'] if assessment else [ss[s['segment_id']] for s in selected]
            source='\n'.join(s['source_text'] for s in parts)
            current='\n'.join(s.get('current_target_text',s.get('target_text','')) for s in parts)
            focus=max(0,current.find(issue['note']['excerpt']))
            location='\n'.join(s.get('href','') for s in selected)
            pdf_evidence=[e for e in (assessment or {}).get('evidence',[]) if e.get('kind')=='pdf']
            if pdf_evidence:
                location='原 PDF 物理页 '+', '.join(str(p) for p in sorted({p for e in pdf_evidence for p in e.get('pages',[])}))
                printed={str(k):v for e in pdf_evidence for k,v in e.get('printed_pages',{}).items()}
                if printed: location+='；印刷页 '+', '.join(str(v) for v in printed.values())
            context_html=''.join('<p><b>原文</b> '+formatted(n['source_text'])+'</p><p><b>现译</b> '+formatted(n.get('current_target_text',n.get('frozen_target_text','')))+'</p>' for n in context)
            thoughts='\n\n'.join(t['content'] for t in issue['note'].get('thoughts',[])) or '请核查此处（未附想法）'
            if issue['note'].get('link_candidates'):
                thoughts+='\n\n待关联想法：\n'+'\n'.join(t['content'] for t in issue['note']['link_candidates'])
            variants=[]
            for label in 'ABC':
                c=next((c for c in (assessment or {}).get('candidates',[]) if c['label']==label),None)
                changed=next((a for kind,a,b,x,y in SequenceMatcher(None,current,c['text'],autojunk=False).get_opcodes() if kind!='equal'),focus) if c else focus
                variants.append(f'<div class="variant"><b>{label}：</b>'+long_text(c['text'],title='完整候选 '+label,focus=changed)+'</div>' if c else f'<div class="variant">{label}：未提供</div>')
            if assessment:
                variants.append('<div class="recommendation"><b>推荐定稿 '+esc(assessment['recommended_candidate'])+'</b><p>'+formatted(assessment['recommended_text'])+'</p></div>')
                variants.append('<details'+(' open' if len(current)<=180 else '')+'><summary>精确差异（整段）</summary><p>'+diff(current,assessment['recommended_text'])+'</p></details>')
            rationale=esc((assessment or {}).get('rationale','尚未辨析'))
            uncertainties='\n'.join((assessment or {}).get('uncertainties',[])) or '未另列不确定项'
            evidence=json.dumps((assessment or {}).get('evidence',[]),ensure_ascii=False,indent=2)
            audit=json.dumps(entry,ensure_ascii=False,indent=2)
            iid=issue['issue_id']; short=int(iid.rsplit('-',1)[1])
            rows.append(f'<tr id="{esc(iid)}" data-status="{esc(issue["status"])}"><td><a href="#{esc(iid)}" class="short">{short}</a><div class="full">{esc(iid)}</div><span class="status">{esc(STATES[issue["status"]])}</span></td>'
                        f'<td><p>{esc(location)}</p><details'+(' open' if len(source)<=350 else '')+f'><summary>完整原文与位置</summary><p>{formatted(source)}</p></details><details><summary>前后文</summary>{context_html}</details></td>'
                        f'<td><b>阅读选区</b>'+long_text(issue['note']['excerpt'],title='完整阅读选区')+'<b>当前工作译文（评估时）</b>'+long_text(current,title='完整当前工作译文',focus=focus)+'</td>'
                        f'<td><p>{esc(thoughts)}</p></td><td>{"".join(variants)}</td><td><p>{rationale}</p><p>{esc(uncertainties)}</p><details><summary>原文证据</summary><pre>{esc(evidence)}</pre></details><details><summary>版本与审计</summary><pre>{esc(audit)}</pre></details></td></tr>')
        report=record('reading-report/1',r,report_revision=rev,edition_id=r['edition_id'],round_revision=r['revision'],issues=shown)
        template=Template(Path(__file__).with_suffix('.html').read_text(encoding='utf8'))
        unlinked=[]
        unlinked=snapshot.get('unlinked_reviews',[])
        audit_html=('<details><summary>未关联笔记审计（'+str(len(unlinked))+'；不作为修改授权）</summary>'+''.join('<p>'+esc(x['review'].get('abstract',''))+'<br>'+esc(x['review'].get('content',''))+'</p>' for x in unlinked)+'</details>') if unlinked else ''
        rendered=template.substitute(book_title=esc(book_title),round_id=esc(r['round_id']),report_revision=esc(rev),created_at=esc(report['created_at']),
                                     css=(Path(__file__).parent/'assets/reading_report.css').read_text(encoding='utf8'),rows=''.join(rows),sync_audit=audit_html)
        path=child(round_dir,f'reports/{rev}.html')
        if output_path is not None:
            target=Path(output_path).resolve(); root=Path(round_dir).resolve()
            if not target.is_relative_to(root): raise ValueError('Report output must stay inside round')
            path=child(round_dir,target.relative_to(root).as_posix())
        if path.exists(): raise FileExistsError(path)
        immutable(round_dir,'reports',rev,report)
        path.parent.mkdir(parents=True,exist_ok=True)
        with path.open('x',encoding='utf8') as stream: stream.write(rendered)
        r['latest_report_revision']=rev; save_state(round_dir,r)
        return path
