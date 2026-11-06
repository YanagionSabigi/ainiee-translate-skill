"""EPUB 2 compatibility navigation derived exclusively from the EPUB 3 TOC."""
import posixpath
from urllib.parse import quote, unquote, urlsplit, urlunsplit
import xml.etree.ElementTree as ET

X = 'http://www.w3.org/1999/xhtml'
EPUB = 'http://www.idpf.org/2007/ops'
NCX = 'http://www.daisy.org/z3986/2005/ncx/'


def make_ncx(navroot, identifier, title, language, nav_path='nav.xhtml', ncx_path='toc.ncx'):
    """Copy the TOC tree and resolve links relative to the NCX, never scan body links."""
    navs = [e for e in navroot.iter('{'+X+'}nav')
            if 'toc' in e.get('{'+EPUB+'}type', '').split()]
    if len(navs) != 1:
        raise ValueError('Exactly one EPUB navigation TOC is required')
    listing = navs[0].find('{'+X+'}ol')
    if listing is None:
        raise ValueError('Navigation TOC needs an ordered list')
    def node(tag, parent, text=None, **attrs):
        result = ET.SubElement(parent, '{'+NCX+'}'+tag, attrs)
        result.text = text
        return result
    root = ET.Element('{'+NCX+'}ncx', {'version':'2005-1',
                      '{http://www.w3.org/XML/1998/namespace}lang':language})
    head = node('head', root)
    node('meta', head, name='dtb:uid', content=identifier)
    depth_meta = node('meta', head, name='dtb:depth', content='1')
    node('meta', head, name='dtb:totalPageCount', content='0')
    node('meta', head, name='dtb:maxPageNumber', content='0')
    node('text', node('docTitle', root), title)
    navmap = node('navMap', root)
    count = 0
    max_depth = 1
    def visit(ol, parent, depth):
        nonlocal count, max_depth
        for li in ol.findall('{'+X+'}li'):
            link = li.find('{'+X+'}a')
            if link is None or not link.get('href'):
                raise ValueError('NCX compatibility requires linked TOC entries')
            url = urlsplit(link.get('href'))
            if url.scheme or url.netloc or url.query:
                raise ValueError('NCX navigation targets must be local publication resources')
            target = posixpath.normpath(posixpath.join(posixpath.dirname(nav_path), unquote(url.path))) if url.path else nav_path
            href = posixpath.relpath(target, posixpath.dirname(ncx_path) or '.')
            href = urlunsplit(('', '', quote(href, safe='/'), '', url.fragment))
            count += 1
            max_depth = max(max_depth, depth)
            point = node('navPoint', parent, id=f'nav-{count}', playOrder=str(count))
            node('text', node('navLabel', point), ''.join(link.itertext()).strip())
            node('content', point, src=href)
            nested = li.find('{'+X+'}ol')
            if nested is not None:
                visit(nested, point, depth+1)
    visit(listing, navmap, 1)
    if not count:
        raise ValueError('Navigation TOC must not be empty')
    depth_meta.set('content', str(max_depth))
    ET.register_namespace('', NCX)
    result = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    ET.register_namespace('', X)
    return result
