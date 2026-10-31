import copy
import json
from pathlib import Path

import pytest
from ainiee_translate.artifact_io import write_json
from ainiee_translate.workbench_glossary import prepare_glossary, apply_glossary
from ainiee_translate.workbench_bridge import load_project, runtime


def materials(tmp_path):
    locked = tmp_path / 'glossary.json'
    rows = [dict(src='account', dst='账户', category='finance', note='保持说明'),
            dict(src='household account', dst='家庭账户', keep_source=False, private={'keep': 1}),
            dict(src='module', dst='模'), dict(src='free module', dst='自由模')]
    write_json(locked, dict(terms=rows))
    metadata = tmp_path / 'evidence.json'
    info = [dict(src=r['src'], category='finance' if n < 2 else 'math',
                 context='A sentence about ' + r['src'] + '.', page=n + 1) for n, r in enumerate(rows)]
    info[1]['base'] = 'account'
    info[3]['base'] = 'module'
    write_json(metadata, dict(terms=info))
    return locked, metadata, info


def test_term_profile_and_independent_family_writeback(tmp_path):
    locked, metadata, info = materials(tmp_path)
    proposal = tmp_path / 'suggested.json'
    original = json.loads(locked.read_text(encoding='utf-8'))
    suggested = copy.deepcopy(original)
    suggested['terms'][1]['dst'] = '家计账户'
    write_json(proposal, suggested)
    project = tmp_path / 'r'
    prepare_glossary(locked, project, proposal, review_data=metadata)
    store, binding = load_project(project)
    assert store.package['review_profile'] == 'glossary'
    items = store.package['items']
    assert items[1]['term_info'] == {k: v for k, v in info[1].items() if k != 'src'} | {'source': info[1]['src']}
    assert items[1]['before'] == [dict(id='dst', type='text', text='家庭账户')]
    assert items[1]['proposal'] == [dict(id='dst', type='text', text='家计账户')]
    assert not items[1]['requires_human']
    assert items[1]['rationale'] == ''
    assert len({i['target_id'] for i in items}) == 4
    draft = store.state()['drafts']
    draft['items'][items[1]['id']] = dict(mode='keep')
    draft['items'][items[3]['id']] = dict(mode='edit', touched=True, edits={'dst': '自由模（修订）'})
    store.save(draft, draft['revision'])
    store.submit([items[1]['id'], items[3]['id']], store.state()['drafts']['revision'])
    result = apply_glossary(project, locked, dict(human_instruction='继续', human_reference='test'))
    actual = json.loads(locked.read_text(encoding='utf-8'))
    assert result['applied'] == 1
    assert actual['terms'][1] == original['terms'][1]
    assert actual['terms'][0] == original['terms'][0]
    assert actual['terms'][3]['dst'] == '自由模（修订）'


def test_missing_evidence_still_opens_but_requires_review(tmp_path):
    locked, _, _ = materials(tmp_path)
    prepare_glossary(locked, tmp_path / 'r')
    store, _ = load_project(tmp_path / 'r')
    assert all(i['requires_human'] for i in store.package['items'])
    assert store.package['items'][0]['term_info']['page'] is None


@pytest.mark.parametrize('bad', ['duplicate', 'unknown', 'unknown_base', 'cycle', 'bool_page', 'bad_context', 'duplicate_source'])
def test_metadata_rejects_ambiguous_or_invalid_materials(tmp_path, bad):
    locked, metadata, info = materials(tmp_path)
    if bad == 'duplicate': info.append(info[0])
    if bad == 'unknown': info[0]['src'] = 'unknown'
    if bad == 'unknown_base': info[1]['base'] = 'unknown'
    if bad == 'cycle': info[0]['base'] = info[1]['src']
    if bad == 'bool_page': info[0]['page'] = True
    if bad == 'bad_context': info[0]['context'] = ['wrong']
    if bad == 'duplicate_source':
        data = json.loads(locked.read_text(encoding='utf-8'))
        data['terms'].append(data['terms'][0])
        write_json(locked, data)
    write_json(metadata, dict(terms=info))
    with pytest.raises(ValueError):
        prepare_glossary(locked, tmp_path / 'r', review_data=metadata)
    assert not (tmp_path / 'r').exists()


def test_runtime_is_030_and_has_navigation_module():
    root = Path(__file__).parents[2] / 'src/ainiee_translate/workbench_runtime'
    assert "'0.3.0'" in (root / 'review_workbench/__init__.py').read_text()
    assert (root / 'web/scripts/navigation.js').is_file()


def test_frozen_term_metadata_is_validated_and_portable(tmp_path):
    from ainiee_translate.workbench_runtime.review_workbench.transfer import export_package, import_results
    from ainiee_translate.workbench_runtime.review_workbench.storage import Store
    import zipfile
    locked, metadata, _ = materials(tmp_path)
    project = tmp_path / 'r'
    prepare_glossary(locked, project, review_data=metadata)
    store, _ = load_project(project)
    for change in ('unknown_base', 'false_required', 'wrong_identity'):
        bad = copy.deepcopy(store.package)
        if change == 'unknown_base': bad['items'][1]['term_info']['base'] = 'unknown'
        if change == 'false_required': bad['items'][1]['term_info']['page'] = None
        if change == 'wrong_identity': bad['items'][1]['term_info']['source'] = 'changed'
        with pytest.raises(ValueError): runtime().model.validate_package(bad)
    archive = tmp_path / 'recipient.zip'
    export_package(store.root, archive)
    recipient = tmp_path / 'friend'
    with zipfile.ZipFile(archive) as z:
        assert 'web/scripts/glossary.js' in z.namelist()
        assert 'web/scripts/navigation.js' in z.namelist()
        z.extractall(recipient)
    remote = Store(recipient)
    draft = remote.state()['drafts']
    draft['items']['terms-2'] = dict(mode='edit', touched=True, edits={'dst':'家计账户'})
    remote.save(draft, draft['revision'])
    remote.submit(['terms-2'], remote.state()['drafts']['revision'])
    from ainiee_translate.workbench_runtime.review_workbench.transfer import result_envelope
    returned = tmp_path / 'returned.json'
    write_json(returned, result_envelope(remote))
    import_results(store.root, returned)
    assert apply_glossary(project, locked, dict(human_instruction='继续',human_reference='test'))['applied'] == 1
    actual = json.loads(locked.read_text(encoding='utf-8'))['terms'][1]
    assert actual['dst'] == '家计账户' and actual['private'] == {'keep':1}


def test_legacy_full_field_binding_still_applies(tmp_path):
    from ainiee_translate.workbench_bridge import package, block, prepare_project
    from ainiee_translate.artifact_io import digest
    from ainiee_translate.workbench_glossary import _fields, _blocks
    locked = tmp_path / 'old.json'
    row = dict(src='account', dst='账户', category='finance', note='原说明', private=1)
    write_json(locked, {'terms':[row]})
    fields = _fields('terms', row)
    blocks = _blocks(row, fields)
    p = package('旧审核包', [{'id':'terms','title':'术语'}])
    p['items'] = [dict(id='terms-1',target_id='terms-1',group_id='terms',facets={},requires_human=False,
                       before=blocks,baseline=copy.deepcopy(blocks),proposal=None,evidence=[block('source','account')],
                       rationale='',location='account',allow_empty_blocks=['category','note'])]
    info = dict(group='terms',index=0,identity_key='src',identity='account',fields=fields,
                identity_hash=digest({k:v for k,v in row.items() if k not in [f['key'] for f in fields]}))
    project = tmp_path / 'r'
    prepare_project(project,p,dict(kind='glossary',locked=str(locked.resolve()),items={'terms-1':info}))
    store,_ = load_project(project)
    d = store.state()['drafts']
    d['items']['terms-1'] = dict(mode='edit',touched=True,edits={'dst':'账目','category':'economics','note':'旧包修订'})
    store.save(d,d['revision']); store.submit(['terms-1'],store.state()['drafts']['revision'])
    assert apply_glossary(project,locked,dict(human_instruction='继续',human_reference='legacy-test'))['applied'] == 1
    actual = json.loads(locked.read_text(encoding='utf-8'))['terms'][0]
    assert actual == row | dict(dst='账目',category='economics',note='旧包修订')
