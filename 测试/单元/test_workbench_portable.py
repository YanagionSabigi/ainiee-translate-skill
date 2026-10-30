import json
import subprocess
import sys
import zipfile
from pathlib import Path

from test_workbench_glossary import setup_glossary, INSTRUCTION


def test_portable_review_is_slim_and_results_roundtrip(tmp_path):
    from ainiee_translate.workbench import main
    from ainiee_translate.workbench_bridge import runtime, load_project
    from ainiee_translate.workbench_glossary import apply_glossary
    locked, project, _ = setup_glossary(tmp_path)
    archive = tmp_path / 'for-review.zip'
    assert main(['export', str(project), '--out', str(archive)]) == 0
    recipient = tmp_path / 'recipient'
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        assert not any('/skill/' in '/'+n or n.endswith('SKILL.md') or n.startswith(('examples/', '.git/', 'wheels/')) for n in names)
        assert not any('katex' in n for n in names)
        assert 'baseline.json' in names and 'OPEN-ME.txt' in names
        assert archive.stat().st_size < 100_000
        z.extractall(recipient)
    # Reviewer has only the portable package, no AiNiee or Git installation.
    script = '''
from pathlib import Path
from review_workbench.storage import Store
from review_workbench.gitops import verify_baseline
from review_workbench.transfer import result_envelope
import json
store=Store(Path.cwd());verify_baseline(store.root,store.package)
d=store.state()['drafts'];key=store.package['items'][0]['id'];d['items'][key]={'mode':'accept'}
store.save(d,d['revision']);store.submit([key],store.state()['drafts']['revision'])
Path('returned.json').write_text(json.dumps(result_envelope(store)),encoding='utf-8')
'''
    import os
    env={**os.environ, 'PATH':str(Path(sys.executable).parent), 'PYTHONPATH':''}
    result=subprocess.run([sys.executable,'-c',script],cwd=recipient,env=env,capture_output=True)
    assert result.returncode == 0, result.stderr.decode(errors='replace')
    assert main(['import-results',str(project),'--from',str(recipient/'returned.json')]) == 0
    assert apply_glossary(project,locked,INSTRUCTION)['applied'] == 1
    assert json.loads(locked.read_text(encoding='utf-8'))['terms'][0]['dst'] == '氧气'
