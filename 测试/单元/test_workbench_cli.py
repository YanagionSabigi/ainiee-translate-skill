def test_cli_help_and_glossary_creation(tmp_path, capsys):
    from ainiee_translate.workbench import main
    from ainiee_translate.artifact_io import write_json
    from ainiee_translate.workbench_bridge import load_project
    locked = tmp_path / 'locked.json'
    write_json(locked, dict(terms=[dict(src='oxygen', dst='氧气')]))
    assert main(['glossary', '--locked', str(locked), '--out', str(tmp_path / 'review')]) == 0
    assert len(load_project(tmp_path / 'review')[0].package['items']) == 1
    assert main(['compare', str(tmp_path / 'review')]) == 0
