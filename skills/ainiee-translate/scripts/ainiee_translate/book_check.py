"""Offline EPUB structure checks and independently reported EPUBCheck status."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import posixpath
import re
import shutil
import subprocess
from urllib.parse import unquote, urlsplit
import zipfile

from lxml import etree

from .mineru_local import safe_relative, write_json


def _structure(path: Path) -> list[str]:
    issues = []
    try:
        with zipfile.ZipFile(path) as z:
            infos = z.infolist()
            names = [safe_relative(info.orig_filename) for info in infos]
            if len({n.casefold() for n in names}) != len(names):
                raise ValueError('Duplicate ZIP member or case collision')
            if not infos or names[0] != 'mimetype' or infos[0].compress_type != zipfile.ZIP_STORED or z.read('mimetype') != b'application/epub+zip':
                raise ValueError('Invalid EPUB mimetype member/order/compression')
            members = set(names)
            parser = etree.XMLParser(resolve_entities=False, no_network=True, load_dtd=False)
            roots, ids = {}, {}
            for name in names:
                if name.endswith(('.xml', '.opf', '.xhtml', '.svg')):
                    root = etree.fromstring(z.read(name), parser)
                    if any(isinstance(node, etree._Entity) for node in root.iter()):
                        raise ValueError('Unresolved XML entity')
                    roots[name] = root
                    values = root.xpath('//@id')
                    if len(values) != len(set(values)):
                        issues.append(f'Duplicate XML ID: {name}')
                    ids[name] = set(values)
            container = roots.get('META-INF/container.xml')
            if container is None:
                raise ValueError('Missing EPUB container')
            rootfiles = container.xpath('//*[local-name()="rootfile"]/@full-path')
            if len(rootfiles) != 1:
                raise ValueError('EPUB requires exactly one package document')
            package_path = safe_relative(rootfiles[0]); package = roots[package_path]
            if package.get('version') != '3.0': issues.append('Package is not EPUB 3')
            ns = {'o': 'http://www.idpf.org/2007/opf', 'dc': 'http://purl.org/dc/elements/1.1/'}
            for name in ('title', 'language', 'identifier'):
                if not package.xpath(f'//dc:{name}[normalize-space()]', namespaces=ns):
                    issues.append(f'Missing metadata: {name}')
            identifier = package.get('unique-identifier')
            if not identifier or identifier not in ids[package_path]: issues.append('Invalid unique-identifier')
            if not package.xpath('//o:meta[@property="dcterms:modified"]', namespaces=ns): issues.append('Missing modified timestamp')
            item_map, resource_files, nav = {}, set(), []
            def resolve(base, url, *, external_link=False):
                parts = urlsplit(url)
                if parts.scheme or parts.netloc:
                    if external_link and parts.scheme in ('http', 'https', 'mailto'):
                        return None, None
                    raise ValueError(f'Nonlocal/unsafe resource URL in {base}')
                raw = unquote(parts.path)
                if raw.startswith('/') or '\\' in raw or ':' in raw or parts.query:
                    raise ValueError(f'Absolute/unsafe path in {base}')
                target = posixpath.normpath(posixpath.join(posixpath.dirname(base), raw)) if raw else base
                safe_relative(target)
                if target not in members: raise ValueError(f'Broken resource link: {base} -> {target}')
                fragment = unquote(parts.fragment)
                if fragment and fragment not in ids.get(target, set()):
                    raise ValueError(f'Broken fragment: {base} -> {target}#{fragment}')
                return target, fragment
            for item in package.xpath('//o:manifest/o:item', namespaces=ns):
                iid = item.get('id')
                if not iid or iid in item_map: raise ValueError('Duplicate/missing manifest ID')
                target, _ = resolve(package_path, item.get('href', ''))
                if target in resource_files: raise ValueError('Duplicate manifest resource')
                resource_files.add(target); item_map[iid] = item
                if not item.get('media-type'): issues.append('Missing resource media type')
                if 'nav' in item.get('properties', '').split(): nav.append(target)
                if target and target.endswith('.xhtml'):
                    if roots[target].xpath('//*[local-name()="math"]') and 'mathml' not in item.get('properties', '').split():
                        issues.append('Missing mathml manifest property')
            if len(nav) != 1 or not roots.get(nav[0], etree.Element('empty')).xpath('//*[local-name()="nav" and @*[local-name()="type"]="toc"]'):
                issues.append('Missing or invalid EPUB navigation')
            spine = package.xpath('//o:spine/o:itemref/@idref', namespaces=ns)
            if not spine or any(i not in item_map for i in spine) or len(spine) != len(set(spine)):
                issues.append('Invalid or duplicate spine reference')
            for name, root in roots.items():
                for node in root.iter():
                    local = etree.QName(node).localname
                    for attr, value in node.attrib.items():
                        if etree.QName(attr).localname in ('href', 'src'):
                            target, _ = resolve(name, value, external_link=local == 'a')
                            if name.endswith(('.xhtml', '.svg')) and target and target not in resource_files:
                                issues.append(f'Linked resource missing from manifest: {target}')
                    if node.get('style') and ('url(' in node.get('style') or '@import' in node.get('style')):
                        raise ValueError('Unvalidated inline CSS resource')
            for name in names:
                if name.endswith('.css'):
                    css = z.read(name).decode('utf8')
                    if '@import' in css: raise ValueError('CSS imports are not permitted')
                    for url in re.findall(r'url\([\s\'"]*([^\)\'"\s]+)', css): resolve(name, url)
            expected = resource_files | {'mimetype', 'META-INF/container.xml', package_path}
            if members != expected: issues.append('Archive contains undeclared publication members')
    except (OSError, ValueError, KeyError, etree.XMLSyntaxError, zipfile.BadZipFile) as exc:
        issues.append(str(exc))
    return issues


def check_epub(path: Path, *, epubcheck_jar: Path | None = None) -> dict:
    path = Path(path)
    issues = _structure(path)
    result = {'structure': {'status': 'failed' if issues else 'passed', 'issues': issues},
              'epubcheck': {'status': 'unavailable'}}
    jar = epubcheck_jar or (Path(os.environ['EPUBCHECK_JAR']) if os.environ.get('EPUBCHECK_JAR') else None)
    java = shutil.which('java')
    if jar is None or not Path(jar).is_file() or not java:
        result['epubcheck']['reason'] = 'Provide EPUBCHECK_JAR and a Java runtime to run official EPUBCheck'
        return result
    report = path.with_suffix('.epubcheck.json')
    try:
        command = [java, '-jar', str(jar), str(path), '--json', str(report)]
        proc = subprocess.run(command, shell=False, capture_output=True, text=True, encoding='utf8', errors='replace', timeout=300)
        log = path.with_suffix('.epubcheck.log'); log.write_text(proc.stdout + '\n' + proc.stderr, encoding='utf8')
        result['epubcheck'] = dict(status='passed' if proc.returncode == 0 else 'failed',
                                   returncode=proc.returncode, report=str(report), log=str(log))
    except (OSError, subprocess.SubprocessError) as exc:
        result['epubcheck'] = dict(status='failed', error=type(exc).__name__)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description='Check EPUB structure and optionally run official EPUBCheck')
    parser.add_argument('epub', type=Path)
    parser.add_argument('--epubcheck-jar', type=Path)
    parser.add_argument('--report', type=Path)
    args = parser.parse_args(argv)
    result = check_epub(args.epub, epubcheck_jar=args.epubcheck_jar)
    if args.report: write_json(args.report, result)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 1 if any(r['status'] == 'failed' for r in result.values()) else 0


if __name__ == '__main__':
    raise SystemExit(main())
