import importlib.util
from pathlib import Path
import subprocess
import zipfile

import pytest


def release_builder():
    spec=importlib.util.spec_from_file_location('release_build',Path(__file__).resolve().parents[2]/'build_release.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_release_is_reproducible_and_excludes_untracked_private_files(tmp_path):
    subprocess.run(['git','init','--quiet',str(tmp_path)],check=True)
    skill=tmp_path/'skills/ainiee-translate';skill.mkdir(parents=True)
    (skill/'SKILL.md').write_text('---\nname: ainiee-translate\n---\n')
    (skill/'LICENSE').write_text('test license')
    subprocess.run(['git','add','skills'],cwd=tmp_path,check=True)
    (skill/'.env').write_text('PRIVATE_CONFIGURATION=not-a-real-secret')
    (skill/'runtime.log').write_text('Private local runtime')
    builder=release_builder()
    builder.skill_zip(tmp_path,tmp_path/'first.zip')
    (skill/'SKILL.md').touch()
    builder.skill_zip(tmp_path,tmp_path/'second.zip')
    assert (tmp_path/'first.zip').read_bytes()==(tmp_path/'second.zip').read_bytes()
    with zipfile.ZipFile(tmp_path/'first.zip') as archive:
        assert set(archive.namelist())=={'ainiee-translate/SKILL.md','ainiee-translate/LICENSE'}


def test_release_rejects_tracked_private_configuration(tmp_path):
    subprocess.run(['git','init','--quiet',str(tmp_path)],check=True)
    skill=tmp_path/'skills/ainiee-translate';skill.mkdir(parents=True)
    (skill/'.env').write_text('PRIVATE_CONFIGURATION=not-a-real-secret')
    subprocess.run(['git','add','--force','skills'],cwd=tmp_path,check=True)
    with pytest.raises(ValueError,match='Runtime, hidden or unsafe'):
        release_builder().skill_zip(tmp_path,tmp_path/'release.zip')
