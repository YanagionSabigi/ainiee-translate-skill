import json
from pathlib import Path
import pytest

from ainiee_translate import parse, export
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheProject import CacheProject
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheFile import CacheFile


def test_babeldoc_removed_before_any_external_fallback(tmp_path, monkeypatch):
    pdf = tmp_path / '原书 空格.pdf'
    pdf.write_bytes(b'%PDF-1.7')
    monkeypatch.setenv('AINIEE_REPO', str(tmp_path))
    with pytest.raises(ValueError, match='backend'):
        parse.parse_input(str(pdf), pdf_backend='babeldoc')


@pytest.mark.parametrize('kind', ['Pdf', 'Office', 'AutoType'])
def test_legacy_pdf_never_uses_external_writer(tmp_path, monkeypatch, kind):
    monkeypatch.setenv('AINIEE_REPO', str(tmp_path))
    cf = CacheFile(storage_path='旧书.PDF', file_project_type=kind)
    project = CacheProject(files={'旧书.PDF': cf})
    with pytest.raises(ValueError, match='new project|新项目'):
        export.export_project(project, str(tmp_path / 'out'), str(tmp_path))


def test_bridge_uses_selected_cli_and_preserves_argv(tmp_path):
    from ainiee_translate.pdf_bridge import skill_root, run_cli
    assert (skill_root() / 'scripts/pdf_to_epub.py').is_file()
    output = tmp_path / '路径 空格' / 'probe.json'
    output.parent.mkdir()
    result = run_cli('probe', '--output', output)
    assert result.returncode == 0
    assert json.loads(output.read_text(encoding='utf8'))
