"""Deterministic EPUB packaging and offline structural validation."""
from __future__ import annotations
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import math, posixpath, re, shutil, tempfile, uuid, zipfile
from urllib.parse import unquote, urlsplit
import xml.etree.ElementTree as ET
from pdf_to_epub import SKILL, load, save, sha, digest, run, pdf_module, rect_check, valid_id
from epub_publication import apply_publication

X='http://www.w3.org/1999/xhtml'; EPUB='http://www.idpf.org/2007/ops'
OPF='http://www.idpf.org/2007/opf'; DC='http://purl.org/dc/elements/1.1/'
def element(tag,parent=None,text=None,**attrs):
    e=ET.Element('{'+X+'}'+tag,attrs) if parent is None else ET.SubElement(parent,'{'+X+'}'+tag,attrs)
    if text is not None: e.text=str(text)
    return e
def add_text(parent,text):
    if len(parent): parent[-1].tail=(parent[-1].tail or '')+text
    else: parent.text=(parent.text or '')+text
def xml_bytes(root):
    ET.register_namespace('',X); ET.register_namespace('epub',EPUB)
    return ET.tostring(root,encoding='utf-8',xml_declaration=True)
def xhtml(title,lang):
    root=element('html',lang=lang); root.set('{http://www.w3.org/XML/1998/namespace}lang',lang)
    head=element('head',root); element('title',head,title); element('link',head,rel='stylesheet',href='book.css',type='text/css')
    return root,element('body',root)
def crop_asset(doc,spec,dest):
    if spec.get('crop_geometry_verified') is False:
        raise ValueError(f'Asset {spec["id"]}: crop geometry is unverified and no usable returned image is available')
    page=doc[spec['page']-1]; rect=rect_check(page,spec['bbox'])
    if rect.get_area()>.8*page.rect.get_area(): raise ValueError('Use precise figure/formula/table crops; whole-page body facsimiles are not reflowable conversion')
    page.get_pixmap(clip=rect,dpi=spec.get('dpi',300),alpha=False).save(dest)
def iter_assets(node):
    """Visit supported content containers without traversing asset metadata."""
    if isinstance(node,list):
        for child in node: yield from iter_assets(child)
    elif isinstance(node,dict):
        if node.get('asset'): yield node['asset']
        for field in ('inline','rows','items'):
            if field in node: yield from iter_assets(node[field])
def local_asset_path(spec,work,issues):
    """Validate a returned resource before choosing TeX or image fallback."""
    expected=spec.get('sha256')
    if expected is not None and (not isinstance(expected,str) or not re.fullmatch(r'[0-9a-fA-F]{64}',expected)):
        raise ValueError(f'Asset {spec["id"]}: sha256 must be 64 hexadecimal characters')
    if not spec.get('path'):
        if expected is not None: raise ValueError(f'Asset {spec["id"]}: sha256 requires a returned resource path')
        return None
    src=(work/spec['path']).resolve()
    if not src.is_relative_to(work.resolve()): raise ValueError('Asset path must stay within work directory')
    if src.suffix.lower() not in {'.png','.jpg','.jpeg','.svg'}: raise ValueError('Asset must be PNG/JPEG/SVG')
    if not src.is_file():
        if expected is not None: raise ValueError(f'Asset {spec["id"]}: hashed returned resource is missing')
        issues.append(f'Asset {spec["id"]}: returned image is missing; source fallback required.')
        return None
    if expected is not None and sha(src).lower()!=expected.lower(): raise ValueError(f'Asset {spec["id"]}: returned resource sha256 mismatch')
    return src
def materialize_assets(book,work,stage,issues,renderer=None):
    specs={}; full_pages=set()
    for group in book['chapters']+book['notes']:
        for b in group['blocks']:
            for spec in iter_assets(b):
                if spec['id'] in specs and specs[spec['id']]!=spec: raise ValueError('Conflicting asset definitions: '+spec['id'])
                specs[spec['id']]=spec
    for image in book.get('publication',{}).get('images',[]):
        spec=image['asset']
        if spec['id'] in specs: raise ValueError('Packaging and body assets need distinct IDs')
        specs[spec['id']]=spec; full_pages.add(spec['id'])
    doc=None; result={}; state=load(work/'state.json')
    def source_doc():
        nonlocal doc
        if doc is None:
            path=Path(state['source_path'])
            if sha(path)!=book['source_sha256']: raise ValueError('Source PDF changed')
            doc=pdf_module().open(path)
        return doc
    try:
        for key,spec in specs.items():
            valid_id(key); folder=stage/'assets'; folder.mkdir(exist_ok=True); dest=folder/(key+'.png'); method='source-crop'
            src=local_asset_path(spec,work,issues); rendered=False; render_error=None
            if spec.get('tex'):
                dest=folder/(key+'.svg')
                try:
                    if not spec.get('tex_verified'): raise ValueError('TeX lacks symbol-level verification')
                    if not renderer: raise ValueError('No formula renderer selected')
                    proc=run([shutil.which('node') or 'node',str(renderer),spec['tex'],str(dest)])
                    if proc.returncode or not dest.exists(): raise ValueError(proc.stderr or 'Renderer produced no asset')
                    if ET.parse(dest).getroot().tag!='{http://www.w3.org/2000/svg}svg': raise ValueError('Invalid formula SVG')
                    method='verified-tex-svg'; rendered=True
                except Exception as exc:
                    if dest.exists(): dest.unlink()
                    render_error=exc; dest=folder/(key+'.png')
            if not rendered:
                if src is not None:
                    dest=folder/(key+src.suffix.lower()); shutil.copyfile(src,dest); method='verified-local-resource'
                elif key in full_pages:
                    d=source_doc()
                    if not 1<=spec['page']<=len(d): raise ValueError('Packaging image page is outside source PDF')
                    d[spec['page']-1].get_pixmap(dpi=spec.get('dpi',200),alpha=False).save(dest); method='full-packaging-page'
                elif spec.get('xref'):
                    f=pdf_module(); d=source_doc(); extracted=d.extract_image(spec['xref']); pix=f.Pixmap(d,spec['xref']); mask=extracted.get('smask',0)
                    if mask: pix=f.Pixmap(pix,f.Pixmap(d,mask))
                    if pix.colorspace and pix.colorspace.n>3: pix=f.Pixmap(f.csRGB,pix)
                    pix.save(dest); method='native-image-xref'
                else: crop_asset(source_doc(),spec,dest)
                if render_error is not None: issues.append(f'Formula {key}: render failure -> {method} ({render_error})')
            result[key]={'href':'assets/'+dest.name,'method':method,'source':spec}
    finally:
        if doc: doc.close()
    return result
def build(args):
    explicit = getattr(args,'book',None)
    manifest_path = getattr(args,'translation_manifest',None)
    if bool(explicit) != bool(manifest_path):
        raise ValueError('Translated book and translation manifest must be paired together')
    work=Path(args.work).resolve(); book=load(explicit or work/'book.json'); output=Path(args.output).resolve(); state=load(work/'state.json')
    report_dir = work
    translated = bool(explicit)
    if translated:
        if not getattr(args,'report_dir',None): raise ValueError('Translated publication requires --report-dir')
        report_dir = Path(args.report_dir).resolve()
        if report_dir == work or work.is_relative_to(report_dir): raise ValueError('Translation reports must be separate from source WORK')
        from translation_contract import validate_translation_binding, compile_relationships
        manifest=load(manifest_path)
        validate_translation_binding(book,manifest,work)
        book=compile_relationships(book,manifest,work)
    elif book.get('schema') != 'epub-book/1':
        raise ValueError('epub-book/2 requires explicit translated book and manifest')
    if output==Path(state['source_path']).resolve() or output.suffix.lower()!='.epub': raise ValueError('Output must be a separate .epub file')
    if sha(state['source_path'])!=book['source_sha256']: raise ValueError('Source PDF changed')
    if not translated and not book.get('reviewed') and not args.allow_unreviewed: raise ValueError('Unreviewed plan; compare sources before publication')
    if sha(work/'raw.json')!=book['raw_sha256']: raise ValueError('Raw changed after normalization')
    if not book['chapters']: raise ValueError('Book needs included content')
    book=apply_publication(book,work); publication=book.get('publication')
    language=book['metadata']['language']
    if language=='und' and book.get('reviewed'): raise ValueError('Reviewed book needs original language metadata')
    issues=list(book.get('issues') or []); output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='epub-',dir=work) as tmp:
        stage=Path(tmp)/'EPUB'; stage.mkdir(); shutil.copyfile(SKILL/'assets/book.css',stage/'book.css')
        assets=materialize_assets(book,work,stage,issues,args.formula_renderer)
        files={c['id']:c['id']+'.xhtml' for c in book['chapters']}; notes={n['id']:n for n in book['notes']}; refs=defaultdict(list); all_ids=set(); blocks={}
        for c in book['chapters']:
            blocks[c['id']]=c['id']
            for b in c['blocks']: blocks[b['id']]=c['id']
        for n in book['notes']:
            if n['chapter'] not in files: raise ValueError('Note belongs to missing chapter: '+n['id'])
            for b in n['blocks']: blocks[b['id']]=n['chapter']
        for n in book['notes']: blocks[n['id']]=n['chapter']
        relation_returns=defaultdict(list)
        def claim(id):
            valid_id(id)
            if id in all_ids: raise ValueError('Duplicate generated ID: '+id)
            all_ids.add(id)
        def inline(parent,items,current):
            for item in items:
                if 'note' in item:
                    nid=item['note']
                    if nid not in notes: raise ValueError('Missing note body: '+nid)
                    rid=item['id']; claim(rid); n=notes[nid]; placement=item.get('placement','super')
                    if placement not in {'super','baseline'}: raise ValueError('Unknown note marker placement')
                    cls='noteref noteref-baseline' if placement=='baseline' else 'noteref'
                    a=element('a',parent,str(item.get('label',n['label'])),id=rid,href=files[n['chapter']]+'#'+nid,role='doc-noteref',**{'class':cls})
                    a.set('{'+EPUB+'}type','noteref'); refs[nid].append((files[current],rid))
                elif 'asset' in item:
                    spec=item['asset']; attrs={'class':'formula-inline'}
                    if 'height_em' in spec or 'baseline_em' in spec:
                        height=float(spec.get('height_em',1.15)); baseline=float(spec.get('baseline_em',-.18))
                        if not 0<height<=12 or not -12<=baseline<=12: raise ValueError('Invalid inline formula relative dimensions')
                        attrs['style']=f'height:{height:g}em;vertical-align:{baseline:g}em'
                    element('img',parent,src=assets[spec['id']]['href'],alt=spec.get('alt',''),**attrs)
                elif 'citation' in item:
                    rid=item['id']; claim(rid)
                    span=element('span',parent,id=rid)
                    targets=item['citation']
                    labels=item.get('target_labels',[])
                    for ti,target in enumerate(targets):
                        if target not in blocks: raise ValueError('Missing semantic reference target: '+target)
                        if ti: add_text(span,', ')
                        label=(labels[ti] if ti<len(labels) and labels[ti] else item.get('text','')) if len(targets)>1 else item.get('text','')
                        element('a',span,label or target,href=files[blocks[target]]+'#'+target)
                        relation_returns[target].append((files[current],rid))
                elif 'link' in item:
                    target=item['link']
                    if target not in blocks: raise ValueError('Missing formula/figure reference: '+target)
                    element('a',parent,item['text'],href=files[blocks[target]]+'#'+target)
                else:
                    p=parent
                    for style in item.get('styles',[]):
                        tag={'bold':'strong','italic':'em','sup':'sup','sub':'sub'}.get(style,'span'); p=element(tag,p,**({'class':style} if tag=='span' else {}))
                    add_text(p,item.get('text',''))
        def render(b,parent,current):
            kind=b['kind']; bid=b['id']; claim(bid)
            if kind in {'figure','formula','table-image'}:
                spec=b['asset']; el=element('div' if kind=='formula' else 'figure',parent,id=bid,**{'class':'formula' if kind=='formula' else 'figure'})
                attrs={}
                if kind=='formula' and 'width_em' in spec:
                    width=spec['width_em']
                    if isinstance(width,bool) or not isinstance(width,(int,float)) or not 0<width<=100 or not math.isfinite(width):
                        raise ValueError('Display formula width_em must be a finite number in 0..100 em, excluding zero')
                    attrs['style']=f'width:{width:g}em;max-width:100%'
                element('img',el,src=assets[spec['id']]['href'],alt=spec.get('alt',''),**attrs)
                if b.get('equation_label') and not spec.get('includes_label'): element('span',el,b['equation_label'],**{'class':'equation-label'})
                if b.get('inline'):
                    inline(element('p' if kind=='formula' else 'figcaption',el,**{'class':'caption'}),b['inline'],current)
                return
            if kind=='table':
                if not b.get('table_evidence'): raise ValueError('Semantic table needs source cell evidence')
                table=element('table',parent,id=bid)
                if b.get('inline'): inline(element('caption',table),b['inline'],current)
                for ri,row in enumerate(b['rows']):
                    tr=element('tr',table)
                    for cell in row:
                        attrs={}; header=ri<b.get('header_rows',0)
                        if isinstance(cell,dict):
                            if not isinstance(cell.get('inline'),list): raise ValueError('Table cell object needs an inline list')
                            items=cell['inline']
                            if 'header' in cell:
                                if not isinstance(cell['header'],bool): raise ValueError('Table cell header must be boolean')
                                header=cell['header']
                            for span in ('rowspan','colspan'):
                                if span in cell:
                                    value=cell[span]
                                    if type(value) is not int or value<=0: raise ValueError('Table cell '+span+' must be a positive integer')
                                    attrs[span]=str(value)
                        else: items=cell if isinstance(cell,list) else [{'text':cell}]
                        inline(element('th' if header else 'td',tr,**attrs),items,current)
                return
            if kind in {'list','ordered-list'}:
                el=element('ol' if kind=='ordered-list' else 'ul',parent,id=bid)
                for items in b['items']: inline(element('li',el),items,current)
                return
            tag={'paragraph':'p','heading':'h'+str(b.get('level',2)),'quote':'blockquote','verse':'p'}.get(kind)
            if tag not in {'p','blockquote','h2','h3','h4','h5','h6'}: raise ValueError('Invalid block kind/level: '+kind)
            el=element(tag,parent,id=bid,**({'class':'verse'} if kind=='verse' else {})); inline(el,b['inline'],current)
        def visible_toc(parent,toc):
            section=element('section',parent,id='publication-contents',**{'class':'visible-toc'})
            section.set('{'+EPUB+'}type','toc'); element('h1',section,book['labels']['contents'])
            for chapter in toc:
                group=element('div',section,**{'class':'toc-chapter'})
                element('a',group,chapter['title'],href=chapter['href'])
                if chapter['sections']:
                    sub=element('div',group,**{'class':'toc-sections'})
                    for item in chapter['sections']:
                        element('a',element('div',sub,**{'class':'toc-section'}),item['title'],href=item['href'])
        roots={}; toc=[]
        if publication: toc=publication['toc']['entries']
        for c in book['chapters']:
            claim(c['id']); root,body=xhtml(c['title'],language); body.set('class','chapter'); body.set('{'+EPUB+'}type','bodymatter'); element('h1',body,c['title'],id=c['id']); sections=[]
            for b in c['blocks']:
                if publication and publication['toc']['placement']=={'chapter':c['id'],'before_block':b['id']}:
                    claim('publication-contents'); visible_toc(body,toc)
                render(b,body,c['id'])
                if b['kind']=='heading' and b.get('level',2)==2: sections.append({'title':''.join(i.get('text','') for i in b['inline']),'href':files[c['id']]+'#'+b['id']})
            roots[c['id']]=(root,body)
            if not publication: toc.append({'title':c['title'],'href':files[c['id']]+'#'+c['id'],'sections':sections})
        note_nodes={}
        for c in book['chapters']:
            selected=[n for n in book['notes'] if n['chapter']==c['id']]
            if selected:
                section=element('section',roots[c['id']][1],role='doc-endnotes',**{'class':'notes'}); section.set('{'+EPUB+'}type','endnotes'); element('h2',section,book['labels']['notes'])
                for n in selected:
                    claim(n['id']); note=element('aside',section,id=n['id'],role='note',**{'class':'note'}); note.set('{'+EPUB+'}type','endnote'); element('p',note,n['label'],**{'class':'no-indent'})
                    for b in n['blocks']: render(b,note,c['id'])
                    note_nodes[n['id']]=note
        # A later note, including one in another chapter, can cite an earlier note.
        # Resolve returns only after every note body has contributed its references.
        for n in book['notes']:
            note=note_nodes[n['id']]; links=refs.get(n['id'],[])
            if not links: issues.append(f'Note {n["id"]} lacks a verified reference; retained as readable endnote.')
            for i,(file,rid) in enumerate(links,1): element('a',note,book['labels']['return']+(f' {i}' if len(links)>1 else ''),href=file+'#'+rid,role='doc-backlink',**{'class':'backlink'})
        for target,returns in relation_returns.items():
            owner=roots[blocks[target]][0]
            node=next((n for n in owner.iter() if n.get('id')==target),None)
            if node is None: raise ValueError('Missing rendered target: '+target)
            if node.tag=='{'+X+'}table':
                caption=node.find('{'+X+'}caption')
                if caption is None:
                    caption=element('caption');node.insert(0,caption)
                node=caption
            elif node.tag in {'{'+X+'}ol','{'+X+'}ul'} | {'{'+X+'}h'+str(i) for i in range(1,7)}:
                parent=next(p for p in owner.iter() if node in list(p))
                after=element('p',**{'class':'backlinks'});parent.insert(list(parent).index(node)+1,after);node=after
            elif node.tag in {'{'+X+'}figure','{'+X+'}div'}:
                node=element('p',node,**{'class':'backlinks'})
            # Block/heading targets receive returns without copying any content.
            for index,(file,rid) in enumerate(returns,1):
                add_text(node,' ')
                element('a',node,book['labels']['return']+' '+str(index),href=file+'#'+rid,**{'class':'backlink'})
        for c in book['chapters']:
            (stage/files[c['id']]).write_bytes(xml_bytes(roots[c['id']][0]))
        navroot,nb=xhtml(book['labels']['contents'],language); nav=element('nav',nb,id='toc'); nav.set('{'+EPUB+'}type','toc'); element('h1',nav,book['labels']['contents']); ol=element('ol',nav)
        contents,cb=xhtml(book['labels']['contents'],language)
        for c in toc:
            li=element('li',ol); element('a',li,c['title'],href=c['href'])
            if c['sections']:
                sub=element('ol',li)
                for s in c['sections']: element('a',element('li',sub),s['title'],href=s['href'])
        standalone=not publication or 'chapter' not in publication['toc']['placement']
        (stage/'nav.xhtml').write_bytes(xml_bytes(navroot))
        if standalone:
            claim('publication-contents'); visible_toc(cb,toc)
            (stage/'contents.xhtml').write_bytes(xml_bytes(contents))
        front_files=[]; cover_href=None
        for image in publication['images'] if publication else []:
            title=image['asset']['alt']; root,body=xhtml(title,language)
            body.set('class','packaging-image'); body.set('{'+EPUB+'}type','cover' if image['role']=='cover' else 'backmatter')
            element('img',body,src=assets[image['asset']['id']]['href'],alt=title)
            (stage/image['file']).write_bytes(xml_bytes(root)); front_files.append(image['file'])
            if image['role']=='cover': cover_href=assets[image['asset']['id']]['href']
        ET.register_namespace('',OPF); ET.register_namespace('dc',DC)
        package=ET.Element('{'+OPF+'}package',{'version':'3.0','unique-identifier':'book-id','prefix':'rendition: http://www.idpf.org/vocab/rendition/#'})
        meta=ET.SubElement(package,'{'+OPF+'}metadata'); identifier='urn:uuid:'+str(uuid.uuid5(uuid.NAMESPACE_URL,book['source_sha256']+digest(book)))
        ET.SubElement(meta,'{'+DC+'}identifier',{'id':'book-id'}).text=identifier
        for k,v in [('title',book['metadata']['title']),('language',language),('creator',book['metadata'].get('creator'))]:
            if v: ET.SubElement(meta,'{'+DC+'}'+k).text=v
        ET.SubElement(meta,'{'+OPF+'}meta',{'property':'dcterms:modified'}).text=datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')
        ET.SubElement(meta,'{'+OPF+'}meta',{'property':'rendition:layout'}).text='reflowable'
        manifest=ET.SubElement(package,'{'+OPF+'}manifest'); itemids={}
        for i,p in enumerate(sorted(p for p in stage.rglob('*') if p.is_file())):
            href=p.relative_to(stage).as_posix(); iid=f'item{i}'; itemids[href]=iid
            media={'.xhtml':'application/xhtml+xml','.css':'text/css','.svg':'image/svg+xml','.png':'image/png','.jpg':'image/jpeg','.jpeg':'image/jpeg'}[p.suffix]
            attrs={'id':iid,'href':href,'media-type':media}
            if href=='nav.xhtml': attrs['properties']='nav'
            if href==cover_href: attrs['properties']='cover-image'
            ET.SubElement(manifest,'{'+OPF+'}item',attrs)
        spine=ET.SubElement(package,'{'+OPF+'}spine'); reading_order=list(front_files)
        if not publication: reading_order.append('contents.xhtml')
        for c in book['chapters']:
            if publication and publication['toc']['placement']=={'before':c['id']}: reading_order.append('contents.xhtml')
            reading_order.append(files[c['id']])
            if publication and publication['toc']['placement']=={'after':c['id']}: reading_order.append('contents.xhtml')
        for file in reading_order: ET.SubElement(spine,'{'+OPF+'}itemref',{'idref':itemids[file]})
        (stage/'package.opf').write_bytes(ET.tostring(package,encoding='utf-8',xml_declaration=True))
        container=b'<?xml version="1.0" encoding="UTF-8"?><container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container"><rootfiles><rootfile full-path="EPUB/package.opf" media-type="application/oebps-package+xml"/></rootfiles></container>'
        pending=output.with_suffix('.epub.tmp')
        with zipfile.ZipFile(pending,'w',compression=zipfile.ZIP_DEFLATED) as z:
            z.writestr('mimetype','application/epub+zip',compress_type=zipfile.ZIP_STORED); z.writestr('META-INF/container.xml',container)
            for p in stage.rglob('*'):
                if p.is_file(): z.write(p,'EPUB/'+p.relative_to(stage).as_posix())
        checks=check_epub(pending)
        if publication: checks['errors'].extend(check_publication(pending,book,reading_order))
        if checks['errors']: pending.unlink(); raise ValueError('Structural check failed: '+str(checks['errors']))
        pending.replace(output)
    report={'source_name':book['source_name'],'source_sha256':book['source_sha256'],'epub':output.name,'epub_sha256':sha(output),
            'reviewed':book['reviewed'],'selected_pages':book['selected_pages'],'extraction':book['extraction'],'structure_rules':book['structure_rules'],
            'chapter_count':len(book['chapters']),'note_mapping':[{k:n.get(k) for k in ['id','label','original_label','chapter','association_evidence']} for n in book['notes']],
            'assets':assets,'publication':publication,'reading_order':reading_order,'issues':issues,'omissions':book['omissions'],'review_evidence':book['review_evidence'],'checks':checks,
            'epubcheck':'Not run by build; use check --epubcheck JAR.','reader_validation':'Not performed by build; record actual reader/version.',
            'style_limits':['OCR has no reliable font/style information; recovered styles need visual evidence.','Dot emphasis falls back to underline; chapter breaks depend on reader.']}
    report['corrections']=[{'block':b['id'],'edits':b.get('edits',[]),'evidence':[i.get('evidence') for i in b.get('inline',[]) if i.get('evidence')]} for group in book['chapters']+book['notes'] for b in group['blocks'] if b.get('edits') or any(i.get('evidence') for i in b.get('inline',[]))]
    report_dir.mkdir(parents=True,exist_ok=True)
    save(report_dir/'conversion-report.json',report)
    lines=[f'# Conversion: {output.name}',f'- Source: {book["source_name"]}',f'- Reviewed: {book["reviewed"]}',f'- Chapters: {len(book["chapters"])}; notes: {len(book["notes"])}','- Structural errors: 0','- EPUBCheck and reader verification: separate required steps.','','## Issues and fallbacks']
    lines+=['- '+s for s in issues] or ['- No unresolved issues recorded; this does not replace visual verification.']
    lines+=['','## Style limits']+['- '+s for s in report['style_limits']]
    lines+=['','## Recovery evidence',f'- {len(report["corrections"])} blocks retain correction/spacing/cell evidence in conversion-report.json and review.json.',f'- {len(report["omissions"])} source records omitted with explicit layout evidence.']
    (report_dir/'conversion-report.md').write_text('\n'.join(lines)+'\n',encoding='utf-8'); publication_state={'stage':'built','epub_sha256':report['epub_sha256'],'translation':translated}
    if translated: save(report_dir/'publication-state.json',publication_state)
    else:
        state.update(publication_state); save(work/'state.json',state)
    print(f'Built {output}; structural errors: 0')
def check_publication(path,book,reading_order=None):
    """Verify the compiled policy against packaged resources, without text output."""
    errors=[]; publication=book['publication']
    with zipfile.ZipFile(path) as z:
        roots={name:ET.fromstring(z.read(name)) for name in z.namelist() if name.endswith(('.xhtml','.opf'))}
        opf=roots['EPUB/package.opf']; manifest={i.get('id'):i for i in opf.findall('.//{'+OPF+'}item')}
        spine=[manifest[r.get('idref')].get('href') for r in opf.findall('.//{'+OPF+'}itemref')]
        if reading_order is not None and spine!=reading_order: errors.append('Publication spine differs from reviewed order')
        front=[image['file'] for image in publication['images']]
        if spine[:len(front)]!=front: errors.append('Packaging images must be first, cover then back-cover')
        visible=[]
        for name,root in roots.items():
            if not name.endswith('.xhtml'): continue
            for section in root.findall('.//{'+X+'}section[@id="publication-contents"]'): visible.append((name,section))
        if len(visible)!=1: errors.append('Exactly one visible bookmark contents is required')
        expected=[(entry['href'],entry['title']) for chapter in publication['toc']['entries'] for entry in [chapter]+chapter['sections']]
        def links(node): return [(a.get('href'),''.join(a.itertext())) for a in node.findall('.//{'+X+'}a')]
        nav=roots['EPUB/nav.xhtml'].find('.//{'+X+'}nav[@{'+EPUB+'}type="toc"]')
        if nav is None or links(nav)!=expected: errors.append('Navigation must match reviewed PDF bookmarks')
        if nav is not None:
            listing=nav.find('{'+X+'}ol'); chapters=listing.findall('{'+X+'}li') if listing is not None else []
            expected_chapters=publication['toc']['entries']
            if len(chapters)!=len(expected_chapters): errors.append('Navigation chapter hierarchy mismatch')
            for li,chapter in zip(chapters,expected_chapters):
                link=li.find('{'+X+'}a'); sub=li.find('{'+X+'}ol')
                expected_sections=[(s['href'],s['title']) for s in chapter['sections']]
                if link is None or link.get('href')!=chapter['href'] or (links(sub) if sub is not None else [])!=expected_sections:
                    errors.append('Navigation section belongs to wrong chapter')
        if visible:
            name,section=visible[0]
            if section.find('.//{'+X+'}ol') is not None: errors.append('Visible contents must not use an ordered list')
            if links(section)!=expected: errors.append('Visible contents links must match navigation')
            groups=section.findall('{'+X+'}div[@class="toc-chapter"]')
            if len(groups)!=len(publication['toc']['entries']): errors.append('Visible contents chapter hierarchy mismatch')
            for group,chapter in zip(groups,publication['toc']['entries']):
                link=group.find('{'+X+'}a'); sub=group.find('{'+X+'}div[@class="toc-sections"]')
                expected_sections=[(s['href'],s['title']) for s in chapter['sections']]
                if link is None or link.get('href')!=chapter['href'] or (links(sub) if sub is not None else [])!=expected_sections:
                    errors.append('Visible contents section belongs to wrong chapter')
            placement=publication['toc']['placement']
            if 'chapter' in placement:
                if name!='EPUB/'+placement['chapter']+'.xhtml': errors.append('Visible contents is in wrong chapter')
                else:
                    body=roots[name].find('{'+X+'}body'); ids=[child.get('id') for child in body]
                    if ids.index('publication-contents')+1!=ids.index(placement['before_block']): errors.append('Visible contents is at wrong original block position')
            else:
                target=next(iter(placement.values()))+'.xhtml'; key=next(iter(placement))
                try:
                    distance=spine.index(target)-spine.index('contents.xhtml')
                    if distance!=(1 if key=='before' else -1): errors.append('Visible contents is at wrong original chapter position')
                except ValueError: errors.append('Visible contents is missing from spine')
        for image in publication['images']:
            root=roots.get('EPUB/'+image['file']); body=root.find('{'+X+'}body') if root is not None else None
            if body is None or len(body)!=1 or body[0].tag!='{'+X+'}img': errors.append('Packaging must contain only the preserved image')
        for chapter in book['chapters']:
            root=roots['EPUB/'+chapter['id']+'.xhtml']; body=root.find('{'+X+'}body')
            selected=[n for n in book['notes'] if n['chapter']==chapter['id']]
            section=body.find('{'+X+'}section[@role="doc-endnotes"]')
            if selected and (section is None or body[-1] is not section): errors.append('Notes must be at their chapter end')
            asides=section.findall('{'+X+'}aside') if section is not None else []
            if [n.get('id') for n in asides]!=[n['id'] for n in selected]: errors.append('Endnote order differs from body-first order')
            for aside,note in zip(asides,selected):
                label=aside.find('{'+X+'}p')
                if label is None or label.text!=note['label']: errors.append('Endnote numeric label mismatch')
            for block in chapter['blocks']:
                from epub_publication import _items
                for item in _items(block):
                    marker=root.find('.//{'+X+'}a[@id="'+item['id']+'"]')
                    if marker is None or marker.text!=item['label'] or marker.get('class')!='noteref': errors.append('Note marker needs its chapter numeric superscript')
    return errors

def check_epub(path):
    errors=[]; ids={}; roots={}; references=[]
    with zipfile.ZipFile(path) as z:
        names=z.namelist(); pool=set(names)
        if len(pool)!=len(names): errors.append('Duplicate ZIP entries')
        if not names or names[0]!='mimetype' or z.read('mimetype')!=b'application/epub+zip' or z.getinfo('mimetype').compress_type!=0: errors.append('mimetype must be first, exact, uncompressed')
        for name in names:
            if name.startswith('/') or '..' in PurePosixPath(name).parts or '\\' in name: errors.append('Unsafe ZIP path '+name)
            if name.endswith(('.xhtml','.opf','.xml','.svg')):
                try: root=ET.fromstring(z.read(name)); roots[name]=root
                except ET.ParseError as exc: errors.append(f'{name}: invalid XML {exc}'); continue
                found=[e.attrib['id'] for e in root.iter() if 'id' in e.attrib]; ids[name]=set(found)
                if len(found)!=len(set(found)): errors.append('Duplicate IDs in '+name)
                for e in root.iter():
                    for attr in ['href','src','{http://www.w3.org/1999/xlink}href']:
                        if e.get(attr): references.append((name,e.get(attr)))
            if name.endswith('.css'): references.extend((name,m) for m in re.findall(r'url\([\s\"\']*([^\)\"\']+)',z.read(name).decode('utf-8')))
        for name,href in references:
            u=urlsplit(href)
            if u.scheme or u.netloc: errors.append(f'Nonlocal URL {name} -> {href}'); continue
            target=posixpath.normpath(posixpath.join(posixpath.dirname(name),unquote(u.path))) if u.path else name
            if target not in pool: errors.append(f'Missing resource {name} -> {href}')
            elif u.fragment and unquote(u.fragment) not in ids.get(target,set()): errors.append(f'Missing target {name} -> {href}')
        container=roots.get('META-INF/container.xml'); opfpath=None
        if container is not None:
            rootfile=container.find('.//{urn:oasis:names:tc:opendocument:xmlns:container}rootfile')
            if rootfile is not None: opfpath=rootfile.get('full-path')
        if not opfpath or opfpath not in roots: errors.append('Missing OPF rootfile')
        else:
            opf=roots[opfpath]; items=opf.findall('.//{'+OPF+'}item'); manifest={i.get('id'):i for i in items}
            if len(manifest)!=len(items): errors.append('Duplicate manifest IDs')
            if opf.get('version')!='3.0': errors.append('Expected EPUB 3 package')
            if len([i for i in items if 'nav' in i.get('properties','').split()])!=1: errors.append('Exactly one nav required')
            for term in ['title','language','identifier']:
                if opf.find('.//{'+DC+'}'+term) is None: errors.append('Missing metadata '+term)
            for ref in opf.findall('.//{'+OPF+'}itemref'):
                if ref.get('idref') not in manifest: errors.append('Unknown spine item')
            declared={posixpath.normpath(posixpath.join(posixpath.dirname(opfpath),i.get('href'))) for i in items}
            resources={n for n in names if n.startswith(posixpath.dirname(opfpath)+'/') and n!=opfpath}
            if resources-declared: errors.append('Unmanifested resources '+str(sorted(resources-declared)))
        for name,root in roots.items():
            if not name.endswith('.xhtml'): continue
            for a in root.findall('.//{'+X+'}a'):
                if a.get('{'+EPUB+'}type')!='noteref': continue
                u=urlsplit(a.get('href','')); target=posixpath.normpath(posixpath.join(posixpath.dirname(name),u.path)) if u.path else name
                note=next((e for e in roots.get(target,ET.Element('none')).iter() if e.get('id')==u.fragment),None)
                if note is None or note.get('{'+EPUB+'}type')!='endnote': errors.append('Noteref lacks endnote '+a.get('id',''))
                elif not any(posixpath.normpath(posixpath.join(posixpath.dirname(target),urlsplit(b.get('href','')).path))==name and urlsplit(b.get('href','')).fragment==a.get('id') for b in note.findall('.//{'+X+'}a')): errors.append('Missing note return '+a.get('id',''))
        for root in roots.values():
            toc=root.find('.//{'+X+'}nav[@{'+EPUB+'}type="toc"]')
            if toc is None: continue
            def depth(e): return (1 if e.tag=='{'+X+'}ol' else 0)+max([depth(c) for c in e]+[0])
            if depth(toc)>2: errors.append('Navigation exceeds chapter-section depth')
    return {'errors':errors,'resource_count':len(names),'links_checked':len(references),'xhtml_count':sum(n.endswith('.xhtml') for n in names)}
def check(args):
    result=check_epub(args.input)
    if args.epubcheck:
        java=shutil.which('java')
        if not java or not Path(args.epubcheck).is_file(): result['epubcheck']={'status':'unavailable'}
        else:
            proc=run([java,'-jar',args.epubcheck,args.input],timeout=180)
            result['epubcheck']={'status':'passed' if proc.returncode==0 else 'failed','returncode':proc.returncode,'output':proc.stdout+proc.stderr}
    else: result['epubcheck']={'status':'not-run'}
    import json
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.output: save(args.output,result)
    return 1 if result['errors'] or result['epubcheck']['status']=='failed' else 0
