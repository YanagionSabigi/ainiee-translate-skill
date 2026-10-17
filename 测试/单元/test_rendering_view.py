from pathlib import Path
import pytest


def test_template_direct_call_requires_formal_binding(tmp_path):
    from ainiee_translate.book_pdf import export_template_sources
    with pytest.raises(ValueError, match='manifest|binding'):
        export_template_sources({'schema':'epub-book/2'},tmp_path,engine='latex',settings={})


def test_markdown_direct_call_requires_formal_binding(tmp_path):
    from ainiee_translate.book_markdown import export_markdown
    with pytest.raises(ValueError, match='manifest|binding'):
        export_markdown({'schema':'epub-book/2'},tmp_path)


def test_old_render_model_cannot_be_published(tmp_path):
    from ainiee_translate.book_pdf import export_template_sources
    with pytest.raises(ValueError,match='epub-book/2|binding'):
        export_template_sources({'schema':'ainiee-book/1'},tmp_path,engine='latex',settings={})
