"""Versioned WeRead proofreading CLI. Agent advice/approval enter as JSON, never inferred."""
import argparse
import json
import os
from pathlib import Path
import sys
from .artifact_io import write_json
from .reading_round import read,freeze_round,load_round
from .weread_client import fetch_snapshot,skill_version,gateway_request
from .weread_notes import normalize_snapshot,merge_snapshot,validate_profile
from .reading_match import match_issues,record_match_override
from .reading_review import export_assessment_tasks,import_assessments
from .reading_report import render_report
from .reading_decisions import record_decisions,apply_decisions,recover_transactions,undo_transaction
from .reading_finalization import finalization_status,record_reading_completion,finalize_round


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    sub=parser.add_subparsers(dest='command',required=True)
    arguments={
        'freeze':['cache','epub','source','storage-path','round','glossary','prompt'],
        'sync':['round','book-id','skill-dir','style-profile'],
        'import-notes':['round','snapshot','style-profile'],
        'match':['round'],'resolve':['round','file'],
        'tasks':['round','cache','out'],'assess':['round','results'],'report':['round'],
        'decide':['round','file'],'apply':['round','cache','decision-ids'],
        'recover':['round','cache'],'undo':['round','cache','transaction-id','instruction-file'],
        'status':['round','cache'],'close-reading':['round','instruction-file'],
        'finalize':['round','cache','publication-context','output'],
        'capture':['book-id','skill-dir','out'],'shelf':['skill-dir','out'],
    }
    for command,names in arguments.items():
        p=sub.add_parser(command)
        for name in names: p.add_argument('--'+name,required=True,**({'nargs':'+'} if name=='decision-ids' else {}))
        if command=='freeze': p.add_argument('--scope',help='Hash-bound evidence for an existing project reading-edition omission policy')
    a=parser.parse_args(argv); result=None
    try:
        cmd=a.command; rd=Path(a.round) if hasattr(a,'round') else None
        if cmd=='freeze':
            result=freeze_round(Path(a.cache),Path(a.epub),Path(a.source),storage_path=a.storage_path,round_dir=rd,
                                glossary_path=Path(a.glossary),prompt_path=Path(a.prompt),scope_path=Path(a.scope) if a.scope else None)
        elif cmd in ('sync','import-notes'):
            profile=read(a.style_profile); validate_profile(profile)
            if cmd=='sync':
                if profile.get('synthetic'): raise ValueError('Synthetic profile is only for offline import-notes')
                existing=load_round(rd)['book_id']
                if existing not in (None,a.book_id): raise ValueError('Round bound to another WeRead book')
                snapshot=fetch_snapshot(api_key=os.environ.get('WEREAD_API_KEY',''),book_id=a.book_id,
                                        skill_version=skill_version(a.skill_dir))
            else: snapshot=read(a.snapshot)
            result=merge_snapshot(rd,normalize_snapshot(snapshot,style_profile=profile))
        elif cmd=='match': result=match_issues(rd)
        elif cmd=='resolve': result=record_match_override(rd,read(a.file))
        elif cmd=='tasks':
            result=export_assessment_tasks(rd,Path(a.cache)); write_json(a.out,result)
        elif cmd=='assess': result=import_assessments(rd,read(a.results))
        elif cmd=='report': result=dict(report=str(render_report(rd).resolve()))
        elif cmd=='decide': result=record_decisions(rd,read(a.file))
        elif cmd=='apply': result=apply_decisions(rd,Path(a.cache),decision_ids=a.decision_ids)
        elif cmd=='recover': result=recover_transactions(rd,Path(a.cache))
        elif cmd=='undo':
            instruction=read(a.instruction_file)
            if not instruction.get('human_reference','').strip(): raise ValueError('Chat reference required for undo')
            result=undo_transaction(rd,Path(a.cache),transaction_id=a.transaction_id,
                    human_instruction=instruction['human_instruction']+'\n'+instruction['human_reference'])
        elif cmd=='status': result=finalization_status(rd,Path(a.cache))
        elif cmd=='close-reading':
            instruction=read(a.instruction_file)
            result=record_reading_completion(rd,human_instruction=instruction['human_instruction'],human_reference=instruction['human_reference'])
        elif cmd=='finalize': result=finalize_round(rd,Path(a.cache),output_dir=Path(a.output),publication_context=read(a.publication_context))
        elif cmd=='capture':
            result=fetch_snapshot(api_key=os.environ.get('WEREAD_API_KEY',''),book_id=a.book_id,skill_version=skill_version(a.skill_dir))
            write_json(a.out,result)
            result=dict(snapshot_id=result['snapshot_id'],saved_to=str(Path(a.out).resolve()),verified=False)
        elif cmd=='shelf':
            _,shelf=gateway_request('/shelf/sync',api_key=os.environ.get('WEREAD_API_KEY',''),skill_version=skill_version(a.skill_dir))
            write_json(a.out,shelf); result=dict(saved_to=str(Path(a.out).resolve()))
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 1 if cmd in ('apply','undo','recover') and result.get('conflicts') else 0
    except (ValueError,OSError,KeyError,TypeError) as exc:
        print(f'Proofreading error: {exc}',file=sys.stderr)
        return 2


if __name__=='__main__':
    raise SystemExit(main())
