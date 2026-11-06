#!/usr/bin/env python3
"""Create a separate compatibility EPUB without changing note targets or text."""
import argparse
import hashlib
import json
from pathlib import Path
import posixpath
import re
import sys
import uuid
import zipfile
from urllib.parse import unquote
import xml.etree.ElementTree as ET
from epub_navigation import make_ncx, X

O = '{http://www.idpf.org/2007/opf}'
D = '{http://purl.org/dc/elements/1.1/}'
C = '{urn:oasis:names:tc:opendocument:xmlns:container}'


def repair(source, output, *, plain_callouts=False, test_label=None, split_at=None):
    source, output = Path(source).resolve(), Path(output).resolve()
    if source == output or output.exists():
        raise ValueError('Choose a new output file; original and previous versions are preserved')
    if output.suffix.lower() != '.epub':
        raise ValueError('Output must have the .epub extension')
    with zipfile.ZipFile(source) as z:
        original = {n:z.read(n) for n in z.namelist()}
    data = dict(original)
    container = ET.fromstring(data['META-INF/container.xml'])
    rootfiles = container.findall(C+'rootfiles/'+C+'rootfile')
    if len(rootfiles) != 1:
        raise ValueError('Only single-rendition EPUBs are supported')
    package_path = rootfiles[0].get('full-path')
    base = posixpath.dirname(package_path)
    splits = []
    if split_at:
        from epub_split import split_chapters
        splits = split_chapters(data, package_path, split_at)
    baseline = dict(data)
    package = ET.fromstring(data[package_path])
    manifest = package.find(O+'manifest')
    spine = package.find(O+'spine')
    metadata = package.find(O+'metadata')
    navs = [i for i in manifest if 'nav' in i.get('properties', '').split()]
    if len(navs) != 1:
        raise ValueError('Exactly one EPUB 3 navigation resource is required')
    nav_path = posixpath.normpath(posixpath.join(base, unquote(navs[0].get('href'))))
    identifier = metadata.find(D+'identifier[@id="'+package.get('unique-identifier')+'"]')
    title = metadata.find(D+'title')
    language = metadata.find(D+'language')
    if identifier is None or title is None or language is None:
        raise ValueError('Package identifier, title and language are required')
    if test_label:
        if 'META-INF/encryption.xml' in data:
            encryption = ET.fromstring(data['META-INF/encryption.xml'])
            if any(e.tag.split('}')[-1] == 'EncryptionMethod' for e in encryption.iter()):
                raise ValueError('Cannot change test identity with encrypted or obfuscated resources; omit --test-label')
        title.text = (title.text or '')+'（'+test_label+'）'
        identifier.text = 'urn:uuid:'+str(uuid.uuid4())
    ncxs = [i for i in manifest if i.get('media-type') == 'application/x-dtbncx+xml']
    if len(ncxs) > 1:
        raise ValueError('Multiple NCX resources require manual review')
    if ncxs:
        item = ncxs[0]
        href = item.get('href')
    else:
        href = 'toc.ncx'
        if posixpath.join(base, href) in data:
            raise ValueError('Unmanifested toc.ncx already exists')
        ids = {i.get('id') for i in manifest}
        ident = 'compat-ncx'
        while ident in ids: ident += '-new'
        item = ET.SubElement(manifest, O+'item', {'id':ident, 'href':href,
                             'media-type':'application/x-dtbncx+xml'})
    ncx_path = posixpath.normpath(posixpath.join(base, unquote(href)))
    data[ncx_path] = make_ncx(ET.fromstring(data[nav_path]), identifier.text, title.text,
                            language.text, nav_path, ncx_path)
    spine.set('toc', item.get('id'))
    data[package_path] = ET.tostring(package, encoding='utf-8', xml_declaration=True)
    callouts = 0
    if plain_callouts:
        for name in list(data):
            if not name.endswith(('.xhtml', '.html')): continue
            root = ET.fromstring(data[name])
            changed = False
            for div in root.iter('{'+X+'}div'):
                classes = div.get('class', '').split()
                kept = [c for c in classes if not re.fullmatch(r'bgc_[0-9a-fA-F]{6}', c)]
                if kept == classes: continue
                if kept: div.set('class', ' '.join(kept))
                else: div.attrib.pop('class', None)
                changed = True
                callouts += 1
            if changed:
                data[name] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    # Nothing is extracted to disk. All resource bytes outside this small allowlist survive.
    for name in data:
        if name.endswith(('.xhtml', '.html')):
            before, after = ET.fromstring(baseline[name]), ET.fromstring(data[name])
            if list(before.itertext()) != list(after.itertext()):
                raise ValueError('Readable content changed: '+name)
            for old, new in zip(before.iter(), after.iter()):
                for attr in ('id', 'href', 'src'):
                    if old.get(attr) != new.get(attr):
                        raise ValueError('Content target or asset reference changed: '+name)
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open('xb') as stream, zipfile.ZipFile(stream, 'w', zipfile.ZIP_DEFLATED) as z:
        z.writestr('mimetype', data.pop('mimetype'), compress_type=zipfile.ZIP_STORED)
        for name, payload in data.items(): z.writestr(name, payload)
    changed = [n for n, payload in data.items() if original.get(n) != payload]
    return {'source_sha256':hashlib.sha256(source.read_bytes()).hexdigest(),
            'output_sha256':hashlib.sha256(output.read_bytes()).hexdigest(),
            'output':str(output), 'changed_resources':changed, 'plain_callouts':callouts,
            'test_label':test_label, 'splits':splits, 'weread_import_verified':False}


def main():
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, 'reconfigure'): stream.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source')
    parser.add_argument('output')
    parser.add_argument('--plain-callouts', action='store_true',
                        help='Remove only bgc_HEX classes from div callouts; keep text, layout and table colors')
    parser.add_argument('--test-label', help='Mark test copy title and use a fresh identifier to avoid import caching')
    parser.add_argument('--split-at', action='append', help='Explicit existing TOC heading, as ZIP/path.xhtml#id; move whole blocks and preserve links')
    parser.add_argument('--report', help='Write a local JSON change report')
    args = parser.parse_args()
    try:
        report = repair(args.source, args.output, plain_callouts=args.plain_callouts, test_label=args.test_label, split_at=args.split_at)
    except (ValueError, KeyError, ET.ParseError, zipfile.BadZipFile) as exc:
        parser.exit(1, str(exc)+'\n')
    if args.report:
        Path(args.report).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
