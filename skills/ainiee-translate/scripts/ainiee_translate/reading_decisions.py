"""Explicit chat decisions, cache-lock CAS, durable apply/undo transactions."""
import copy
from pathlib import Path
from . import cache_io, batch
from .artifact_io import text_sha256,write_json
from .reading_round import (load_round,load_issues,round_lock,current_items,record,read,child,
                            revision,immutable,save_state,item_identity)


def _decision(round_dir,did):
    return read(child(round_dir,f'decisions/{did}.json'))['decisions'][0]


def record_decisions(round_dir,decisions):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir); idx={i['issue_id']:i for i in issues['issues']}
        pending=[]
        for supplied in decisions.get('decisions',[]):
            d=copy.deepcopy(supplied); iid=d.get('issue_id'); issue=idx.get(iid)
            if issue is None: raise ValueError('Use the full stable issue ID in structured decisions')
            if not d.get('human_instruction','').strip() or not d.get('human_reference','').strip():
                raise ValueError('Explicit human instruction and chat reference required')
            report=read(child(round_dir,f"reports/{d['report_revision']}.json"))
            shown=next((i for i in report['issues'] if i['issue_id']==iid),None)
            if (shown is None or report['edition_id']!=r['edition_id']
                    or d.get('annotation_revision')!=shown['annotation_revision']
                    or issue['annotation_revision']!=shown['annotation_revision']
                    or d.get('assessment_revision')!=shown['assessment_revision']
                    or issue.get('current_assessment_revision')!=shown['assessment_revision']
                    or issue['status'] in ('remote_deleted','out_of_scope','missing_unconfirmed','stale')):
                raise ValueError('Decision report/annotation/assessment is stale')
            action=d.get('action'); assessment=shown.get('assessment')
            if action not in ('accept','candidate','keep','defer','custom'): raise ValueError('Unknown decision action')
            expected=[]; selected_text=None
            if action not in ('keep','defer'):
                if not assessment: raise ValueError('Location and assessment required before modifying text')
                if action in ('accept','candidate'):
                    label=assessment['recommended_candidate'] if action=='accept' else d.get('candidate')
                    chosen=next((c for c in assessment['candidates'] if c['label']==label),None)
                    if chosen is None: raise ValueError('Requested candidate is absent in that report')
                    selected_text=chosen['text']; edits=chosen['edits']
                else:
                    selected_text=d.get('selected_text'); edits=d.get('edits',[])
                    if not isinstance(selected_text,str) or not selected_text.strip(): raise ValueError('Exact human final text required')
                parts={s['segment_id']:s for s in assessment['segments']}
                if (len(edits)!=len(parts) or {e.get('segment_id') for e in edits}!=set(parts)
                        or any(not isinstance(e.get('replacement_text'),str) or not e['replacement_text'].strip() for e in edits)
                        or selected_text!='\n'.join(e['replacement_text'] for e in edits)):
                    raise ValueError('Exact per-segment edits must equal displayed final text')
                for e in edits:
                    s=parts[e['segment_id']]
                    expected.append(dict(segment_id=s['segment_id'],text_index=s['text_index'],storage_path=s['storage_path'],
                         source_text=s['source_text'],source_text_sha256=s['source_text_sha256'],
                         before_text=s['current_target_text'],target_text_sha256=s['target_text_sha256'],
                         replacement_text=e['replacement_text'],item_identity=s['item_identity']))
            if 'selected_text' in supplied and supplied['selected_text']!=selected_text:
                raise ValueError('Selected text differs from the displayed candidate')
            did=d.get('decision_id') or revision()
            d.update(decision_id=did,selected_text=selected_text,expected_segments=expected)
            if child(round_dir,f'decisions/{did}.json').exists(): raise ValueError('Decision ID already exists')
            pending.append(d)
        if not pending: raise ValueError('No decisions')
        if len({d['decision_id'] for d in pending})!=len(pending): raise ValueError('Duplicate decision IDs')
        for d in pending:
            immutable(round_dir,'decisions',d['decision_id'],record('reading-decisions/1',r,decisions=[d]))
            issue=idx[d['issue_id']]
            previous=issue.get('active_decision_id')
            if previous:
                old=_decision(round_dir,previous)
                identical=(d['action'] in ('accept','candidate','custom') and old['action'] in ('accept','candidate','custom')
                           and old['selected_text']==d['selected_text'] and old['expected_segments']==d['expected_segments'])
                if not identical:
                    for old_id in issue.get('decision_ids',[]):
                        issue.setdefault('superseded_decisions',{})[old_id]=d['decision_id']
            issue.setdefault('decision_ids',[]).append(d['decision_id'])
            issue['active_decision_id']=d['decision_id']
            if d['action']=='keep':
                shown=next(i for i in read(child(round_dir,f"reports/{d['report_revision']}.json"))['issues'] if i['issue_id']==d['issue_id'])
                issue['kept_segments']=copy.deepcopy((shown.get('assessment') or {}).get('segments',[]))
                _resolve_conflicts(round_dir,issue,d['decision_id'])
            issue['status']={'keep':'kept','defer':'deferred'}.get(d['action'],'approved_pending_apply')
            issue['history'].append(dict(decision_id=d['decision_id'],action=d['action'],report_revision=d['report_revision']))
        r.pop('finalization',None); save_state(round_dir,r,issues)
        return record('reading-decisions/1',r,decisions=pending)


def _save_transaction(round_dir,transaction):
    # Materialized state is atomic; every transition is also append-only evidence.
    tid=transaction['transaction_id']
    immutable(round_dir,'transactions/events',tid+'-'+revision(),copy.deepcopy(transaction))
    write_json(child(round_dir,f'transactions/{tid}.json'),transaction)


def _resolve_conflicts(round_dir,issue,decision_id):
    for path in child(round_dir,'transactions').glob('*.json'):
        txn=read(path)
        if txn['state']=='conflict' and any(did in issue.get('decision_ids',[]) for did in txn['decision_ids']):
            issue.setdefault('resolved_transactions',{})[txn['transaction_id']]=decision_id


def _project_transaction(round_dir,r,issues,txn):
    idx={i['issue_id']:i for i in issues['issues']}
    outcomes={s.get('result') for s in txn['segments']}
    success=outcomes<= {'applied','noop'}
    pending=outcomes=={'not_applied'}
    for did in txn['decision_ids']:
        d=_decision(round_dir,did); issue=idx[d['issue_id']]
        current=(issue['annotation_revision']==d['annotation_revision']
                 and issue.get('current_assessment_revision')==d['assessment_revision']
                 and did not in issue.get('superseded_decisions',{})
                 and issue['status'] not in ('remote_deleted','out_of_scope','missing_unconfirmed','stale'))
        if current and txn['action']=='undo':
            issue['status']='needs_assessment' if success else 'conflict'
            if success: issue['current_assessment_revision']=None
        elif current:
            issue['status']='applied' if success else ('approved_pending_apply' if pending else 'conflict')
        issue.setdefault('decision_results',{})[did]=dict(transaction_id=txn['transaction_id'],
            result=('undone' if txn['action']=='undo' else 'applied') if success else ('pending' if pending else 'conflict'))
        issue['history'].append(dict(transaction_id=txn['transaction_id'],action=txn['action'],results=copy.deepcopy(txn['segments'])))
        if success and current:
            _resolve_conflicts(round_dir,issue,did)
    r.pop('finalization',None); save_state(round_dir,r,issues)


def _new_transaction(r,d,*,action='apply',original_transaction_id=None,human_instruction=None):
    segments=[]
    for s in d['expected_segments']:
        before=s['before_text']; after=s['replacement_text']
        segments.append(dict(segment_id=s['segment_id'],text_index=s['text_index'],storage_path=s['storage_path'],
                             source_text_sha256=s['source_text_sha256'],before_text=before,after_text=after,
                             before_sha256=text_sha256(before),after_sha256=text_sha256(after),
                             item_identity=s['item_identity'],result='prepared'))
    return record('reading-transaction/1',r,transaction_id=revision(),decision_ids=[d['decision_id']],action=action,
                  original_transaction_id=original_transaction_id,human_instruction=human_instruction,state='prepared',segments=segments)


def _write_transaction(round_dir,cache_path,txn):
    # An identical approved target is an idempotent no-op. CAS still runs inside
    # the public writer, against this observed version and the bound identity.
    _,current=current_items(round_dir,cache_path)
    expected={}
    for s in txn['segments']:
        it=current.get(s['text_index'])
        same=(it is not None and text_sha256(it.source_text)==s['source_text_sha256']
              and item_identity(it)==s['item_identity'] and text_sha256(it.translated_text)==s['after_sha256'])
        expected[s['text_index']]=s['after_sha256'] if same else s['before_sha256']
        s['idempotent']=same
    _save_transaction(round_dir,txn)
    items=[dict(text_index=s['text_index'],text=s['after_text']) for s in txn['segments']]
    # Public cache layer performs the comparison inside its own single lock.
    byindex={s['text_index']:s for s in txn['segments']}
    ordinary_check=batch.make_check(False)
    def check(it,text):
        if item_identity(it)!=byindex[it.text_index]['item_identity']: return ['stale_identity'],[]
        return ordinary_check(it,text)
    result=cache_io.apply_writeback(str(cache_path),items,2,lambda row:row['text'],check=check,
             expected_source_sha256={s['text_index']:s['source_text_sha256'] for s in txn['segments']},
             expected_target_sha256=expected)
    rejected={x['text_index']:x['reason'] for x in result.rejected}
    for s in txn['segments']:
        reason=rejected.get(s['text_index'])
        s['result']='rejected' if reason else ('noop' if s['idempotent'] else 'applied')
        if reason: s['reason']=reason
    txn['state']='cache_written'; _save_transaction(round_dir,txn)
    txn['state']='conflict' if rejected else 'committed'; _save_transaction(round_dir,txn)


def apply_decisions(round_dir,cache_path,*,decision_ids):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir); idx={i['issue_id']:i for i in issues['issues']}
        current_items(round_dir,cache_path)
        # An unresolved crash must be recovered, not submitted as another write.
        if any(read(p)['state'] in ('prepared','cache_written') for p in child(round_dir,'transactions').glob('*.json')):
            raise ValueError('Recover incomplete transactions before applying decisions')
        result=dict(applied=0,conflicts=0,transaction_ids=[],results=[])
        for did in dict.fromkeys(decision_ids):
            d=_decision(round_dir,did); i=idx.get(d['issue_id'])
            previous=(i or {}).get('decision_results',{}).get(did,{}).get('result')
            if previous in ('applied','undone'): continue
            if i and did in i.get('superseded_decisions',{}):
                result['conflicts']+=1; result['results'].append(dict(decision_id=did,result='superseded')); continue
            if d['action'] in ('keep','defer'): continue
            if (i is None or i['annotation_revision']!=d['annotation_revision']
                    or i.get('current_assessment_revision')!=d['assessment_revision']
                    or i['status'] in ('remote_deleted','missing_unconfirmed','out_of_scope','stale')):
                result['conflicts']+=1; result['results'].append(dict(decision_id=did,result='stale')); continue
            txn=_new_transaction(r,d); _write_transaction(round_dir,cache_path,txn)
            _project_transaction(round_dir,r,issues,txn)
            result['applied' if txn['state']=='committed' else 'conflicts']+=1
            result['transaction_ids'].append(txn['transaction_id'])
            result['results'].append(dict(decision_id=did,segments=copy.deepcopy(txn['segments'])))
        return result


def recover_transactions(round_dir,cache_path):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir); result=dict(recovered=0,conflicts=0)
        with cache_io.locked(str(cache_path)):
            _,idx=current_items(round_dir,cache_path)
            for path in sorted(child(round_dir,'transactions').glob('*.json')):
                txn=read(path)
                if txn['state'] in ('committed','conflict'):
                    # Crash after commit journal, before issue projection.
                    projected=all(any(any(h.get('transaction_id')==txn['transaction_id'] for h in i['history'])
                                      for i in issues['issues'] if i['issue_id']==_decision(round_dir,did)['issue_id']) for did in txn['decision_ids'])
                    if not projected: _project_transaction(round_dir,r,issues,txn); result['recovered']+=1
                    continue
                for s in txn['segments']:
                    it=idx.get(s['text_index'])
                    if it is None or item_identity(it)!=s['item_identity'] or text_sha256(it.source_text)!=s['source_text_sha256']:
                        s['result']='conflict'
                    elif text_sha256(it.translated_text)==s['after_sha256']:
                        s['result']='noop' if s.get('idempotent') or s['before_sha256']==s['after_sha256'] else 'applied'
                    elif text_sha256(it.translated_text)==s['before_sha256']:
                        s['result']='not_applied'
                    else: s['result']='conflict'
                outcomes={s['result'] for s in txn['segments']}
                txn['state']='committed' if outcomes<= {'applied','noop'} or outcomes=={'not_applied'} else 'conflict'
                _save_transaction(round_dir,txn); _project_transaction(round_dir,r,issues,txn)
                result['recovered']+=1; result['conflicts']+=txn['state']=='conflict'
        return result


def undo_transaction(round_dir,cache_path,*,transaction_id,human_instruction):
    if not isinstance(human_instruction,str) or not human_instruction.strip():
        raise ValueError('Explicit human undo instruction required')
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir); current_items(round_dir,cache_path)
        original=read(child(round_dir,f'transactions/{transaction_id}.json'))
        if original['action']!='apply' or not any(s['result'] in ('applied','noop') for s in original['segments']):
            raise ValueError('No applied changes to undo')
        for path in child(round_dir,'transactions').glob('*.json'):
            prior=read(path)
            if prior.get('original_transaction_id')==transaction_id and prior['state']=='committed':
                return dict(applied=0,conflicts=0,transaction_ids=[prior['transaction_id']])
        txn=record('reading-transaction/1',r,transaction_id=revision(),decision_ids=original['decision_ids'],
                   action='undo',state='prepared',original_transaction_id=transaction_id,human_instruction=human_instruction,segments=[])
        for s in original['segments']:
            if s['result']!='applied': continue
            txn['segments'].append(dict(segment_id=s['segment_id'],text_index=s['text_index'],storage_path=s['storage_path'],
                source_text_sha256=s['source_text_sha256'],before_text=s['after_text'],after_text=s['before_text'],
                before_sha256=s['after_sha256'],after_sha256=s['before_sha256'],item_identity=s['item_identity'],result='prepared'))
        if not txn['segments']: return dict(applied=0,conflicts=0,transaction_ids=[])
        _write_transaction(round_dir,cache_path,txn); _project_transaction(round_dir,r,issues,txn)
        return dict(applied=int(txn['state']=='committed'),conflicts=int(txn['state']=='conflict'),transaction_ids=[txn['transaction_id']])
