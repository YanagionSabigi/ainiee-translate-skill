import json
import os
from pathlib import Path
import subprocess
import sys
sys.path.insert(0,str(Path(__file__).parents[1]/'单元'))
from test_reading_match import setup_round
from test_reading_review import result_for
from test_reading_decisions import prepare
from test_weread_notes import PROFILE,mark

def test_reading_cli_exit_codes(tmp_path):
    env={**os.environ,'PYTHONPATH':str(Path(__file__).parents[2]/'src')}
    help_run=subprocess.run([sys.executable,'-m','ainiee_translate.reading','--help'],capture_output=True,text=True,env=env)
    assert help_run.returncode==0 and 'import-notes' in help_run.stdout
    invalid=subprocess.run([sys.executable,'-m','ainiee_translate.reading','status','--round',str(tmp_path/'missing'),'--cache','absent'],capture_output=True,text=True,env=env)
    assert invalid.returncode==2 and 'Traceback' not in invalid.stderr

def test_reading_end_to_end_with_transport_and_real_export(tmp_path):
    from ainiee_translate.reading import main
    from ainiee_translate.weread_client import fetch_snapshot
    from ainiee_translate.reading_round import read,load_round,load_issues
    from ainiee_translate.artifact_io import write_json
    root,rd=setup_round(tmp_path,'一盏安静的灯照着窗户。')
    baseline=(rd/'edition/reading.epub').read_bytes()
    profile=root/'capabilities.json'; write_json(profile,PROFILE)
    def transport(body,headers):
        return {'updated':[mark()]} if body['api_name']=='/book/bookmarklist' else {'reviews':[],'hasMore':0}
    snapshot=fetch_snapshot(api_key='fake',book_id='b',skill_version='synthetic',transport=transport)
    write_json(root/'snapshot.json',snapshot)
    common=['--round',str(rd)]
    assert main(['import-notes',*common,'--snapshot',str(root/'snapshot.json'),'--style-profile',str(profile)])==0
    assert main(['match',*common])==0
    assert main(['tasks',*common,'--cache',str(root/'cache.json'),'--out',str(root/'tasks.json')])==0
    tasks=read(root/'tasks.json'); write_json(root/'assessment.json',result_for(tasks))
    assert main(['assess',*common,'--results',str(root/'assessment.json')])==0
    assert main(['report',*common])==0
    d=prepare(root,rd); write_json(root/'decision.json',d)
    assert main(['decide',*common,'--file',str(root/'decision.json')])==0
    did=next((rd/'decisions').glob('*.json')).stem
    assert main(['apply',*common,'--cache',str(root/'cache.json'),'--decision-ids',did])==0
    assert main(['import-notes',*common,'--snapshot',str(root/'snapshot.json'),'--style-profile',str(profile)])==0
    assert len(load_issues(rd)['issues'])==1
    assert (rd/'edition/reading.epub').read_bytes()==baseline
    assert main(['finalize',*common,'--cache',str(root/'cache.json'),'--publication-context',str(profile),'--output',str(rd/'final')])==2
    assert not (rd/'final').exists()
