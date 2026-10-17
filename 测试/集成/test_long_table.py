import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '夹具'))
from long_table import add_long_table
from v2_sample import make_bound
from ainiee_translate.book_pdf import export_template_sources


@pytest.mark.parametrize('engine', ['latex', 'typst'])
@pytest.mark.parametrize('header_kind', ['plain', 'note', 'reference'])
def test_table_continuation_does_not_duplicate_semantic_anchors(tmp_path, engine, header_kind):
    _, target, _, manifest, _ = make_bound(tmp_path / 'work', lambda b: add_long_table(b, header_kind, row_count=3))
    source = export_template_sources(target, tmp_path / engine, engine=engine, settings={},
                                     manifest=manifest, work=tmp_path / 'work').read_text(encoding='utf8')
    assert source.count('Part 003') == 1
    if engine == 'latex':
        assert '\\begin{longtable}' in source
        if header_kind == 'plain':
            assert source.count('Part & Count') == 2
        else:
            ident = 'table-header-note' if header_kind == 'note' else 'table-header-ref'
            assert source.count('label{' + ident + '}') == 1
            continuation = source.split('\\endfirsthead', 1)[1].split('\\endhead', 1)[0]
            assert ident not in continuation
    else:
        assert 'table.header(repeat: ' + str(header_kind == 'plain').lower() in source
        if header_kind != 'plain':
            ident = 'table-header-note' if header_kind == 'note' else 'table-header-ref'
            assert source.count('<' + ident + '>') >= 1
            assert source.count('#metadata(none) <' + ident + '>') == 1
