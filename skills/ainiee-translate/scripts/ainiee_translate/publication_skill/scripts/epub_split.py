"""Explicit, reviewed section splits for importers that divide long XHTML arbitrarily."""
from copy import deepcopy
import posixpath
import re
from urllib.parse import quote, unquote, urlsplit, urlunsplit
import xml.etree.ElementTree as ET
from epub_navigation import X, EPUB

O = '{http://www.idpf.org/2007/opf}'


def split_chapters(data, package_path, targets):
    """Move complete sibling blocks at TOC headings; preserve all IDs and rewrite links."""
    base = posixpath.dirname(package_path)
    package = ET.fromstring(data[package_path])
    manifest, spine = package.find(O+'manifest'), package.find(O+'spine')
    if any(i.get('media-overlay') or i.get('media-type') == 'application/smil+xml' for i in manifest):
        raise ValueError('Explicit splitting does not support media overlays')
    roots = {n:ET.fromstring(payload) for n, payload in data.items() if n.endswith('.xhtml')}
    origins = {n:n for n in roots}
    nav_items = [i for i in manifest if 'nav' in i.get('properties', '').split()]
    if len(nav_items) != 1: raise ValueError('Splitting requires one reviewed navigation document')
    nav_path = posixpath.normpath(posixpath.join(base, unquote(nav_items[0].get('href'))))
    reviewed = {}
    toc = [n for n in roots[nav_path].iter('{'+X+'}nav') if 'toc' in n.get('{'+EPUB+'}type','').split()]
    if len(toc) != 1: raise ValueError('Splitting requires one EPUB navigation TOC')
    for a in toc[0].iter('{'+X+'}a'):
        url = urlsplit(a.get('href', ''))
        dest = posixpath.normpath(posixpath.join(posixpath.dirname(nav_path), unquote(url.path)))
        reviewed[(dest, unquote(url.fragment))] = ''.join(a.itertext()).strip()
    used_files = set()
    reports = []
    for target in targets:
        url = urlsplit(target)
        name, anchor = unquote(url.path), unquote(url.fragment)
        if name in used_files:
            raise ValueError('Only one explicit split per original file is supported')
        used_files.add(name)
        if url.scheme or url.netloc or url.query or (name, anchor) not in reviewed:
            raise ValueError('Split target must be an existing local TOC heading: '+target)
        root = roots[name]
        body = root.find('{'+X+'}body')
        content = body
        if len(body) == 1 and body[0].tag == '{'+X+'}div' and not body[0].attrib:
            content = body[0]
        heading = content.find('*[@id="'+anchor+'"]')
        if heading is None or not re.fullmatch('{'+X+'}h[1-6]', heading.tag):
            raise ValueError('Split heading must be a complete direct block in body or its anonymous div')
        index = list(content).index(heading)
        if index == 0: raise ValueError('Split must leave content in the first file')
        new_name = posixpath.splitext(name)[0]+'-part2.xhtml'
        if new_name in data: raise ValueError('Split output resource already exists: '+new_name)
        items = [i for i in manifest if posixpath.normpath(posixpath.join(base, unquote(i.get('href','')))) == name]
        if len(items) != 1: raise ValueError('Split source must be uniquely manifested')
        source_item = items[0]
        refs = [i for i in spine if i.get('idref') == source_item.get('id')]
        if len(refs) != 1: raise ValueError('Split source must occur exactly once in spine')
        new_root = deepcopy(root)
        new_body = new_root.find('{'+X+'}body')
        new_body.attrib.pop('id', None)
        new_content = new_body[0] if content is not body else new_body
        for child in list(new_content): new_content.remove(child)
        new_content.text = None
        new_content.tail = None
        if content is not body: new_body.text = None
        for child in list(content)[index:]:
            content.remove(child)
            new_content.append(child)
        title = new_root.find('{'+X+'}head/{'+X+'}title')
        if title is None: raise ValueError('Split source needs a title')
        title.text = reviewed[(name, anchor)]
        roots[new_name] = new_root
        origins[new_name] = name
        ids = {i.get('id') for i in manifest}
        item_id = source_item.get('id')+'-part2'
        while item_id in ids: item_id += '-new'
        attrs = dict(source_item.attrib, id=item_id, href=quote(posixpath.relpath(new_name, base or '.'), safe='/'))
        ET.SubElement(manifest, O+'item', attrs)
        ref = ET.Element(O+'itemref', dict(refs[0].attrib, idref=item_id))
        spine.insert(list(spine).index(refs[0])+1, ref)
        reports.append({'source':name, 'continuation':new_name, 'heading':anchor,
                        'title':title.text, 'original_bytes':len(data[name])})
    locations = {}
    for name, root in roots.items():
        for node in root.iter():
            if node.get('id'):
                key = (origins[name], node.get('id'))
                if key in locations and node.tag not in ('{'+X+'}style',):
                    raise ValueError('Split duplicated an existing target: '+str(key))
                locations[key] = name
    link_roots = dict(roots, **{package_path:package})
    for name, root in link_roots.items():
        for node in root.iter():
            for attr in ('href', 'src'):
                if not node.get(attr): continue
                url = urlsplit(node.get(attr))
                if url.scheme or url.netloc or not url.fragment: continue
                origin = origins.get(name, name)
                path = posixpath.normpath(posixpath.join(posixpath.dirname(origin), unquote(url.path))) if url.path else origin
                dest = locations.get((path, unquote(url.fragment)))
                physical = posixpath.normpath(posixpath.join(posixpath.dirname(name), unquote(url.path))) if url.path else name
                if dest is None or dest == physical: continue
                href = quote(posixpath.relpath(dest, posixpath.dirname(name) or '.'), safe='/')
                node.set(attr, urlunsplit(('', '', href, url.query, url.fragment)))
    ET.register_namespace('', X)
    ET.register_namespace('epub', EPUB)
    for name, root in roots.items():
        # Preserve unrelated XHTML byte for byte.
        if name not in data or ET.tostring(ET.fromstring(data[name])) != ET.tostring(root):
            data[name] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    data[package_path] = ET.tostring(package, encoding='utf-8', xml_declaration=True)
    for report in reports:
        report['part_bytes'] = [len(data[report['source']]), len(data[report['continuation']])]
    return reports
