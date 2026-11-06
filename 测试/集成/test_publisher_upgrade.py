from ainiee_translate.pdf_bridge import publisher_module


def test_translated_figure_crossref_anchors_without_english_or_chinese_labels():
    figure = {'id':'fig', 'kind':'figure', 'inline':[{'text':'Illustration 1'}]}
    body = {'id':'p', 'kind':'paragraph', 'inline':[{'text':'Voir illustration'}, {'citation':['fig'], 'relation_kind':'crossref'}]}
    later = {'id':'later', 'kind':'paragraph', 'inline':[{'text':'Suite'}]}
    ordered, placements = publisher_module('epub_figures').plan_figure_layout([body, later, figure])
    assert [block['id'] for block in ordered] == ['p', 'fig', 'later']
    assert placements[0]['after_block'] == 'p'


def test_translated_notes_follow_figure_moved_before_later_paragraph(tmp_path):
    publication = publisher_module('epub_publication')
    figures = publisher_module('epub_figures')
    book = {'schema':'epub-book/2', 'chapters':[{'id':'c', 'blocks':[
        {'id':'p', 'kind':'paragraph', 'inline':[{'text':'See image'}]},
        {'id':'later', 'kind':'paragraph', 'inline':[{'note':'n1','id':'r1'}]},
        {'id':'fig', 'kind':'figure', 'after_block':'p', 'placement_evidence':'source checked', 'inline':[{'note':'n2','id':'r2'}]}]}],
        'notes':[{'id':'n1','chapter':'c','label':'a','association_evidence':'source checked','blocks':[]}, {'id':'n2','chapter':'c','label':'b','association_evidence':'source checked','blocks':[]}]}
    compiled = publication.apply_publication(book, tmp_path)
    compiled['chapters'][0]['blocks'], _ = figures.plan_figure_layout(compiled['chapters'][0]['blocks'])
    publication.number_notes_in_reading_order(compiled)
    assert [(note['id'], note['label']) for note in compiled['notes']] == [('n2','1'), ('n1','2')]


def test_epub_reference_examples_reside_in_packaged_template_directory():
    from pathlib import Path
    from ainiee_translate.pdf_bridge import skill_root
    package = Path(skill_root()).parent
    examples = package / 'assets/template/epub'
    for name, epub in [('reference-book', 'reference.epub'), ('weread-compat', 'compatible.epub')]:
        assert (examples / name / epub).is_file()
        assert (examples / name / 'source.json').is_file()
        assert (examples / name / 'build_example.py').is_file()
    assert not (skill_root() / 'examples').exists()
