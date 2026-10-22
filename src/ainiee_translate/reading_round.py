"""Immutable reading editions and round-scoped, atomically saved state."""
from contextlib import contextmanager
from datetime import datetime, timezone
import html
import json
from pathlib import Path
import posixpath
import re
import shutil
import tempfile
import unicodedata
from uuid import uuid4
import zipfile

from bs4 import BeautifulSoup
from lxml import etree
from .artifact_io import sha256, text_sha256, safe_relative, write_json
from . import cache_io


def now():
    return datetime.now(timezone.utc).isoformat()


def revision():
    return uuid4().hex


def read(path):
    return json.loads(Path(path).read_text(encoding='utf8'))


def record(schema, r, **values):
    return dict(schema=schema, created_at=now(), project_id=r['project_id'], round_id=r['round_id'], **values)


def child(root, name):
    """Resolve relative artifact names without following a symlink outside root."""
    root = Path(root).resolve()
    path = (root / safe_relative(str(name))).resolve()
    if not path.is_relative_to(root):
        raise ValueError('Artifact escapes round directory')
    return path


def immutable(root, folder, name, value):
    path = child(root, f'{folder}/{safe_relative(name)}.json')
    if path.exists():
        raise FileExistsError(path)
    write_json(path, value)
    return path


def load_round(round_dir):
    return read(child(round_dir, 'round.json'))


def load_segments(round_dir):
    return read(child(round_dir, 'edition/segments.json'))['segments']


def load_issues(round_dir):
    return read(child(round_dir, 'issues.json'))


@contextmanager
def round_lock(round_dir):
    with cache_io.locked(str(Path(round_dir) / 'round.json')):
        yield


def save_state(round_dir, r, issues=None):
    r['revision'] = revision()
    if issues is not None:
        write_json(child(round_dir, 'issues.json'), issues)
    write_json(child(round_dir, 'round.json'), r)


def plain(text):
    return BeautifulSoup(text, 'html.parser').get_text()


def normalized(text):
    return re.sub(r'\s+', ' ', unicodedata.normalize('NFC', plain(text))).strip()


def epub_blocks(path):
    """Read package/spine order, never ZIP iteration order or a remote chapter UID."""
    parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
    with zipfile.ZipFile(path) as z:
        names = [safe_relative(i.filename) for i in z.infolist() if not i.is_dir()]
        if len(names) != len(set(names)):
            raise ValueError('Duplicate EPUB member')
        container = etree.fromstring(z.read('META-INF/container.xml'), parser)
        packages = container.xpath('//*[local-name()="rootfile"]/@full-path')
        if len(packages) != 1:
            raise ValueError('Expected one EPUB package')
        package_path = safe_relative(packages[0])
        package = etree.fromstring(z.read(package_path), parser)
        manifest = {i.get('id'): i for i in package.xpath('//*[local-name()="manifest"]/*')}
        result = []
        for spine_index, iid in enumerate(package.xpath('//*[local-name()="spine"]/*/@idref')):
            item = manifest[iid]
            href = safe_relative(posixpath.normpath(posixpath.join(posixpath.dirname(package_path), item.get('href'))))
            # Imported legacy EPUBs can contain HTML-style void elements. Match
            # visible reader content; formal XML/EPUB validity is a separate gate.
            soup = BeautifulSoup(z.read(href), 'html.parser', from_encoding='utf8')
            body = soup.find('body')
            if body is None:
                raise ValueError('Missing EPUB body')
            for unsafe in body.find_all(['script', 'style']):
                unsafe.decompose()
            block_tags=['p','h1','h2','h3','h4','h5','h6','li','td','blockquote','figcaption','caption','pre','div','aside','dt','dd']
            blocks = body.find_all(block_tags)
            # Parent list/table/quote elements must not duplicate child paragraphs.
            blocks = [b for b in blocks if not b.find(block_tags)]
            for block_index, node in enumerate(blocks):
                result.append(dict(item_id=iid, href=href, spine_index=spine_index,
                                   block_index=block_index, element_id=node.get('id'),
                                   chapter_title=(body.find(['h1','h2']).get_text() if body.find(['h1','h2']) else ''),
                                   visible_text=node.get_text()))
        return result


def current_items(round_dir, cache_path):
    """Use composite book/item identity; reject a reparse's unrelated text_index."""
    r = load_round(round_dir)
    p = cache_io.load_cache(cache_path)
    if p.project_id != r['project_id'] or r['storage_path'] not in p.files:
        raise ValueError('Cache project/book differs from reading round')
    cf = p.files[r['storage_path']]
    idx = {it.text_index: it for it in cf.items}
    if len(idx) != len(cf.items):
        raise ValueError('Duplicate text_index in selected book')
    return p, idx


def item_identity(item):
    """Location identity survives language edits but distinguishes re-parsed units."""
    from .artifact_io import digest
    meta=item.extra.get('ainiee_pdf',{})
    return digest(dict(item_id=item.extra.get('item_id'),original_html=item.extra.get('original_html'),
                       document_id=meta.get('document_id'),unit_id=meta.get('unit_id'),
                       slot_path=meta.get('slot_path'),source_refs=meta.get('source_refs'),
                       translation_policy=meta.get('translation_policy')))


def freeze_round(cache_path, epub_path, source_path, *, storage_path, round_dir, glossary_path, prompt_path,scope_path=None):
    with cache_io.locked(str(cache_path)):
        return _freeze_round(cache_path,epub_path,source_path,storage_path=storage_path,round_dir=round_dir,
                             glossary_path=glossary_path,prompt_path=prompt_path,scope_path=scope_path)


def _freeze_round(cache_path, epub_path, source_path, *, storage_path, round_dir, glossary_path, prompt_path,scope_path=None):
    cache_path, epub_path, source_path = map(Path, (cache_path, epub_path, source_path))
    round_dir = Path(round_dir)
    safe_relative(storage_path.replace('\\', '/'))
    if round_dir.exists():
        raise FileExistsError('Reading round already exists')
    project = cache_io.load_cache(cache_path)
    if not project.project_id or storage_path not in project.files:
        raise ValueError('Explicit cache project and storage_path required')
    cf = project.files[storage_path]
    scope=read(scope_path) if scope_path else None
    if scope and (scope.get('schema')!='reading-scope/1' or scope.get('cache_sha256')!=sha256(cache_path)
                  or scope.get('epub_sha256')!=sha256(epub_path) or not scope.get('evidence_reference')):
        raise ValueError('Reading scope must bind the exact cache/EPUB and existing project policy evidence')
    blocks = epub_blocks(epub_path)
    block_texts=[normalized(b['visible_text']) for b in blocks]
    source_blocks = epub_blocks(source_path) if source_path.suffix.lower()=='.epub' else []
    segments = []
    for it in cf.items:
        # Follow the existing scope/status policy for excluded units.
        if not (it.source_text or '').strip() or it.translation_status in (7, 8):
            continue
        if not (it.translated_text or '').strip() or it.translation_status not in (1,2):
            raise ValueError(f'Missing translation: {it.text_index}')
        target = normalized(it.translated_text)
        meta = it.extra.get('ainiee_pdf', {})
        matches=[]
        for b,visible in zip(blocks,block_texts):
            if not meta:
                if visible==target: matches.append(dict(b,text_start=0,text_end=len(visible)))
                continue
            offset=0
            while (offset:=visible.find(target,offset))>=0:
                matches.append(dict(b,text_start=offset,text_end=offset+len(target)))
                offset+=max(1,len(target))
        mapping_status='mapped'
        if not matches and meta and meta.get('unit_id') in (scope or {}).get('omitted_units',{}):
            if not scope['omitted_units'][meta['unit_id']]: raise ValueError('Omitted unit requires policy explanation')
            mapping_status='outside_reading_edition'
        elif not matches and meta and (meta.get('slot_path') or [None])[0]=='metadata':
            # Metadata is frozen and verified against the package, not invented as
            # a selectable body paragraph (covers can be raster images).
            field=(meta['slot_path']+[None])[1]
            with zipfile.ZipFile(epub_path) as z:
                package=next(n for n in z.namelist() if n.endswith('.opf'))
                soup=BeautifulSoup(z.read(package),'xml')
                values=[n.get_text() for n in soup.find_all(field)] if field else []
            if target not in [normalized(v) for v in values]: raise ValueError('EPUB metadata differs from cache')
            mapping_status='package_metadata'
        elif not matches:
            raise ValueError(f'EPUB does not contain current translation: {it.text_index}')
        if source_blocks and not any(normalized(b['visible_text']) == normalized(it.source_text)
                                     and (not it.extra.get('item_id') or b['item_id']==it.extra['item_id']) for b in source_blocks):
            raise ValueError('Source EPUB differs from cache')
        segment = dict(segment_id=f'{storage_path}#{it.text_index}', text_index=it.text_index,
                       storage_path=storage_path, source_text=it.source_text, target_text=it.translated_text,
                       source_text_sha256=text_sha256(it.source_text), target_text_sha256=text_sha256(it.translated_text),
                       locators=matches, item_id=it.extra.get('item_id'), original_html=it.extra.get('original_html'),
                       item_identity=item_identity(it),mapping_status=mapping_status)
        if meta:
            segment.update(document_id=meta.get('document_id', cf.extra.get('ainiee_pdf', {}).get('document_id')),
                           unit_id=meta.get('unit_id'), provenance=meta.get('provenance',meta.get('source_refs',[])))
        segments.append(segment)
    if not segments or not any(s['locators'] for s in segments) or len({s['segment_id'] for s in segments}) != len(segments):
        raise ValueError('No uniquely identified translated segments')
    round_dir.parent.mkdir(parents=True, exist_ok=True)
    sequence = round_dir.parent / 'round-sequence.json'
    with cache_io.locked(str(sequence)):
        seq = read(sequence) if sequence.exists() else {}
        number = seq.get(project.project_id, 0) + 1
        rid = f'R{number:04d}'
        r = dict(schema='reading-round/1', created_at=now(), project_id=project.project_id, round_id=rid,
                 revision=revision(), edition_id=sha256(epub_path), storage_path=storage_path,
                 book_id=None, style_profile=None, reading_completion=None,
                 last_complete_snapshot_id=None, latest_snapshot_id=None, next_issue_number=1)
        stage = Path(tempfile.mkdtemp(prefix='.freeze-', dir=round_dir.parent))
        try:
            edition = stage / 'edition'; edition.mkdir()
            for src, dest in [(epub_path, 'reading.epub'),(cache_path,'cache.frozen.json'),
                              (Path(glossary_path),'glossary.locked.json'), (Path(prompt_path),'prompt.txt'),
                              (source_path, 'source' + source_path.suffix.lower())]:
                shutil.copyfile(src, edition / dest)
            manifest = record('reading-edition/1', r, epub_sha256=sha256(epub_path), cache_sha256=sha256(cache_path),
                              source_sha256=sha256(source_path), glossary_sha256=sha256(glossary_path),
                              prompt_sha256=sha256(prompt_path), source_path=str(source_path.resolve()),
                              frozen_source='source'+source_path.suffix.lower(), spine=blocks)
            write_json(edition/'source-manifest.json', manifest)
            if scope: write_json(edition/'reading-scope.json',scope)
            write_json(edition/'segments.json', record('reading-segments/1', r, segments=segments))
            write_json(stage/'round.json', r)
            write_json(stage/'issues.json', record('reading-issues/1', r, issues=[]))
            stage.rename(round_dir)
            seq[project.project_id] = number; write_json(sequence, seq)
        finally:
            if stage.exists():
                shutil.rmtree(stage)
    return r
