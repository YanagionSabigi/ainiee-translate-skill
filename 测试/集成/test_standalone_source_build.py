import importlib.util
from pathlib import Path


def test_fork_can_build_without_a_sibling_publisher_checkout(tmp_path):
    spec = importlib.util.spec_from_file_location('skill_build', Path(__file__).resolve().parents[2] / 'build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    repo = tmp_path / 'standalone-fork'
    source = repo / 'src/ainiee_translate'
    bundle = repo / 'skills/ainiee-translate/scripts/ainiee_translate'
    publisher = bundle / 'publication_skill'
    source.mkdir(parents=True)
    (publisher / 'scripts').mkdir(parents=True)
    (source / '__init__.py').write_text('VERSION = "test"\n')
    (publisher / 'SKILL.md').write_text('Publisher\n')
    (publisher / 'scripts/translation_contract.py').write_text('SCHEMA = "epub-book/2"\n')
    build.build(repo)
    build.build(repo, check=True)
    assert (bundle / '__init__.py').read_bytes() == (source / '__init__.py').read_bytes()
    assert (publisher / 'scripts/translation_contract.py').is_file()
