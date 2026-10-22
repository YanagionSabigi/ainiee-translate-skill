"""Whole-book delivery gate; intermediate builds remain in private checks/."""
import copy
from pathlib import Path
import shutil
from . import cache_io
from .artifact_io import sha256,text_sha256,write_json,digest
from .book_check import check_epub
from .export import export_project
from .reading_round import (load_round,load_issues,load_segments,round_lock,current_items,read,child,
                            record,revision,now,save_state)

TERMINAL={'applied','kept','remote_deleted','out_of_scope'}


def _status(round_dir,cache_path):
    r=load_round(round_dir); issues=load_issues(round_dir); project,idx=current_items(round_dir,cache_path)
    segments={s['segment_id']:s for s in load_segments(round_dir)}
    blockers=[]; changed=[]; state_changed=False
    for issue in issues['issues']:
        for selection in (issue.get('matching') or {}).get('selected') or []:
            s=segments.get(selection['segment_id']); it=idx.get(s['text_index']) if s else None
            status=None
            if it is None: status='needs_location'
            elif s.get('unit_id') and it.extra.get('ainiee_pdf',{}).get('unit_id')!=s['unit_id']: status='needs_location'
            elif text_sha256(it.source_text)!=s['source_text_sha256']:
                # A reviewed new assessment can bind a reconciled source. The frozen edition stays unchanged.
                arev=issue.get('current_assessment_revision')
                assessed=None
                if arev:
                    a=read(child(round_dir,f'assessments/{arev}.json'))
                    assessed=next((p for row in a['issues'] if row['issue_id']==issue['issue_id']
                                   for p in row['segments'] if p['segment_id']==s['segment_id']),None)
                if not assessed or assessed['source_text_sha256']!=text_sha256(it.source_text): status='stale'
            if it is not None and issue['status'] in ('applied','kept'):
                bound=[]
                if issue['status']=='applied':
                    did=issue.get('active_decision_id')
                    if did:
                        d=read(child(round_dir,f'decisions/{did}.json'))['decisions'][0]
                        bound=[(p['segment_id'],text_sha256(p['replacement_text'])) for p in d['expected_segments']]
                else:
                    bound=[(p['segment_id'],p['target_text_sha256']) for p in issue.get('kept_segments',[])]
                if any(sid==s['segment_id'] and expected!=text_sha256(it.translated_text) for sid,expected in bound): status='stale'
            if status and issue['status'] not in ('remote_deleted','out_of_scope'):
                if issue['status']!=status or issue.get('current_assessment_revision'):
                    issue['history'].append(dict(status=issue['status'],reason='source_or_identity_changed'))
                    issue.update(status=status,current_assessment_revision=None); state_changed=True
        if issue['status'] not in TERMINAL: blockers.append(issue['issue_id']+':'+issue['status'])
        if issue['status']=='remote_deleted':
            if not r.get('last_complete_snapshot_id'): blockers.append(issue['issue_id']+':deletion_unverified')
    for path in child(round_dir,'transactions').glob('*.json'):
        txn=read(path)
        resolved=any(txn['transaction_id'] in i.get('resolved_transactions',{}) for i in issues['issues'])
        if txn['state']!='committed' and not resolved: blockers.append('transaction:'+txn['transaction_id']+':'+txn['state'])
        elif txn['state']=='committed' and not any(h.get('transaction_id')==txn['transaction_id'] for i in issues['issues'] for h in i['history']):
            blockers.append('transaction:'+txn['transaction_id']+':unprojected')
    for it in idx.values():
        pdf=it.extra.get('ainiee_pdf')
        if not pdf: continue
        from .pdf_bridge import contract
        proof=pdf.get('proofreading',{})
        if (proof.get('status')!='passed' or proof.get('independent') is not True
                or proof.get('target_sha256')!=contract().content_digest(it.source_text if pdf.get('translation_policy')=='preserve_source' else it.translated_text)):
            changed.append(pdf.get('unit_id')); blockers.append('pdf_target_proof:'+str(pdf.get('unit_id')))
    completion=r.get('reading_completion')
    if not completion or not completion.get('human_instruction','').strip() or not completion.get('human_reference','').strip():
        blockers.append('human_reading_completion_required')
    if (not completion or not completion.get('snapshot_id') or completion['snapshot_id']!=r.get('latest_snapshot_id')
            or completion['snapshot_id']!=r.get('last_complete_snapshot_id')):
        blockers.append('final_complete_sync_required')
    if state_changed: save_state(round_dir,r,issues)
    return dict(blockers=list(dict.fromkeys(blockers)),changed_pdf_unit_ids=changed,
                round_revision=r['revision'],issues_revision=digest(issues),cache_sha256=sha256(cache_path))


def finalization_status(round_dir,cache_path):
    with round_lock(round_dir):
        with cache_io.locked(str(cache_path)):
            return _status(round_dir,cache_path)


def record_reading_completion(round_dir,*,human_instruction,human_reference):
    if not human_instruction.strip() or not human_reference.strip():
        raise ValueError('Explicit whole-book completion instruction and chat reference required')
    with round_lock(round_dir):
        r=load_round(round_dir)
        r['reading_completion']=dict(human_instruction=human_instruction,human_reference=human_reference,
                                    confirmed_at=now(),snapshot_id=None)
        r.pop('finalization',None); save_state(round_dir,r)
        return r


def finalize_round(round_dir,cache_path,*,output_dir,publication_context):
    round_dir=Path(round_dir); cache_path=Path(cache_path); output_dir=Path(output_dir)
    if not output_dir.resolve().is_relative_to(round_dir.resolve()) or output_dir.resolve().is_relative_to((round_dir/'edition').resolve()):
        raise ValueError('Final output must remain in round, outside immutable edition')
    if output_dir.exists(): raise FileExistsError('Final output exists; preserve the prior delivery')
    with round_lock(round_dir):
        with cache_io.locked(str(cache_path)):
            initial=_status(round_dir,cache_path)
            if initial['blockers']: raise ValueError('Final delivery blocked: '+', '.join(initial['blockers']))
            r=load_round(round_dir); project,idx=current_items(round_dir,cache_path)
            storage=r['storage_path']; project.files={storage:project.files[storage]}
            stage=child(round_dir,'checks/build-'+revision()); stage.mkdir(parents=True)
            shutil.copyfile(cache_path,stage/'cache.snapshot.json')
    manifest=read(child(round_dir,'edition/source-manifest.json'))
    context=copy.deepcopy(publication_context)
    book_settings=context.pop('book_settings',None)
    pdf_engines=context.pop('pdf_engines',None)
    context['cache_path']=str(stage/'cache.snapshot.json')
    cf=project.files[storage]; is_pdf=bool(cf.extra.get('ainiee_pdf'))
    requested=context.pop('formats',None)
    formats=['epub'] if is_pdf else ['source']
    if requested:
        # A PDF template is only built if it was part of the original project request.
        if not is_pdf or any(f not in ('epub','pdf','latex','typst') for f in requested):
            raise ValueError('Template output requires a structured PDF project and explicit formats')
        formats=list(dict.fromkeys(['epub']+requested))
    if is_pdf:
        for name in ('glossary_path','prompt_path','review_path'):
            if not context.get(name): raise ValueError('PDF publication context missing '+name)
        input_path=str(Path(manifest['source_path']).parent)
    else:
        original=child(round_dir,'edition/'+manifest['frozen_source'])
        input_root=stage/'input'; target=input_root/storage; target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(original,target); input_path=str(input_root)
    export_project(project,str(stage/'export'),input_path,formats=formats,cache_root=cache_path.resolve().parent,
                   publication_context=context,book_settings=book_settings,pdf_engines=pdf_engines)
    epubs=[p for p in (stage/'export').rglob('*.epub') if not any(part.startswith('bilingual_') for part in p.relative_to(stage/'export').parts)]
    if len(epubs)!=1: raise ValueError('Expected exactly one final translated EPUB')
    checks=check_epub(epubs[0]); write_json(stage/'checks.json',checks)
    if any(checks.get(name,{}).get('status')!='passed' for name in ('structure','epubcheck')):
        raise ValueError('Final EPUB structure and official EPUBCheck must both pass; inspect private checks')
    deliver=stage/'delivery'; deliver.mkdir()
    shutil.copyfile(epubs[0],deliver/'book.epub')
    pdfs=list((stage/'export').rglob('*.pdf'))
    if 'pdf' in formats:
        engines=pdf_engines or ['latex','typst']
        for engine in engines:
            matches=[p for p in pdfs if p.parent.name==engine]
            if len(matches)!=1: raise ValueError('Missing newly compiled template PDF: '+engine)
            shutil.copyfile(matches[0],deliver/(engine+'.pdf'))
    with round_lock(round_dir):
        with cache_io.locked(str(cache_path)):
            current=_status(round_dir,cache_path)
            if current!=initial: raise ValueError('Round, issues or cache changed during finalization; delivery blocked')
            r=load_round(round_dir)
            result=record('reading-finalization/1',r,status='passed',validation_mode='synthetic' if (r.get('style_profile') or {}).get('synthetic') else 'account',checks=checks,cache_sha256=initial['cache_sha256'],
                          snapshot_id=r['last_complete_snapshot_id'],files={p.name:sha256(p) for p in deliver.iterdir()})
            write_json(deliver/'finalization.json',result)
            output_dir.parent.mkdir(parents=True,exist_ok=True)
            if output_dir.exists(): raise FileExistsError(output_dir)
            deliver.rename(output_dir)
            r['finalization']=dict(output_dir=str(output_dir.resolve()),**result); save_state(round_dir,r)
            return result
