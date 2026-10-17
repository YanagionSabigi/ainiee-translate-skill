"""Versioned source/translation contract shared by preparation and publication.

Text lives only in chapters/notes and their original containers. ``units`` is an
index of JSON paths with immutable source evidence, never a second render model.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re


def content_digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True,
                                     separators=(',', ':')).encode('utf-8')).hexdigest()


def localized_labels(language,source,overrides=None):
    labels={'contents':'目录','notes':'注释','return':'返回'} if language.split('-')[0]=='zh' else deepcopy(source)
    if overrides:
        if set(overrides)-set(labels) or any(not isinstance(v,str) or not v.strip() for v in overrides.values()):
            raise ValueError('Invalid editorial labels')
        labels.update(overrides)
    return labels


def _file_hash(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8-sig'))


def value_at(book, path):
    value = book
    for part in path:
        value = value[part]
    return value


def set_value(book, path, value):
    parent = value_at(book, path[:-1])
    parent[path[-1]] = value


def _walk_text(node, path):
    """Only human-readable content, excluding labels, IDs and source evidence."""
    if isinstance(node, str):
        yield path, node
    elif isinstance(node, list):
        for i, child in enumerate(node):
            yield from _walk_text(child, path + [i])
    elif isinstance(node, dict):
        for key in ('title', 'text', 'caption', 'alt'):
            if isinstance(node.get(key), str):
                yield path + [key], node[key]
        for key in ('inline', 'rows', 'items', 'blocks'):
            if key in node:
                yield from _walk_text(node[key], path + [key])
        if isinstance(node.get('asset'), dict):
            yield from _walk_text(node['asset'], path + ['asset'])


def text_slots(book):
    if isinstance(book.get('metadata', {}).get('title'), str):
        yield ['metadata', 'title'], book['metadata']['title'], None, None, book.get('metadata_provenance', []), False
    for group_key in ('chapters', 'notes'):
        for gi, group in enumerate(book.get(group_key, [])):
            chapter = group['id'] if group_key == 'chapters' else group['chapter']
            if isinstance(group.get('title'), str):
                yield [group_key, gi, 'title'], group['title'], chapter, None, group.get('heading_provenance', []), False
            for bi, block in enumerate(group.get('blocks', [])):
                preserve = block.get('translation_policy') == 'preserve_source' or block.get('role') in {'bibliography-entry', 'bibliography', 'reference-entry'} or block.get('kind') == 'bibliography-entry'
                for path, text in _walk_text(block, [group_key, gi, 'blocks', bi]):
                    if text.strip():
                        yield path, text, chapter, block['id'], block.get('provenance', []) or ([block['source_region']] if block.get('source_region') else []), preserve


def iter_units(book):
    if book.get('schema') != 'epub-book/2':
        raise ValueError('Translation requires epub-book/2; legacy books remain source publications')
    yield from book.get('units', [])


def _inline_nodes(node, path):
    if isinstance(node, list):
        for i, child in enumerate(node):
            yield from _inline_nodes(child, path + [i])
    elif isinstance(node, dict):
        if any(k in node for k in ('note', 'link', 'citation', 'ref')):
            yield path, node
        for field in ('inline', 'rows', 'items'):
            if field in node:
                yield from _inline_nodes(node[field], path + [field])


def _assets(node):
    if isinstance(node,list):
        for child in node: yield from _assets(child)
    elif isinstance(node,dict):
        if isinstance(node.get('asset'),dict): yield node['asset']
        for key in ('chapters','notes','blocks','inline','rows','items','structure_rules','publication','images'):
            if key in node: yield from _assets(node[key])


def extraction_bindings(book,work):
    work=Path(work).resolve(); results=book.get('mineru_result') or []
    if isinstance(results,dict): results=[results]
    bindings=[]
    for result in results:
        if not result.get('originals'): raise ValueError('MinerU original result locator is missing')
        root=(work/result['originals']).resolve(); manifest=root.parent/'import-manifest.json'
        if not root.is_relative_to(work) or not manifest.is_file(): raise ValueError('MinerU original import manifest is missing')
        data=_load(manifest)
        if data.get('bundle_sha256')!=result['bundle_sha256']: raise ValueError('MinerU original bundle fingerprint mismatch')
        for item in data['files']:
            path=(root/item['path']).resolve()
            if not path.is_relative_to(root) or not path.is_file() or _file_hash(path)!=item['sha256']:
                raise ValueError('Immutable original MinerU result changed')
        bindings.append({'manifest':manifest.relative_to(work).as_posix(),'sha256':_file_hash(manifest)})
    return bindings


def unit_structure_digest(book,unit):
    """Bind non-text structure/resources and related links, without global invalidation."""
    if not unit.get('block_id'):
        return content_digest({'owner':unit['chapter_id'],'provenance':unit.get('provenance',[])})
    block=next(b for g in book['chapters']+book['notes'] for b in g['blocks'] if b['id']==unit['block_id'])
    snapshot=deepcopy(block)
    def erase(node):
        if isinstance(node,list):
            for item in node: erase(item)
        elif isinstance(node,dict):
            for key in ('text','title','caption','alt'):
                if key in node: node[key]=None
            for key in ('inline','rows','items','asset'):
                if key in node: erase(node[key])
    erase(snapshot)
    refs=[{k:r[k] for k in ('ref_id','kind','targets','status','evidence')} for r in book.get('references',[]) if r['block_id']==unit['block_id']]
    return content_digest([snapshot,refs])


REQUIRED_CHECKS={'omissions','meaning','ocr','terminology','numbers','formulae','structure','references'}


def validate_proof_record(proof,unit,*,source_sha256,target_text,prompt_sha256,glossary_sha256):
    evidence=proof.get('evidence')
    pages={p.get('page',p.get('physical_page')) for p in unit.get('provenance',[]) if isinstance(p,dict)}-{None}
    if (proof.get('status')!='passed' or proof.get('independent') is not True
        or not proof.get('context_id') or not proof.get('translation_context_id')
        or proof['context_id']==proof['translation_context_id']
        or proof.get('unit_id')!=unit['unit_id'] or proof.get('source_sha256')!=unit['source_sha256']
        or proof.get('source_revision')!=unit['source_revision']
        or proof.get('structure_sha256')!=unit.get('structure_sha256')
        or proof.get('target_sha256')!=content_digest(target_text)
        or proof.get('prompt_sha256')!=prompt_sha256 or proof.get('glossary_sha256')!=glossary_sha256
        or not unit.get('provenance') or proof.get('provenance')!=unit['provenance']
        or not isinstance(evidence,dict) or evidence.get('pdf_sha256')!=source_sha256
        or not isinstance(evidence.get('pages'),list) or not evidence['pages']
        or not all(type(p) is int and p>0 for p in evidence['pages'])
        or not pages.issubset(set(evidence['pages'])) or not evidence.get('observations')
        or set(proof.get('checks',[]))!=REQUIRED_CHECKS or not isinstance(proof.get('findings'),list)
        or any(not isinstance(f,dict) or f.get('status')!='resolved' or not f.get('resolution') for f in proof.get('findings',[]))):
        raise ValueError('Invalid current independent PDF proofreading record: '+unit['unit_id'])


def prepare_translation_book(book, work):
    """Prepare a minimum structure without asserting OCR or proofreading success.

    Existing v2 IDs survive source corrections. A changed source leaf increments
    only its source_revision. Explicit IDs are required for structural split/merge.
    """
    result = deepcopy(book)
    if result.get('schema') not in {'epub-book/1', 'epub-book/2'}:
        raise ValueError('Unsupported source book schema')
    if not result.get('chapters') or not result.get('source_sha256'):
        raise ValueError('Minimum structure needs chapters and source PDF hash')
    def slot_key(chapter, block, path):
        # Array positions are locators, never identities. Owner IDs survive insertions.
        suffix = path[5:] if block else path[2:] if chapter else path
        return (chapter, block, tuple(suffix))
    old_units = {slot_key(u['chapter_id'], u['block_id'], u['path']): u for u in result.get('units', [])}
    result['schema'] = 'epub-book/2'
    result.setdefault('document_id', 'doc-' + result['source_sha256'][:24])
    result.setdefault('revision', 1)
    review = Path(work) / result.get('review_path','review.json')
    if review.is_file(): result['review_sha256'] = _file_hash(review)
    result.setdefault('review_sha256', None)
    result.setdefault('notes', [])
    result['extraction_bindings']=extraction_bindings(result,work)
    for spec in _assets(result):
        if spec.get('path'):
            path=(Path(work)/spec['path']).resolve()
            if not path.is_relative_to(Path(work).resolve()) or not path.is_file(): raise ValueError('Missing/unsafe source resource')
            actual=_file_hash(path)
            if spec.get('sha256') and spec['sha256']!=actual: raise ValueError('Immutable source resource changed')
            spec['sha256']=actual
    units = []
    for path, text, chapter, block, provenance, preserve in text_slots(result):
        key = slot_key(chapter, block, path)
        old = old_units.get(key)
        identity = [result['document_id'], chapter, block, list(key[2])]
        unit = deepcopy(old) if old else {
            'unit_id': 'u-' + content_digest(identity)[:24], 'path': path,
            'chapter_id': chapter, 'block_id': block, 'source_revision': 1,
            'source_verification': {'status': 'pending', 'evidence': []}, 'markers': []}
        if old and old['source_text'] != text:
            unit['source_revision'] += 1
            unit['source_verification'] = {'status': 'pending', 'evidence': []}
        unit['path'] = path
        unit['markers'] = re.findall(r'⟦AT:[^⟧]*⟧', text)
        unit.update(source_text=text, source_sha256=content_digest(text), provenance=deepcopy(provenance),
                    translation_policy='preserve_source' if preserve else 'translate',
                    policy_evidence='Source bibliography metadata is retained verbatim' if preserve else '')
        units.append(unit)
    result['units'] = units
    entities = []
    for chapter in result['chapters']:
        entities.append({'entity_id': chapter['id'], 'kind': 'chapter', 'chapter_id': chapter['id'], 'label': chapter.get('original_label', ''), 'provenance': chapter.get('heading_provenance', [])})
        for block in chapter['blocks']:
            kind = {'heading': 'section', 'table-image': 'table'}.get(block['kind'], block['kind'])
            if block.get('role') in {'bibliography-entry', 'bibliography', 'reference-entry'}: kind = 'bibliography'
            entities.append({'entity_id': block['id'], 'kind': kind, 'chapter_id': chapter['id'], 'label': block.get('original_label', block.get('equation_label', '')), 'provenance': block.get('provenance', [])})
    for note in result['notes']:
        entities.append({'entity_id': note['id'], 'kind': 'note', 'chapter_id': note['chapter'], 'label': note.get('original_label', note.get('label', '')), 'evidence': note.get('association_evidence', ''), 'provenance': note.get('provenance', [])})
        for block in note['blocks']:
            entities.append({'entity_id': block['id'], 'kind': block['kind'], 'chapter_id': note['chapter'], 'label': '', 'provenance': block.get('provenance', [])})
    old_entities = {e['entity_id']:e for e in result.get('entities', [])}
    result['entities'] = [dict(old_entities.get(e['entity_id'], {}), **e) for e in entities]
    refs = []
    registered = {r['ref_id']: r for r in result.get('references', [])}
    note_map = {n['id']: n for n in result['notes']}
    for gkey in ('chapters', 'notes'):
        for gi, group in enumerate(result[gkey]):
            chapter = group['id'] if gkey == 'chapters' else group['chapter']
            for bi, block in enumerate(group['blocks']):
                for path, node in _inline_nodes(block, [gkey, gi, 'blocks', bi]):
                    rid = node.get('ref', node.get('id')) or 'r-' + content_digest([result['document_id'], path])[:24]
                    node['id'] = rid
                    if rid in registered:
                        refs.append(dict(deepcopy(registered[rid]), path=path, chapter_id=chapter, block_id=block['id'])); continue
                    kind = 'note' if 'note' in node else 'citation' if 'citation' in node else 'crossref'
                    targets = node.get('citation') if kind == 'citation' else [node.get('note', node.get('link'))]
                    if isinstance(targets, str): targets = [targets]
                    evidence = node.get('evidence') or (note_map.get(node.get('note'), {}).get('association_evidence'))
                    refs.append({'ref_id': rid, 'kind': kind, 'chapter_id': chapter, 'block_id': block['id'], 'path': path,
                                 'targets': targets or [], 'status': 'resolved' if evidence and all(targets or []) else 'pending',
                                 'evidence': evidence or '', 'display': node.get('text', node.get('label', ''))})
    result['references'] = refs
    for unit in result['units']: unit['structure_sha256']=unit_structure_digest(result,unit)
    result.setdefault('issues', [])
    result['preparation'] = {'minimum_structure_ready': True, 'source_verified': False,
                             'translation_complete': False, 'proofreading_complete': False}
    validate_v2(result)
    return result


def _safe(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', value):
        raise ValueError('Invalid stable ID')


def validate_v2(book):
    if book.get('schema') != 'epub-book/2': raise ValueError('Expected epub-book/2')
    _safe(book.get('document_id'))
    if type(book.get('revision')) is not int or book['revision'] < 1: raise ValueError('Invalid source revision')
    expected = {tuple(p) for p, *_ in text_slots(book)}
    seen = set(); ids = set()
    for unit in iter_units(book):
        _safe(unit['unit_id'])
        if unit['unit_id'] in ids: raise ValueError('Duplicate unit ID')
        ids.add(unit['unit_id']); path = tuple(unit['path'])
        if path in seen: raise ValueError('Duplicate text slot')
        seen.add(path)
        if not isinstance(value_at(book, path), str): raise ValueError('Text slot is not text')
        if content_digest(unit['source_text']) != unit['source_sha256']: raise ValueError('Source unit hash mismatch')
        if unit['translation_policy'] not in {'translate', 'preserve_source'}: raise ValueError('Invalid translation policy')
        if unit['translation_policy'] == 'preserve_source' and not unit.get('policy_evidence'): raise ValueError('Preserve source needs evidence')
    if expected != seen: raise ValueError('Unregistered or stale text slot')
    entities = {}
    for entity in book.get('entities', []):
        eid = entity['entity_id']; _safe(eid)
        if eid in entities: raise ValueError('Duplicate entity ID')
        entities[eid] = entity
    anchor_list = [c['id'] for c in book['chapters']] + [b['id'] for g in book['chapters'] + book['notes'] for b in g['blocks']] + [n['id'] for n in book['notes']]
    if len(anchor_list) != len(set(anchor_list)): raise ValueError('Duplicate content anchor ID')
    anchors=set(anchor_list)
    if set(entities) != anchors: raise ValueError('Entity registry differs from content anchors')
    refs = set()
    for ref in book.get('references', []):
        rid = ref['ref_id']; _safe(rid)
        if rid in refs or rid in anchors: raise ValueError('Duplicate reference ID')
        refs.add(rid)
        if ref['status'] not in {'resolved', 'pending', 'external', 'text_only'}: raise ValueError('Invalid reference status')
        if ref['kind'] not in {'note','crossref','citation'}: raise ValueError('Invalid relationship kind')
        if any(target not in entities for target in ref['targets']): raise ValueError('Missing relation target')
        if ref['status'] == 'resolved' and (not ref['targets'] or not ref.get('evidence')): raise ValueError('Resolved relation needs target evidence')
        if ref['status']=='external' and (ref['targets'] or not ref.get('evidence')): raise ValueError('External relationship needs evidence and no fabricated internal target')
        node = value_at(book, ref['path'])
        if node.get('id') != rid and node.get('ref') != rid: raise ValueError('Reference path identity mismatch')
    actual = {node.get('ref', node.get('id')) for key in ('chapters', 'notes') for gi, g in enumerate(book[key]) for bi, b in enumerate(g['blocks']) for _, node in _inline_nodes(b, [key, gi, 'blocks', bi])}
    if actual != refs: raise ValueError('Unregistered reference occurrence')
    for unit in iter_units(book):
        if unit.get('structure_sha256') != unit_structure_digest(book,unit): raise ValueError('Unit structure fingerprint mismatch')


def validate_translation_binding(book, manifest, work):
    """Fail closed against current source, file evidence and per-unit proof."""
    work = Path(work)
    validate_v2(book)
    if manifest.get('schema') != 'translation-manifest/1': raise ValueError('Expected translation-manifest/1')
    source = _load(work / 'book.source.json'); validate_v2(source)
    if any(value_at(source,u['path']) != u['source_text'] for u in iter_units(source)):
        raise ValueError('Source book text is inconsistent with source unit index')
    for key, value in {'document_id': source['document_id'], 'source_revision': source['revision'],
                       'source_book_sha256': content_digest(source), 'translated_book_sha256': content_digest(book),
                       'source_sha256': source['source_sha256'], 'raw_sha256': source['raw_sha256'],
                       'review_sha256': source['review_sha256']}.items():
        if manifest.get(key) != value: raise ValueError('Translation manifest binding mismatch: ' + key)
    if book['document_id'] != source['document_id'] or book['revision'] != source['revision']:
        raise ValueError('Translated book source identity mismatch')
    state = _load(work / 'state.json')
    if source.get('extraction_bindings') != extraction_bindings(source,work):
        raise ValueError('Original extraction manifest binding changed')
    if _file_hash(state['source_path']) != source['source_sha256']: raise ValueError('Source PDF hash mismatch')
    for name, key in [('raw.json', 'raw_sha256'), (source.get('review_path','review.json'), 'review_sha256')]:
        if _file_hash(work / name) != source[key]: raise ValueError('Current source/raw/review hash mismatch: ' + name)
    if not source.get('structure_rules',{}).get('publication') or not source.get('publication_input'):
        raise ValueError('Formal translation needs the reviewed publication-input and bookmark policy')
    for spec in _assets(source):
        if spec.get('path'):
            path=(work/spec['path']).resolve()
            if not path.is_relative_to(work.resolve()) or not path.is_file() or not spec.get('sha256') or _file_hash(path)!=spec['sha256']:
                raise ValueError('Source resource fingerprint changed')
    artifacts = manifest.get('artifacts', {})
    paths = {}
    for key in ('cache', 'prompt', 'glossary', 'proofreading', 'decisions'):
        item = artifacts.get(key, {}); path = Path(item.get('path', ''))
        path = path if path.is_absolute() else work / path
        if not path.is_file() or _file_hash(path) != item.get('sha256'):
            raise ValueError('Translation artifact hash mismatch: ' + key)
        paths[key] = path
    proof_artifact = _load(paths['proofreading'])
    if proof_artifact.get('schema') != 'pdf-proofreading/1': raise ValueError('Invalid proofreading artifact')
    records = proof_artifact.get('records', [])
    source_units = {u['unit_id']: u for u in iter_units(source)}
    if {u['unit_id'] for u in iter_units(book)} != set(source_units) or set(manifest.get('units', {})) != set(source_units):
        raise ValueError('Translation unit coverage mismatch')
    # All non-text structure is immutable in the independent translated copy.
    skeleton_source, skeleton_target = deepcopy(source), deepcopy(book)
    for unit in iter_units(book):
        uid = unit['unit_id']; original = source_units[uid]
        if unit != original: raise ValueError('Translated source unit metadata changed: ' + uid)
        target = value_at(book, unit['path']); target_hash = content_digest(target)
        if re.findall(r'⟦AT:[^⟧]*⟧',target) != original.get('markers',[]):
            raise ValueError('Translated structural marker order mismatch')
        set_value(skeleton_source, original['path'], None); set_value(skeleton_target, unit['path'], None)
        binding = manifest['units'][uid]
        if binding.get('source_sha256') != original['source_sha256'] or binding.get('target_sha256') != target_hash:
            raise ValueError('Current source/target unit hash mismatch: ' + uid)
        verified = binding.get('source_verified', original.get('source_verification', {}))
        if verified.get('status') != 'verified' or not verified.get('evidence'): raise ValueError('Source unit is not verified: ' + uid)
        if unit['translation_policy'] == 'preserve_source':
            if target != original['source_text']: raise ValueError('Preserve source text changed: ' + uid)
        elif not target.strip(): raise ValueError('Missing translation: ' + uid)
        proof = binding.get('proofreading', {})
        validate_proof_record(proof,original,source_sha256=source['source_sha256'],target_text=target,
            prompt_sha256=artifacts['prompt']['sha256'],glossary_sha256=artifacts['glossary']['sha256'])
        if (proof.get('unit_id') != uid or proof.get('status') != 'passed' or proof.get('independent') is not True
                or not proof.get('context_id') or not proof.get('translation_context_id') or proof.get('context_id')==proof.get('translation_context_id')
                or not proof.get('evidence') or not proof.get('provenance')
                or proof.get('provenance') != original.get('provenance')
                or verified.get('evidence') != proof.get('evidence')
                or proof.get('source_sha256') != original['source_sha256'] or proof.get('target_sha256') != target_hash
                or proof.get('prompt_sha256') != artifacts['prompt']['sha256'] or proof.get('glossary_sha256') != artifacts['glossary']['sha256']
                or proof not in records):
            raise ValueError('Missing current independent proofreading: ' + uid)
    skeleton_target.pop('translation', None)
    if manifest.get('target_language') != book['metadata']['language'] or not re.fullmatch(r'[a-z]{2,3}(?:-[A-Za-z0-9]+)*',book['metadata']['language']):
        raise ValueError('Invalid translation target language binding')
    skeleton_target['metadata']['language']=source['metadata']['language']
    if manifest.get('editorial_labels') != book['labels']: raise ValueError('Editorial label binding mismatch')
    skeleton_target['labels']=source['labels']
    if skeleton_source != skeleton_target: raise ValueError('Translated book changed source structure')
    cache=_load(paths['cache']); cache_units={}
    for cf in cache.get('files',{}).values():
        if cf.get('extra',{}).get('ainiee_pdf',{}).get('document_id') != source['document_id']: continue
        meta=cf['extra']['ainiee_pdf']
        if book['labels']!=localized_labels(meta.get('target_language','zh'),source['labels'],meta.get('target_labels')):
            raise ValueError('Current editorial label configuration changed')
        for item in cf.get('items',[]):
            meta=item.get('extra',{}).get('ainiee_pdf',{}); uid=meta.get('unit_id')
            if uid in cache_units: raise ValueError('Duplicate disk cache unit')
            cache_units[uid]=item
    if set(cache_units) != set(source_units): raise ValueError('Current disk cache coverage mismatch')
    for uid,original in source_units.items():
        item=cache_units[uid]
        if item.get('source_text')!=original['source_text']: raise ValueError('Current disk cache source mismatch')
        target=value_at(book,original['path'])
        if original['translation_policy']!='preserve_source' and (item.get('translation_status') not in (1,2) or item.get('translated_text')!=target):
            raise ValueError('Current disk cache translation mismatch')

    decisions = _load(paths['decisions'])
    if decisions.get('schema') != 'pdf-decisions/1' or type(decisions.get('revision')) is not int: raise ValueError('Invalid decisions artifact')
    for ref in book.get('references', []):
        if ref['status'] in {'resolved', 'external'}: continue
        decision = next((d for d in decisions.get('decisions', []) if d.get('ref_id') == ref['ref_id']), {})
        if (decision.get('action') != 'text_only' or not isinstance(decision.get('source_revision'),int) or decision['source_revision'] > source['revision']
                or decision.get('reference_sha256') != content_digest(ref) or not decision.get('evidence') or not decision.get('approved_by')):
            raise ValueError('Unresolved semantic relationship: ' + ref['ref_id'])
        related={u['unit_id']:u['source_sha256'] for u in source['units'] if u['block_id']==ref['block_id']}
        if decision.get('source_units') != related: raise ValueError('Human decision is stale for related source text')


def compile_relationships(book, manifest, work):
    """Generate publication links from the verified registry in a transient copy."""
    result = deepcopy(book)
    decision_path=Path(manifest['artifacts']['decisions']['path'])
    decisions = _load(decision_path if decision_path.is_absolute() else Path(work)/decision_path)
    waived = {d['ref_id'] for d in decisions.get('decisions',[]) if d.get('action') == 'text_only'}
    entities = {e['entity_id']:e for e in result['entities']}
    for ref in result['references']:
        node = value_at(result,ref['path'])
        display = node.get('text', node.get('label',ref.get('display','')))
        if ref['ref_id'] in waived or ref['status'] == 'text_only':
            node.clear(); node.update(text=display)
        elif ref['status'] == 'external':
            node.clear(); node.update(text=display)
        elif ref['kind'] == 'note':
            node['note'] = ref['targets'][0]
        else:
            node.clear(); node.update(citation=list(ref['targets']), text=display,
                                     id=ref['ref_id'], relation_kind=ref['kind'],
                                     target_labels=[entities[t].get('label','') for t in ref['targets']])
    # Bookmark source titles remain evidence. Translated titles drive both TOCs.
    policy = result.get('structure_rules',{}).get('publication',{}).get('toc')
    if policy:
        by_id={c['id']:c for c in result['chapters']}
        by_id.update({b['id']:b for c in result['chapters'] for b in c['blocks']})
        for entry in policy['entries']:
            node=by_id[entry['target']]
            entry['display_title']=node.get('title') or ''.join(i.get('text','') for i in node.get('inline',[]))
            entry['title_evidence']='Bound translated text and current independent proofreading'
    return result


def persist_source(book,work):
    """Keep every source revision by content, then atomically advance the pointer."""
    from pdf_to_epub import save
    work=Path(work)
    validate_v2(book)
    if any(value_at(book,u['path']) != u['source_text'] for u in iter_units(book)):
        raise ValueError('Source snapshot does not match its source units')
    snapshots=work/'source-revisions'; snapshots.mkdir(exist_ok=True)
    path=snapshots/(str(book['revision'])+'-'+content_digest(book)+'.json')
    if not path.exists(): save(path,book)
    save(work/'book.source.json',book)
    return book


def revise_source(work,changes):
    """Evidence-bearing local OCR corrections; original extraction stays immutable."""
    from pdf_to_epub import save
    work=Path(work); original=_load(work/'book.source.json'); result=deepcopy(original)
    units={u['unit_id']:u for u in result['units']}; seen=set()
    for change in changes:
        if 'asset_id' in change:
            specs=[spec for spec in _assets(result) if spec['id']==change['asset_id']]
            if not specs or not change.get('evidence') or any(content_digest(spec)!=change.get('asset_sha256') for spec in specs):
                raise ValueError('Resource revision requires current spec fingerprint and PDF evidence')
            allowed={'bbox','page','path','sha256','tex','tex_verified','alt','width_em','height_em','baseline_em','includes_label','crop_geometry_verified'}
            if set(change.get('changes',{}))-allowed: raise ValueError('Unsupported resource revision field')
            for spec in specs: spec.update(change['changes'])
            continue
        if 'ref_id' in change:
            ref=next((r for r in result['references'] if r['ref_id']==change['ref_id']),None)
            if ref is None or change.get('reference_sha256') != content_digest(ref) or not change.get('evidence'):
                raise ValueError('Relationship correction requires current identity/hash and source evidence')
            ref.update(targets=change['targets'],status=change.get('status','resolved'),evidence=change['evidence'])
            node=value_at(result,ref['path'])
            if ref['kind']=='note': node['note']=ref['targets'][0]
            elif ref['kind']=='citation': node['citation']=ref['targets']
            else: node['link']=ref['targets'][0]
            continue
        uid=change['unit_id']
        if uid in seen or uid not in units: raise ValueError('Unknown/duplicate revised unit')
        seen.add(uid); unit=units[uid]
        if change.get('source_sha256') != unit['source_sha256'] or not change.get('evidence'):
            raise ValueError('Source correction requires current hash and PDF evidence')
        if not isinstance(change.get('text'),str) or not change['text'].strip(): raise ValueError('Correction cannot remove content')
        set_value(result,unit['path'],change['text'])
    result=prepare_translation_book(result,work)
    result['revision']=original['revision']+1
    record={'schema':'source-review-revision/1','previous_review_sha256':original['review_sha256'],
            'source_sha256':original['source_sha256'],'revision':result['revision'],'changes':changes,
            'asset_hashes':{spec['path']:spec['sha256'] for spec in _assets(result) if spec.get('path')},
            'structure_verification':'Current non-text structure/resources fingerprinted; independent context proofreading binds affected unit structure hashes.'}
    review_path='reviews/revision-'+str(result['revision'])+'-'+content_digest(record)+'.json'
    save(work/review_path,record)
    result['review_path']=review_path; result['review_sha256']=_file_hash(work/review_path)
    return persist_source(result,work)


def revise_structure(work,plan_path,id_mapping,evidence):
    """Re-normalize an evidence-bearing structure plan, retaining stable unit lineage."""
    from types import SimpleNamespace
    from pdf_to_epub import normalize,save
    work=Path(work); original=_load(work/'book.source.json')
    if not evidence or not isinstance(id_mapping,dict): raise ValueError('Structure revision needs evidence and an explicit ID mapping object')
    candidate=normalize(SimpleNamespace(work=work,plan=plan_path,minimum_structure=True))
    if candidate['source_sha256']!=original['source_sha256'] or candidate['raw_sha256']!=original['raw_sha256']:
        raise ValueError('Changed PDF/extraction requires a new source project')
    candidate.update(schema='epub-book/2',document_id=original['document_id'],revision=original['revision']+1,
                     units=deepcopy(original['units']))
    result=prepare_translation_book(candidate,work)
    old={u['unit_id']:u for u in original['units']};new={u['unit_id']:u for u in result['units']}
    destinations=set()
    for uid,values in id_mapping.items():
        values=[values] if isinstance(values,str) else values
        if uid not in old or not isinstance(values,list) or not values or len(values)!=len(set(values)) or any(v not in new for v in values):
            raise ValueError('Invalid structure revision ID mapping')
        destinations.update(values)
    removed,added=set(old)-set(new),set(new)-set(old)
    if removed and added and (not removed.issubset(id_mapping) or not added.issubset(destinations)):
        raise ValueError('Split/merge requires complete explicit ID mapping')
    for uid in set(old)&set(new):
        if old[uid]['source_sha256']==new[uid]['source_sha256']: continue
        owner=(new[uid]['chapter_id'],new[uid]['block_id'])
        relatives={v for v in added if (new[v]['chapter_id'],new[v]['block_id'])==owner}
        retired={v for v in removed if (old[v]['chapter_id'],old[v]['block_id'])==owner}
        if (relatives or retired) and (uid not in id_mapping or uid not in destinations or not relatives.issubset(destinations) or not retired.issubset(id_mapping)):
            raise ValueError('Split/merge requires mapping for retained and changed IDs')
    record={'schema':'source-structure-revision/1','revision':result['revision'],'previous_review_sha256':original['review_sha256'],
            'source_sha256':original['source_sha256'],'evidence':evidence,'id_mapping':id_mapping,'plan':_load(plan_path)}
    review_path='reviews/structure-'+str(result['revision'])+'-'+content_digest(record)+'.json'
    save(work/review_path,record)
    result.update(review_path=review_path,review_sha256=_file_hash(work/review_path),id_mapping=deepcopy(id_mapping))
    return persist_source(result,work)
