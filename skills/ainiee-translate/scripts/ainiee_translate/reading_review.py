"""Agent assessment task/result contracts; never generates translation advice."""
import copy
from pathlib import Path
from .artifact_io import text_sha256, sha256, digest
from .reading_round import (load_round, load_issues, load_segments, current_items, round_lock, read,
                            child, record, revision, immutable, save_state, item_identity)
from .weread_notes import new_issue


def export_assessment_tasks(round_dir, cache_path, *, issue_ids=None):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir)
        project,idx=current_items(round_dir,cache_path)
        ss=load_segments(round_dir); byid={s['segment_id']:s for s in ss}
        rows=[]
        for issue in issues['issues']:
            if issue_ids is not None and issue['issue_id'] not in issue_ids: continue
            selected=(issue.get('matching') or {}).get('selected')
            if not selected or issue['status'] in ('needs_link','remote_deleted','out_of_scope','missing_unconfirmed'): continue
            parts=[]; contexts=[]
            for selection in selected:
                s=byid[selection['segment_id']]; it=idx.get(s['text_index'])
                if it is None:
                    issue['status']='needs_location'; parts=[]; break
                pdf=it.extra.get('ainiee_pdf',{})
                if pdf.get('unit_id') and pdf.get('unit_id')!=s.get('unit_id'):
                    issue['status']='needs_location'; parts=[]; break
                if not s.get('unit_id') and s.get('item_identity')!=item_identity(it):
                    issue['status']='needs_location'; parts=[]; break
                if text_sha256(it.source_text)!=s['source_text_sha256']:
                    issue['status']='stale'
                part=dict(segment_id=s['segment_id'],text_index=s['text_index'],storage_path=s['storage_path'],
                          source_text=it.source_text,source_text_sha256=text_sha256(it.source_text),
                          frozen_source_text=s['source_text'],frozen_target_text=s['target_text'],
                          current_target_text=it.translated_text,target_text_sha256=text_sha256(it.translated_text),
                          selection=selection,unit_id=pdf.get('unit_id'),document_id=pdf.get('document_id',s.get('document_id')),
                          provenance=copy.deepcopy(pdf.get('provenance',pdf.get('source_refs',s.get('provenance')))),
                          item_identity=item_identity(it),is_pdf=bool(pdf))
                parts.append(part)
                position=ss.index(s)
                contexts.extend(dict(segment_id=n['segment_id'],source_text=n['source_text'],
                                     frozen_target_text=n['target_text'],current_target_text=idx[n['text_index']].translated_text if n['text_index'] in idx else None)
                                for n in ss[max(0,position-1):position+2])
            if not parts: continue
            rows.append(dict(issue_id=issue['issue_id'],annotation_revision=issue['annotation_revision'],
                             selected_reading_text=issue['note']['excerpt'],note=copy.deepcopy(issue['note']),
                             matching=copy.deepcopy(issue['matching']),segments=parts,context=contexts))
        manifest=read(child(round_dir,'edition/source-manifest.json'))
        tasks=record('reading-assessment-tasks/1',r,task_revision=revision(),issues=rows,
                     prompt_sha256=manifest['prompt_sha256'],glossary_sha256=manifest['glossary_sha256'],
                     prompt=child(round_dir,'edition/prompt.txt').read_text(encoding='utf8'),
                     glossary=read(child(round_dir,'edition/glossary.locked.json')),
                     cache_path=str(Path(cache_path).resolve()),source_path=manifest['source_path'],source_sha256=manifest['source_sha256'])
        immutable(round_dir,'tasks',tasks['task_revision'],tasks)
        save_state(round_dir,r,issues)
        return tasks


def _validate_candidates(row,task):
    parts={s['segment_id']:s for s in task['segments']}
    candidates=row.get('candidates',[])
    labels=[c.get('label') for c in candidates]
    if 'A' not in labels or len(labels)!=len(set(labels)) or not set(labels)<=set('ABC'):
        raise ValueError('Candidates require unique A/B/C labels and current-text A')
    for c in candidates:
        edits=c.get('edits',[])
        if len(edits)!=len(parts) or {e.get('segment_id') for e in edits}!=set(parts):
            raise ValueError('Candidate must replace every selected segment exactly once')
        if any(not isinstance(e.get('replacement_text'),str) or not e['replacement_text'].strip() for e in edits):
            raise ValueError('Empty candidate replacement')
        display='\n'.join(e['replacement_text'] for e in edits)
        if c.get('text')!=display: raise ValueError('Candidate display must equal its exact segment edits')
        if c['label']=='A' and any(e['replacement_text']!=parts[e['segment_id']]['current_target_text'] for e in edits):
            raise ValueError('Candidate A must retain the displayed current text')
        if c['label']=='B':
            proposal=row.get('user_proposal',{})
            thoughts=task['note'].get('thoughts',[])
            quoted=proposal.get('text')
            if not isinstance(quoted,str) or not quoted or not any(t['review_id']==proposal.get('review_id') and quoted in t['content'] for t in thoughts):
                raise ValueError('B requires an explicit quoted user proposal in an associated thought')
            if quoted!=c['text']:
                sid=proposal.get('segment_id'); s=parts.get(sid)
                start,end=proposal.get('start'),proposal.get('end')
                if (s is None or not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(s['current_target_text'])
                        or proposal.get('source_excerpt')!=s['current_target_text'][start:end]
                        or proposal['source_excerpt'] not in task['note']['excerpt']):
                    raise ValueError('Partial user proposal needs an exact current-text range in the reading excerpt')
                expected={k:v['current_target_text'] for k,v in parts.items()}
                expected[sid]=s['current_target_text'][:start]+quoted+s['current_target_text'][end:]
                if any(e['replacement_text']!=expected[e['segment_id']] for e in edits):
                    raise ValueError('B changes text beyond the explicit user proposal')
    recommended=next((c for c in candidates if c['label']==row.get('recommended_candidate')),None)
    if recommended is None or row.get('recommended_text')!=recommended['text']:
        raise ValueError('Recommendation must bind an exact displayed candidate')
    if not isinstance(row.get('rationale'),str) or not row['rationale'].strip() or not isinstance(row.get('uncertainties'),list):
        raise ValueError('Assessment rationale and uncertainties required')


def _validate_evidence(row,task,tasks):
    evidence=row.get('evidence')
    if not isinstance(evidence,list) or not evidence: raise ValueError('Source evidence required')
    pdfparts=[s for s in task['segments'] if s.get('is_pdf')]
    if not pdfparts:
        hrefs={s['selection'].get('href') for s in task['segments']}
        if any(not any(e.get('kind')=='epub' and e.get('href')==href and e.get('observations') for e in evidence) for href in hrefs):
            raise ValueError('Actual source XHTML evidence required')
        return
    path=Path(tasks['source_path'])
    if not path.is_file() or path.suffix.lower()!='.pdf' or sha256(path)!=tasks['source_sha256']:
        raise ValueError('Original PDF evidence missing or changed')
    for s in pdfparts:
        provenance=s.get('provenance') or []
        if isinstance(provenance,dict): provenance=[provenance]
        pages={p.get('physical_page',p.get('page')) for p in provenance}; pages.discard(None)
        if not pages or not any(e.get('kind')=='pdf' and e.get('pdf_sha256')==tasks['source_sha256']
                               and pages<=set(e.get('pages',[])) and e.get('observations') for e in evidence):
            raise ValueError('PDF assessment requires actual original-page observations and hash')


def import_assessments(round_dir,results):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir); byid={i['issue_id']:i for i in issues['issues']}
        tasks=read(child(round_dir,f"tasks/{results['task_revision']}.json"))
        taskrows={i['issue_id']:i for i in tasks['issues']}
        _,idx=current_items(round_dir,tasks['cache_path'])
        rows=results.get('issues',[]); seen=set()
        if not rows: raise ValueError('No assessment results')
        for row in rows:
            iid=row.get('issue_id'); issue=byid.get(iid); task=taskrows.get(iid)
            if iid in seen or issue is None or task is None: raise ValueError('Unknown/duplicate assessment issue')
            seen.add(iid)
            if (row.get('annotation_revision')!=issue['annotation_revision'] or row.get('annotation_revision')!=task['annotation_revision']
                    or row.get('segments')!=task['segments'] or issue.get('matching')!=task['matching']
                    or issue['status'] in ('needs_link','remote_deleted','out_of_scope','missing_unconfirmed')):
                raise ValueError('Stale assessment input')
            for s in task['segments']:
                it=idx.get(s['text_index'])
                if it is None or text_sha256(it.source_text)!=s['source_text_sha256'] or text_sha256(it.translated_text)!=s['target_text_sha256']:
                    raise ValueError('Stale assessment source/target')
            _validate_candidates(row,task); _validate_evidence(row,task,tasks)
        expanded=results.get('expanded_findings',[])
        segments={s['segment_id']:s for s in load_segments(round_dir)}
        for f in expanded:
            if f.get('origin_issue_id') not in byid or f.get('segment_id') not in segments or not f.get('problem_key') or not f.get('note'):
                raise ValueError('Expanded finding requires origin, known segment and problem evidence')
        assessment=record('reading-assessments/1',r,assessment_revision=revision(),task_revision=tasks['task_revision'],issues=copy.deepcopy(rows))
        immutable(round_dir,'assessments',assessment['assessment_revision'],assessment)
        for row in rows:
            issue=byid[row['issue_id']]
            if issue.get('current_assessment_revision'):
                issue['history'].append(dict(assessment_revision=issue['current_assessment_revision'],status=issue['status']))
            issue.update(current_assessment_revision=assessment['assessment_revision'],status='needs_approval')
        keys={i['external_key'] for i in issues['issues']}
        for f in expanded:
            key='expanded:'+digest([f['segment_id'],f['problem_key']])
            if key in keys: continue
            s=segments[f['segment_id']]
            issue=new_issue(r,external_key=key,note=dict(excerpt=s['target_text'],thoughts=[],needs_link=False,
                            expanded_observation=f['note']),origin_issue_id=f['origin_issue_id'])
            issue.update(status='needs_assessment',matching=dict(edition_id=r['edition_id'],annotation_revision=1,
                         candidates=[],selected=[dict(segment_id=s['segment_id'],start=0,end=len(s['target_text']),
                         href=s['locators'][0]['href'],block_index=s['locators'][0]['block_index'])]))
            issues['issues'].append(issue); keys.add(key)
        save_state(round_dir,r,issues)
        return assessment
