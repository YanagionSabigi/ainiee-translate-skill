import copy
import pytest
from test_reading_report import ready
from test_workbench_glossary import submit, INSTRUCTION
from ainiee_translate.artifact_io import write_json


def setup_reading(tmp_path):
    from ainiee_translate.workbench_reading import prepare_reading
    root, rd, tasks = ready(tmp_path)
    project = tmp_path / 'review'
    prepare_reading(rd, root / 'cache.json', project)
    return root, rd, tasks, project


def test_recommendation_uses_existing_transaction_and_is_idempotent(tmp_path):
    from ainiee_translate.workbench_reading import apply_reading
    from ainiee_translate import cache_io
    root, rd, tasks, project = setup_reading(tmp_path)
    submit(project)
    result = apply_reading(project, root / 'cache.json', INSTRUCTION)
    assert result['applied'] == 1 and result['conflicts'] == 0
    assert cache_io.load_cache(root / 'cache.json').files['source.epub'].items[1].translated_text == '一盏宁静的灯照着窗户。'
    assert list((rd / 'transactions').glob('*.json'))
    assert apply_reading(project, root / 'cache.json', INSTRUCTION)['applied'] == 0


def test_comments_and_drafts_are_not_approval(tmp_path):
    from ainiee_translate.workbench_reading import apply_reading
    from ainiee_translate.reading_round import load_issues
    root, rd, tasks, project = setup_reading(tmp_path)
    assert apply_reading(project, root / 'cache.json', INSTRUCTION)['applied'] == 0
    submit(project, 'comment')
    assert apply_reading(project, root / 'cache.json', INSTRUCTION)['needs_agent']
    assert load_issues(rd)['issues'][0]['status'] == 'needs_approval'


@pytest.mark.parametrize('change', ['assessment', 'annotation', 'cache'])
def test_stale_business_versions_rejected(tmp_path, change):
    from ainiee_translate.workbench_reading import apply_reading
    from ainiee_translate.reading_round import load_issues
    from ainiee_translate import cache_io
    root, rd, tasks, project = setup_reading(tmp_path)
    submit(project)
    if change == 'cache':
        p = cache_io.load_cache(root / 'cache.json')
        p.files['source.epub'].items[1].translated_text = '后来的修改'
        cache_io.save_cache(p, root / 'cache.json')
    else:
        issues = load_issues(rd)
        if change == 'assessment':
            issues['issues'][0]['current_assessment_revision'] = 'different'
        else:
            issues['issues'][0]['annotation_revision'] += 1
        write_json(rd / 'issues.json', issues)
    assert apply_reading(project, root / 'cache.json', INSTRUCTION)['conflicts'] == 1
    assert not list((rd / 'transactions').glob('*.json'))


def test_edit_keeps_internal_newline_and_emoji(tmp_path):
    from ainiee_translate.workbench_reading import apply_reading
    from ainiee_translate.workbench_bridge import load_project
    from ainiee_translate import cache_io
    root, rd, tasks, project = setup_reading(tmp_path)
    store, _ = load_project(project)
    bid = store.package['items'][0]['before'][0]['id']
    text = '一盏宁静的灯。\n照着窗户。😀'
    submit(project, 'edit', {bid: text})
    assert apply_reading(project, root / 'cache.json', INSTRUCTION)['applied'] == 1
    assert cache_io.load_cache(root / 'cache.json').files['source.epub'].items[1].translated_text == text


def test_cross_paragraph_edit_maps_each_block_without_splitting_newlines(tmp_path):
    from test_reading_match import setup_round
    from test_reading_review import tasks_for, result_for
    from ainiee_translate.reading_review import import_assessments
    from ainiee_translate.workbench_reading import prepare_reading, apply_reading
    from ainiee_translate.workbench_bridge import load_project
    from ainiee_translate import cache_io
    root, rd = setup_round(tmp_path, '前半句在这里结束。后半句从这里开始。')
    tasks = tasks_for(root, rd)
    result = result_for(tasks)
    parts = tasks['issues'][0]['segments']
    assert len(parts) == 2
    for candidate in result['issues'][0]['candidates']:
        candidate['edits'] = [dict(segment_id=s['segment_id'], replacement_text=s['current_target_text'] + ('新' if candidate['label'] == 'C' else '')) for s in parts]
        candidate['text'] = '\n'.join(e['replacement_text'] for e in candidate['edits'])
    result['issues'][0]['recommended_text'] = result['issues'][0]['candidates'][1]['text']
    import_assessments(rd, result)
    project = tmp_path / 'cross-review'
    prepare_reading(rd, root / 'cache.json', project)
    store, _ = load_project(project)
    bids = [b['id'] for b in store.package['items'][0]['before']]
    submit(project, 'edit', dict(zip(bids, ['第一段\n仍是第一段 😀', '第二段全文'])))
    assert apply_reading(project, root / 'cache.json', INSTRUCTION)['applied'] == 1
    items = cache_io.load_cache(root / 'cache.json').files['source.epub'].items
    assert [items[2].translated_text, items[3].translated_text] == ['第一段\n仍是第一段 😀', '第二段全文']


def test_overlapping_issues_with_different_decisions_do_not_write(tmp_path):
    from ainiee_translate.workbench_reading import prepare_reading, apply_reading
    from ainiee_translate.reading_report import render_report
    from ainiee_translate.reading_round import load_issues, load_round, read
    from ainiee_translate.workbench_bridge import load_project
    root, rd, _ = ready(tmp_path)
    # Two assessed issues selecting the same business segment, as may occur with
    # distinct phone annotations; preserve separate issue identities.
    report_path = render_report(rd)
    report = read(report_path.with_suffix('.json'))
    shown = copy.deepcopy(report['issues'][0])
    shown['issue_id'] = 'WR-R0001-000002'
    report['issues'].append(shown)
    write_json(report_path.with_suffix('.json'), report)
    issues = load_issues(rd)
    second = copy.deepcopy(issues['issues'][0])
    second['issue_id'] = shown['issue_id']
    issues['issues'].append(second)
    write_json(rd / 'issues.json', issues)
    project = tmp_path / 'overlap-review'
    prepare_reading(rd, root / 'cache.json', project)
    store, _ = load_project(project)
    draft = store.state()['drafts']
    draft['items'] = {report['issues'][0]['issue_id']: dict(mode='accept'), shown['issue_id']: dict(mode='keep')}
    store.save(draft, draft['revision'])
    store.submit(list(draft['items']), store.state()['drafts']['revision'])
    result = apply_reading(project, root / 'cache.json', INSTRUCTION)
    assert result['conflicts'] == 2 and result['applied'] == 0
    assert not list((rd / 'transactions').glob('*.json'))
