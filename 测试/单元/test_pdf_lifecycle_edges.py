"""Regression cases for revision routing, concurrent mutation and evidence reuse."""
import copy
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / '夹具'))
from v2_sample import make_bound
from ainiee_translate import cache_io
from ainiee_translate.artifact_io import write_json
from ainiee_translate.pdf_bridge import contract
from ainiee_translate.pdf_cache import reconcile_cache, apply_cache_to_book
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheProject import CacheProject
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheFile import CacheFile
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheItem import CacheItem


def test_concurrent_writers_wait_for_lock_and_preserve_updates(tmp_path):
    cache = tmp_path / 'counter.txt'
    cache.write_text('0')
    script = '''
import sys,time
from pathlib import Path
from ainiee_translate.cache_io import locked
path=Path(sys.argv[1])
print('ready',flush=True)
with locked(str(path)):
    current=int(path.read_text())
    time.sleep(.1)
    path.write_text(str(current+1))
'''
    children = []
    try:
        with cache_io.locked(str(cache)):
            children = [subprocess.Popen([sys.executable, '-c', script, str(cache)], stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE, text=True) for _ in range(2)]
            assert all(p.stdout.readline().strip() == 'ready' for p in children)
            time.sleep(.35)
            assert cache.read_text() == '0', 'a concurrent writer entered the held critical section'
        for child in children:
            _, error = child.communicate(timeout=15)
            assert child.returncode == 0, error
        assert cache.read_text() == '2'
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
                child.communicate()


def test_reconcile_keeps_routing_and_unaffected_source_proof(tmp_path):
    book, _, cf, _, _ = make_bound(tmp_path)
    cf.extra['ainiee_pdf'].update(book_source='source-book.json', work='relative work', custom_context={'id': 'project'})
    changed = copy.deepcopy(book)
    changed['revision'] += 1
    fresh = reconcile_cache(changed, cf)
    assert fresh.extra['ainiee_pdf']['book_source'] == 'source-book.json'
    assert fresh.extra['ainiee_pdf']['work'] == 'relative work'
    assert fresh.extra['ainiee_pdf']['custom_context'] == {'id': 'project'}
    assert all(i.extra['ainiee_pdf']['proofreading'] == old.extra['ainiee_pdf']['proofreading']
               for i, old in zip(fresh.items, cf.items))
    assert all(i.extra['ainiee_pdf']['source_verification']['status'] == 'verified' for i in fresh.items)


def _split_book(book):
    changed = copy.deepcopy(book)
    changed['revision'] += 1
    unit = next(u for u in changed['units'] if u['source_text'] == 'Three objects.')
    old_id = unit['unit_id']
    unit['unit_id'] = 'replacement-id'
    unit['source_revision'] += 1
    return changed, old_id


def test_cli_reconcile_allocates_project_wide_indices(tmp_path):
    from ainiee_translate.pdf_review import main
    book, _, cf, _, ctx = make_bound(tmp_path)
    changed, old_id = _split_book(book)
    other = CacheFile(storage_path='other.txt', items=[CacheItem(text_index=max(i.text_index for i in cf.items)+1,
                                                                source_text='untouched')])
    cache_io.save_cache(CacheProject(files={'source.pdf': cf, 'other.txt': other}), str(ctx['cache_path']))
    write_json(tmp_path/'changed.json', changed)
    write_json(tmp_path/'mapping.json', {old_id: ['replacement-id']})
    main(['reconcile', '--book', str(tmp_path/'changed.json'), '--cache', str(ctx['cache_path']),
          '--work', str(tmp_path), '--output', str(tmp_path/'reconciled.json'),
          '--id-mapping', str(tmp_path/'mapping.json')])
    project = cache_io.load_cache(str(ctx['cache_path']))
    indices = [i.text_index for i in cache_io.iter_items(project)]
    assert len(indices) == len(set(indices))
    replacement = next(i for i in cache_io.iter_items(project) if i.extra.get('ainiee_pdf', {}).get('unit_id')=='replacement-id')
    assert not replacement.translated_text and replacement.translation_status == 0
    assert project.files['other.txt'].items[0].text_index == other.items[0].text_index


def test_duplicate_split_destinations_rejected_without_mutation(tmp_path):
    book, _, cf, _, _ = make_bound(tmp_path)
    changed, old_id = _split_book(book)
    before = cf.to_dict()
    with pytest.raises(ValueError, match='duplicate|Duplicate'):
        reconcile_cache(changed, cf, {old_id: ['replacement-id', 'replacement-id']})
    assert cf.to_dict() == before


def test_merge_mapping_does_not_guess_translation(tmp_path):
    book, _, cf, _, _ = make_bound(tmp_path)
    changed, old_id = _split_book(book)
    second = next(u for u in book['units'] if u['unit_id'] != old_id)
    fresh = reconcile_cache(changed, cf, {old_id: ['replacement-id'], second['unit_id']: ['replacement-id']})
    mapped = next(i for i in fresh.items if i.extra['ainiee_pdf']['unit_id']=='replacement-id')
    assert not mapped.translated_text and 'proofreading' not in mapped.extra['ainiee_pdf']
    assert next(i for i in fresh.items if i.extra['ainiee_pdf']['unit_id']==second['unit_id']).translation_status == 0


def test_reconcile_rejects_replacement_pdf_and_current_cache_mismatch(tmp_path):
    book, _, cf, _, _ = make_bound(tmp_path)
    changed = copy.deepcopy(book)
    changed['source_sha256'] = '0' * 64
    with pytest.raises(ValueError, match='PDF/document'):
        reconcile_cache(changed, cf)
    changed = copy.deepcopy(book)
    changed['revision'] += 1
    with pytest.raises(ValueError, match='reconcile'):
        apply_cache_to_book(changed, cf)


def test_translation_change_invalidates_only_its_proof(tmp_path):
    book, _, cf, _, ctx = make_bound(tmp_path)
    item = next(i for i in cf.items if i.extra['ainiee_pdf']['translation_policy']=='translate')
    project = CacheProject(files={'source.pdf':cf})
    assert cache_io.set_polish(project, item.text_index, item.translated_text)
    assert item.extra['ainiee_pdf'].get('proofreading')
    assert cache_io.set_polish(project, item.text_index, item.translated_text+' revised')
    assert 'proofreading' not in item.extra['ainiee_pdf']
    assert item.extra['ainiee_pdf']['source_verification']['status']=='verified'
    assert any(i.extra['ainiee_pdf'].get('proofreading') for i in cf.items if i is not item)


def test_waiver_bound_to_actual_reference_and_related_text(tmp_path):
    from ainiee_translate.pdf_issues import issue_ledger, decide_issue, publication_decisions
    book, _, _, _, _ = make_bound(tmp_path)
    ref = book['references'][0]
    ref['status'] = 'pending'
    ledger = issue_ledger(book, [{'id':'R1','kind':'semantic_reference','cause':'ambiguous', 'ref_id':ref['ref_id']}])
    ledger = decide_issue(ledger, 'R1', action='plain_text', reason='human selected plain text', actor='human', book=book)
    decision = publication_decisions(ledger, book)['decisions']
    assert len(decision)==1 and decision[0]['action']=='text_only'
    changed = copy.deepcopy(book)
    changed['references'][0]['display']='changed display'
    assert publication_decisions(ledger, changed)['decisions']==[]
    changed = copy.deepcopy(book)
    unit = next(u for u in changed['units'] if u['block_id']==ref['block_id'])
    unit['source_sha256']='f'*64
    assert publication_decisions(ledger, changed)['decisions']==[]


def test_unknown_reference_cannot_be_waived(tmp_path):
    from ainiee_translate.pdf_issues import issue_ledger, decide_issue
    book, _, _, _, _ = make_bound(tmp_path)
    ledger=issue_ledger(book,[{'id':'R1','kind':'semantic_reference','cause':'invented','ref_id':'not-in-book'}])
    with pytest.raises(ValueError, match='reference'):
        decide_issue(ledger,'R1',action='plain_text',reason='approve',actor='human',book=book)


def test_issue_report_cli_runs_after_definition(tmp_path):
    from ainiee_translate.pdf_issues import main
    write_json(tmp_path/'book.json', {'document_id':'doc','revision':1,'references':[]})
    result=subprocess.run([sys.executable,'-m','ainiee_translate.pdf_issues','report','--book',str(tmp_path/'book.json'),
        '--ledger',str(tmp_path/'issues.json'),'--output',str(tmp_path/'issues.md')],capture_output=True,text=True)
    assert result.returncode == 0, result.stderr
    assert (tmp_path/'issues.md').exists()


def test_multichapter_review_import_merges_current_proofs(tmp_path):
    from ainiee_translate.pdf_review import main, export_review_tasks
    book, _, cf, _, ctx = make_bound(tmp_path)
    write_json(tmp_path/'source.json', book)
    output=tmp_path/'incremental-proof.json'
    for chapter in ['c1','c2']:
        ids=[u['unit_id'] for u in book['units'] if u['chapter_id']==chapter]
        tasks=export_review_tasks(book,cf,work=tmp_path,prompt_path=ctx['prompt_path'],glossary_path=ctx['glossary_path'],
            context_id='review-'+chapter,translation_context_id='translator',unit_ids=ids)
        results={'records':[dict(unit_id=u['unit_id'],source_sha256=u['source_sha256'],target_sha256=u['target_sha256'],
            context_id=tasks['context_id'],status='passed',findings=[],checks=tasks['required_checks'],
            evidence={'pdf_sha256':book['source_sha256'],
                      'pages':sorted({p.get('physical_page',p.get('page')) for p in u['provenance']}),
                      'observations':'synthetic incremental evidence'}) for u in tasks['units']]}
        write_json(tmp_path/'tasks.json',tasks); write_json(tmp_path/'results.json',results)
        main(['import','--book',str(tmp_path/'source.json'),'--cache',str(ctx['cache_path']),'--work',str(tmp_path),
            '--output',str(output),'--prompt',str(ctx['prompt_path']),'--glossary',str(ctx['glossary_path']),
            '--tasks',str(tmp_path/'tasks.json'),'--results',str(tmp_path/'results.json')])
    records=json.loads(output.read_text(encoding='utf8'))['records']
    assert {r['unit_id'] for r in records}=={u['unit_id'] for u in book['units'] if u['chapter_id'] in ['c1','c2']}
    assert {r['context_id'] for r in records}=={'review-c1','review-c2'}

@pytest.mark.parametrize('operation', ['split','merge'])
def test_structural_split_merge_preserving_first_id_needs_mapping(tmp_path, operation):
    from ainiee_translate.pdf_cache import book_to_cache_file
    book, _, cf, _, _ = make_bound(tmp_path)
    changed = copy.deepcopy(book)
    block = changed['chapters'][0]['blocks'][0]
    original_uid = next(u['unit_id'] for u in book['units'] if u['source_text']=='Three objects.')
    block['inline'][0]['text'] = 'Three '
    block['inline'].append({'text':'objects.'})
    changed['revision'] += 1
    split = contract().prepare_translation_book(changed, tmp_path)
    extra_uid = next(u['unit_id'] for u in split['units'] if u['source_text']=='objects.')
    assert original_uid in {u['unit_id'] for u in split['units']}
    if operation == 'split':
        with pytest.raises(ValueError, match='explicit ID mapping'):
            reconcile_cache(split, cf)
        reconciled = reconcile_cache(split, cf, {original_uid:[original_uid,extra_uid]})
        assert not next(i for i in reconciled.items if i.extra['ainiee_pdf']['unit_id']==original_uid).translated_text
    else:
        split_cf = book_to_cache_file(split, storage_path='source.pdf')
        for item in split_cf.items:
            if item.translation_status != 7:
                item.translation_status=1
                item.translated_text='synthetic translation'
        with pytest.raises(ValueError, match='explicit ID mapping'):
            reconcile_cache(book, split_cf)
        reconciled = reconcile_cache(book, split_cf, {original_uid:[original_uid],extra_uid:[original_uid]})
        assert not next(i for i in reconciled.items if i.extra['ainiee_pdf']['unit_id']==original_uid).translated_text


def test_manifest_builder_rejects_malformed_direct_proof(tmp_path):
    from ainiee_translate.pdf_review import build_translation_manifest
    book, target, cf, _, ctx = make_bound(tmp_path)
    item=cf.items[0]
    record=item.extra['ainiee_pdf']['proofreading']
    record.pop('checks')
    record.pop('findings')
    record['evidence']='garbage'
    ledger=json.loads(ctx['review_path'].read_text(encoding='utf8'))
    ledger['records']=[record if row['unit_id']==record['unit_id'] else row for row in ledger['records']]
    write_json(ctx['review_path'],ledger)
    cache_io.save_cache(CacheProject(files={'source.pdf':cf}),str(ctx['cache_path']))
    with pytest.raises(ValueError):
        build_translation_manifest(book,target,cf,work=tmp_path,**ctx)


def test_manifest_builder_checks_current_disk_cache(tmp_path):
    from ainiee_translate.pdf_review import build_translation_manifest
    book, target, cf, _, ctx = make_bound(tmp_path)
    disk=cache_io.load_cache(str(ctx['cache_path']))
    disk.files['source.pdf'].items[0].translated_text='different on disk'
    cache_io.save_cache(disk,str(ctx['cache_path']))
    with pytest.raises(ValueError,match='cache'):
        build_translation_manifest(book,target,cf,work=tmp_path,**ctx)
