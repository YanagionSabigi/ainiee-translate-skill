"""Normalize verified styles, preserve unresolved links, merge immutable history."""
import copy
import json
from .artifact_io import digest
from .reading_round import (load_round, load_issues, round_lock, read, record, child,
                            immutable, save_state, revision, normalized)


def validate_profile(profile):
    if (profile.get('schema')!='weread-capabilities/1'
            or not (profile.get('verified') is True or profile.get('synthetic') is True)
            or 'blue_wave_style' not in profile or profile['blue_wave_style'] in (None,'unverified')
            or not profile.get('evidence_reference')):
        raise ValueError('A verified capability profile (or explicit synthetic fixture) is required')


def _same(a,b):
    # JSON true and 1 / numeric 17 and string "17" are distinct styles.
    return type(a) is type(b) and a==b


def normalize_snapshot(snapshot, *, style_profile):
    validate_profile(style_profile)
    if snapshot.get('schema')!='weread-snapshot/1' or not snapshot.get('snapshot_id') or not snapshot.get('book_id'):
        raise ValueError('Invalid snapshot identity')
    book=str(snapshot['book_id'])
    responses=snapshot['responses']; highlights=responses['highlights']
    if not isinstance(highlights.get('updated'),list): raise ValueError('Missing highlight records')
    notes=[]; other_keys=[]; ids=set(); all_marks=[]
    for mark in highlights['updated']:
        if str(mark.get('bookId',book))!=book: raise ValueError('Cross-book highlight')
        key=f"{book}:bookmark:{mark['bookmarkId']}"
        if key in ids: raise ValueError('Duplicate bookmark ID')
        ids.add(key)
        all_marks.append(dict(external_key=key,excerpt=mark.get('markText',''),chapter_uid=mark.get('chapterUid'),range=mark.get('range')))
        if not _same(mark.get('colorStyle'),style_profile['blue_wave_style']):
            other_keys.append(key); continue
        notes.append(dict(external_key=key,bookmark_id=mark['bookmarkId'],book_id=book,
                          excerpt=mark.get('markText',''),style=mark.get('colorStyle'),
                          chapter_uid=mark.get('chapterUid'),range=mark.get('range'),
                          thoughts=[],link_candidates=[],needs_link=False))
    unlinked=[]; review_ids=set()
    for page in responses['reviews']:
        for wrapped in page['reviews']:
            review=wrapped.get('review',wrapped)
            rid=review.get('reviewId')
            if rid is None or rid in review_ids: raise ValueError('Missing/duplicate personal review ID')
            review_ids.add(rid)
            if str(review.get('bookId',book))!=book: raise ValueError('Cross-book personal review')
            candidates=[]
            if review.get('abstract') and review.get('chapterUid') is not None:
                candidates=[n for n in all_marks if n['chapter_uid']==review['chapterUid']
                            and normalized(n['excerpt'])==normalized(review['abstract'])]
                if style_profile.get('range_link_verified') is True and review.get('range') is not None:
                    candidates=[n for n in candidates if n['range']==review['range']]
            thought=dict(review_id=rid,content=review.get('content',''),abstract=review.get('abstract'),
                         range=review.get('range'),chapter_uid=review.get('chapterUid'))
            blue={n['external_key']:n for n in notes}
            if len(candidates)==1 and candidates[0]['external_key'] in blue:
                blue[candidates[0]['external_key']]['thoughts'].append(thought)
            else:
                keys=[n['external_key'] for n in candidates]
                unlinked.append(dict(review=thought,candidate_external_keys=keys))
                for n in candidates:
                    if n['external_key'] in blue:
                        blue[n['external_key']]['needs_link']=True
                        blue[n['external_key']]['link_candidates'].append(thought)
    for note in notes:
        note['thoughts'].sort(key=lambda x:str(x['review_id']))
        note['link_candidates'].sort(key=lambda x:str(x['review_id']))
    complete=copy.deepcopy(snapshot.get('completeness',{}))
    complete['reviews_complete']=complete.get('reviews_complete') is True and bool(responses['reviews']) and responses['reviews'][-1].get('hasMore')==0
    complete['highlights_complete']=style_profile.get('highlights_snapshot_complete') is True and not highlights.get('hasMore',False)
    complete['deletion_semantics_verified']=style_profile.get('deletion_semantics_verified') is True
    return dict(snapshot=copy.deepcopy(snapshot),snapshot_id=snapshot['snapshot_id'],book_id=book,notes=notes,
                other_keys=other_keys,unlinked_reviews=unlinked,completeness=complete,style_profile=copy.deepcopy(style_profile))


def new_issue(r, *, external_key, note, origin_issue_id=None):
    n=r['next_issue_number']; r['next_issue_number']+=1
    issue=dict(issue_id=f"WR-{r['round_id']}-{n:06d}",external_key=external_key,annotation_revision=1,
               status='needs_link' if note.get('needs_link') else 'needs_location',note=note,matching=None,
               current_assessment_revision=None,history=[])
    if origin_issue_id: issue['origin_issue_id']=origin_issue_id
    return issue


def merge_snapshot(round_dir, normalized):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir)
        if r['book_id'] not in (None,normalized['book_id']): raise ValueError('Round bound to another WeRead book')
        profile=normalized['style_profile']; validate_profile(profile)
        if r['style_profile'] and not _same(r['style_profile']['blue_wave_style'],profile['blue_wave_style']):
            raise ValueError('Bound blue wave style cannot change during a round')
        sid=normalized['snapshot_id']
        snapshot=copy.deepcopy(normalized['snapshot'])
        snapshot.update(project_id=r['project_id'],round_id=r['round_id'],completeness=normalized['completeness'],
                        style_profile=profile,unlinked_reviews=normalized['unlinked_reviews'])
        snap_path=child(round_dir,f'snapshots/{sid}.json')
        if snap_path.exists():
            if read(snap_path)!=snapshot: raise ValueError('Snapshot ID reused with changed content')
            return issues
        immutable(round_dir,'snapshots',sid,snapshot)
        r.update(book_id=normalized['book_id'],style_profile=profile,latest_snapshot_id=sid)
        complete=all(normalized['completeness'].get(k) is True for k in ('reviews_complete','highlights_complete','deletion_semantics_verified'))
        if complete:
            r['last_complete_snapshot_id']=sid
            if r.get('reading_completion'): r['reading_completion']['snapshot_id']=sid
        existing={i['external_key']:i for i in issues['issues']}
        present=set()
        for note in normalized['notes']:
            key=note['external_key']; present.add(key)
            override=r.get('link_overrides',{}).get(key)
            if override and override['external_note_sha256']==digest(note):
                note=copy.deepcopy(override['resolved_note'])
            issue=existing.get(key)
            if issue is None:
                issues['issues'].append(new_issue(r,external_key=key,note=note)); continue
            if digest(issue['note'])!=digest(note):
                issue['history'].append(copy.deepcopy({k:v for k,v in issue.items() if k!='history'}))
                issue.update(note=note,annotation_revision=issue['annotation_revision']+1,
                             status='needs_link' if note['needs_link'] else 'stale',matching=None,current_assessment_revision=None)
            elif issue['status'] in ('missing_unconfirmed','remote_deleted','out_of_scope'):
                issue['status']='needs_link' if note['needs_link'] else 'needs_location'
        for issue in issues['issues']:
            if issue.get('origin_issue_id') or issue['external_key'] in present: continue
            if issue['external_key'] in normalized['other_keys']:
                status='out_of_scope'
            else:
                if not complete and issue['status']=='remote_deleted': continue
                status='remote_deleted' if complete else 'missing_unconfirmed'
            if issue['status']!=status:
                issue['history'].append(dict(status=issue['status'],snapshot_id=sid,annotation_revision=issue['annotation_revision']))
                issue['status']=status
        r.pop('finalization',None)
        save_state(round_dir,r,issues)
        return issues
