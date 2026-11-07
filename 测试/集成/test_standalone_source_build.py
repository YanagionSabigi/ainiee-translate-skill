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


def test_bundle_remains_publisher_source_with_older_sibling_and_includes_examples(tmp_path):
    spec = importlib.util.spec_from_file_location('skill_build', Path(__file__).resolve().parents[2] / 'build.py')
    build = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(build)
    repo = tmp_path / 'ainiee'
    publisher = repo / 'skills/ainiee-translate/scripts/ainiee_translate/publication_skill'
    sibling = tmp_path / 'pdf-to-epub-skill'
    for root, marker in [(publisher, 'current'), (sibling, 'old')]:
        (root / 'scripts').mkdir(parents=True)
        (root / 'scripts/translation_contract.py').write_text(marker)
        (root / 'SKILL.md').write_text(marker)
    example = repo / 'src/ainiee_translate/assets/template/epub/reference-book/reference.epub'
    example.parent.mkdir(parents=True)
    example.write_bytes(b'example')
    selected = build.publication_files(repo)
    assert selected[Path('SKILL.md')].read_text() == 'current'
    assert example.read_bytes() == b'example'
    assert Path('examples/reference-book/reference.epub') not in selected


def test_development_bridge_prefers_bundled_publisher_over_old_sibling(tmp_path, monkeypatch):
    from ainiee_translate import pdf_bridge
    repo = tmp_path / 'ainiee'
    module = repo / 'src/ainiee_translate/pdf_bridge.py'
    module.parent.mkdir(parents=True)
    module.touch()
    bundled = repo / 'skills/ainiee-translate/scripts/ainiee_translate/publication_skill'
    sibling = tmp_path / 'pdf-to-epub-skill'
    for root in (bundled, sibling):
        (root / 'scripts').mkdir(parents=True)
        (root / 'scripts/pdf_to_epub.py').touch()
    monkeypatch.delenv('AINIEE_PDF_TO_EPUB', raising=False)
    monkeypatch.setattr(pdf_bridge, '__file__', str(module))
    assert pdf_bridge.skill_root() == bundled.resolve()
