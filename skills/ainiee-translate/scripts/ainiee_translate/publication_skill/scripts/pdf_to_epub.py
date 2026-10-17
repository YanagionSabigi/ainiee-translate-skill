#!/usr/bin/env python3
"""Source-preserving PDF extraction and reviewed EPUB 3 assembly (Python 3.10+)."""
from __future__ import annotations
import argparse, csv, hashlib, importlib.util, io, json, math, os, re, shutil, subprocess, sys
from collections import defaultdict
from pathlib import Path

VERSION='1.3.0'
SKILL=Path(__file__).resolve().parents[1]
for stream in (sys.stdout,sys.stderr):
    if hasattr(stream,'reconfigure'): stream.reconfigure(encoding='utf-8')

def pdf_module():
    try:
        import pymupdf
        return pymupdf
    except ImportError as exc:
        raise ValueError('PyMuPDF missing in this Python; select a Python with pymupdf or install it in an isolated environment.') from exc

def load(path): return json.loads(Path(path).read_text(encoding='utf-8-sig'))
def json_default(obj):
    if isinstance(obj,bytes): return obj.hex()
    if type(obj).__module__.startswith('pymupdf'): return list(obj)
    raise TypeError(f'Unsupported JSON value: {type(obj).__name__}')
def save(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_suffix(path.suffix+'.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2,default=json_default),encoding='utf-8'); tmp.replace(path)
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''): h.update(chunk)
    return h.hexdigest()
def digest(obj): return hashlib.sha256(json.dumps(obj,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
def run(argv,timeout=120): return subprocess.run(argv,capture_output=True,text=True,encoding='utf-8',errors='replace',timeout=timeout)
def pages(spec,count):
    if not spec or spec=='all': return list(range(1,count+1))
    result=set()
    for part in spec.split(','):
        if not re.fullmatch(r'\d+(?:-\d+)?',part.strip()): raise ValueError('Pages must be 1-based inclusive: 1-5,8')
        nums=list(map(int,part.split('-'))); a,b=nums[0],nums[-1]
        if a<1 or b<a or b>count: raise ValueError(f'Page range outside 1..{count}: {part}')
        result.update(range(a,b+1))
    return sorted(result)
def tesseract_path(explicit=None):
    if explicit: return str(Path(explicit)) if Path(explicit).is_file() else shutil.which(explicit)
    found=shutil.which('tesseract')
    if not found and os.name=='nt':
        p=Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Tesseract-OCR/tesseract.exe'
        found=str(p) if p.is_file() else None
    return found
def probe(args):
    from mineru_backend import probe as mineru_probe
    from mineru_local import probe as mineru_local_probe
    tess=tesseract_path(args.tesseract)
    result={'python':sys.version,'executable':sys.executable,'pipeline':VERSION,
            'modules':{m:bool(importlib.util.find_spec(m)) for m in ['pymupdf','PIL']},
            'tools':{m:shutil.which(m) for m in ['mineru','mineru-kit','mineru-open-api','babeldoc','java','epubcheck','node']},
            'tesseract':{'path':tess,'version':None,'languages':[]},'mineru':mineru_probe(),
            'mineru_local':mineru_local_probe(),
            'default_backend':'mineru-local','external_services':'Default MinerU extraction uses the local CLI; explicit MinerU cloud submission requires --allow-upload.'}
    result['tools']['mineru-open-api']=result['mineru']['cli'].get('path')
    if tess:
        result['tesseract']['version']=run([tess,'--version']).stdout.splitlines()[0]
        result['tesseract']['languages']=run([tess,'--list-langs']).stdout.splitlines()[1:]
    print(json.dumps(result,ensure_ascii=False,indent=2))
    if args.output: save(args.output,result)
def rect_check(page,bbox):
    f=pdf_module(); rect=f.Rect(bbox if bbox else page.rect)
    if rect.is_empty or not page.rect.contains(rect): raise ValueError(f'Invalid/out-of-page region: {bbox}')
    return rect
def native(page,rect):
    f=pdf_module(); data=page.get_text('dict',clip=rect,flags=f.TEXT_PRESERVE_WHITESPACE|f.TEXT_PRESERVE_LIGATURES); lines=[]
    for bi,block in enumerate(data['blocks']):
        if block['type']!=0: continue
        for line in block['lines']:
            spans=[]
            for s in line['spans']:
                styles=[]
                if s['flags']&16: styles.append('bold')
                if s['flags']&2: styles.append('italic')
                if s['flags']&1: styles.append('sup')
                spans.append({'text':s['text'],'styles':styles,'font':s['font'],'size':s['size'],'bbox':list(s['bbox']),'origin':list(s['origin'])})
            if ''.join(s['text'] for s in spans).strip(): lines.append({'bbox':list(line['bbox']),'spans':spans,'block':bi,'direction':list(line['dir']),'confidence':None})
    return lines
def text_of(line): return ''.join(s['text'] for s in line['spans'])
def inspect(args):
    f=pdf_module(); src=Path(args.input).resolve(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    doc=f.open(src); selection=pages(args.pages,len(doc)); records=[]
    from publication_input import load_plan, apply_selection_routes
    policy=load_plan(args,src,doc,out)
    selection,routes=apply_selection_routes(policy,selection,{},doc)
    for n in selection:
        p=doc[n-1]; rectangles=[rect_check(p,r.get('bbox')) for r in routes.get(str(n),[{}])]
        text='\n'.join(text_of(line) for rect in rectangles for line in native(p,rect)); images=p.get_image_info(xrefs=True)
        coverage=min(1.,sum((f.Rect(i['bbox'])&p.rect).get_area() for i in images)/p.rect.get_area())
        hidden=sum(len(t.get('chars',[])) for t in p.get_texttrace() if t.get('type')==3)
        suspicious=text.count('\ufffd')+sum(1 for c in text if ord(c)<32 and c not in '\n\t\r')
        category='scan' if len(text.strip())<8 and coverage>.5 else ('image-with-text-needs-verification' if coverage>.65 else 'digital-candidate')
        if suspicious or hidden: category='text-layer-needs-verification'
        records.append({'page':n,'width':p.rect.width,'height':p.rect.height,'text_chars':len(text),'image_coverage':coverage,
                        'hidden_chars':hidden,'suspicious_chars':suspicious,'category':category,'text_preview':text[:1400],
                        'fonts':p.get_fonts(full=True),'images':images,'drawing_count':len(p.get_drawings()),'page_label':p.get_label()})
    categories={r['category'] for r in records}; candidates=[r['page'] for r in records if r['category']!='digital-candidate']
    reps=sorted(set([selection[0],selection[len(selection)//2],selection[-1]]+candidates[:3])) if selection else []
    for n in reps:
        path=out/'pages'/f'p{n:04d}.png'; path.parent.mkdir(exist_ok=True); doc[n-1].get_pixmap(dpi=140).save(path)
    result={'schema':'pdf-inspection/1','source_name':src.name,'source_sha256':sha(src),'metadata':doc.metadata,'page_count':len(doc),
            'selected_pages':selection,'bookmarks':doc.get_toc(simple=False),'page_records':records,'representative_pages':reps,
            'classification':'mixed-candidate' if len(categories)>1 else next(iter(categories),'excluded-selection'),
            'language':'Determine from source pages; metadata is only a hint.','warning':'Routing hints are not reliability verdicts.'}
    if policy: result['publication_input']=policy
    save(out/'inspection.json',result); doc.close(); print(f'Inspected {len(selection)} pages -> {out}')
def ocr(page,rect,out,key,tess,language,dpi,psm,rotation):
    if not tess: raise ValueError('Tesseract unavailable: choose a local/authorized parser or source-verified transcription; no empty-text fallback.')
    pix=page.get_pixmap(clip=rect,dpi=dpi,alpha=False); path=out/'ocr'/f'{key}.png'; path.parent.mkdir(exist_ok=True); pix.save(path)
    if rotation:
        from PIL import Image
        with Image.open(path) as im: im.rotate(rotation,expand=False,fillcolor='white').save(path)
    proc=run([tess,str(path),'stdout','-l',language,'--dpi',str(dpi),'--psm',str(psm),'tsv'],timeout=180)
    (out/'ocr'/f'{key}.stderr.txt').write_text(proc.stderr,encoding='utf-8')
    if proc.returncode: raise ValueError('OCR failed: '+proc.stderr[-900:])
    (out/'ocr'/f'{key}.tsv').write_text(proc.stdout,encoding='utf-8'); groups=defaultdict(list)
    for w in csv.DictReader(io.StringIO(proc.stdout),delimiter='\t'):
        if w['level']=='5' and w['text'].strip(): groups[(w['block_num'],w['par_num'],w['line_num'])].append(w)
    lines=[]; scale=dpi/72; rad=math.radians(rotation)
    def original(x,y):
        a=x-pix.width/2; b=y-pix.height/2
        return (rect.x0+(math.cos(rad)*a-math.sin(rad)*b+pix.width/2)/scale,rect.y0+(math.sin(rad)*a+math.cos(rad)*b+pix.height/2)/scale)
    for group,words in groups.items():
        boxes=[]; spans=[]
        for wi,w in enumerate(words):
            x,y,ww,hh=[float(w[k]) for k in ['left','top','width','height']]
            corners=[original(x,y),original(x+ww,y),original(x,y+hh),original(x+ww,y+hh)]
            box=[min(c[0] for c in corners),min(c[1] for c in corners),max(c[0] for c in corners),max(c[1] for c in corners)]; boxes.append(box)
            spans.append({'text':(' ' if wi else '')+w['text'],'styles':[],'bbox':box,'confidence':float(w['conf']),'size':hh/scale,'font':None})
        lines.append({'bbox':[min(b[0] for b in boxes),min(b[1] for b in boxes),max(b[2] for b in boxes),max(b[3] for b in boxes)],
                      'block':'-'.join(group[:2]),'spans':spans,'confidence':sum(float(w['conf']) for w in words)/len(words)})
    return lines
def extract(args):
    if getattr(args,'backend','mineru-local')=='mineru-local':
        from mineru_local_flow import extract as mineru_local_extract
        return mineru_local_extract(args)
    from publication_input import load_plan, apply_selection_routes
    if getattr(args,'backend','local')=='mineru':
        with pdf_module().open(args.input) as policy_doc:
            policy=load_plan(args,Path(args.input).resolve(),policy_doc,Path(args.out))
        if policy: raise ValueError('Publication input plans require a local extraction backend')
    language={'ch':'chi_sim+eng','en':'eng','chinese_cht':'chi_tra+eng'}.get(args.language,args.language)
    route_selection=load(args.routes) if args.routes else {}
    if getattr(args,'backend','local')=='mineru':
        with pdf_module().open(args.input) as routing_doc: selected=pages(args.pages,len(routing_doc))
        if any(str(n) not in route_selection for n in selected) or any(r.get('method','mineru') in {'mineru','auto'} for n in selected for r in route_selection.get(str(n),[])):
            from mineru_flow import extract as mineru_extract
            return mineru_extract(args)
    f=pdf_module(); src=Path(args.input).resolve(); out=Path(args.out); out.mkdir(parents=True,exist_ok=True)
    doc=f.open(src); selection=pages(args.pages,len(doc)); routes=load(args.routes) if args.routes else {}; tess=tesseract_path(args.tesseract)
    policy=load_plan(args,src,doc,out)
    selection,routes=apply_selection_routes(policy,selection,routes,doc)
    source_hash=sha(src); records=[]; failures=[]; reused=0; tess_identity=[tess,Path(tess).stat().st_mtime_ns] if tess else None
    for n in selection:
        p=doc[n-1]; configs=routes.get(str(n),[{'method':'auto'}]); rectangles=[]
        if not configs: raise ValueError(f'Page {n}: empty routing list')
        for r in configs:
            rect=rect_check(p,r.get('bbox'))
            if any((rect&previous).get_area()>.1 for previous in rectangles): raise ValueError(f'Page {n}: overlapping extraction regions')
            rectangles.append(rect)
        record={'page':n,'width':p.rect.width,'height':p.rect.height,'regions':[]}
        for ri,route in enumerate(configs,1):
            rect=rectangles[ri-1]; key=f'p{n:04d}-r{ri:02d}'
            fingerprint=digest({'version':'1.0.0','pdf':source_hash,'page':n,'route':route,'language':language,'dpi':args.dpi,'psm':args.psm,'tesseract':tess_identity})
            cache=out/'cache'/f'{key}.json'; old=load(cache) if cache.exists() else {}
            if old.get('fingerprint')==fingerprint and old.get('status')=='complete': region=old; reused+=1
            else:
                method=route.get('method','auto'); region={'id':key,'bbox':list(rect),'route':route,'fingerprint':fingerprint,'lines':[],'issues':[]}
                try:
                    if method not in {'auto','native','ocr'}: raise ValueError(f'Unknown backend {method}')
                    if method=='auto':
                        candidate=native(p,rect); text=''.join(map(text_of,candidate)); method='native' if len(text.strip())>=8 and '\ufffd' not in text else 'ocr'
                        region['issues'].append('Automatic routing is provisional; verify text against page image, including hidden OCR.')
                    try:
                        lines=native(p,rect) if method=='native' else ocr(p,rect,out,key,tess,language,args.dpi,route.get('psm',args.psm),route.get('rotation',0))
                        if not lines: raise ValueError(f'{method} returned no text')
                    except Exception as exc:
                        if method=='native' and route.get('fallback')=='ocr':
                            region['issues'].append(f'Native failure -> OCR: {exc}'); method='ocr'
                            lines=ocr(p,rect,out,key,tess,language,args.dpi,route.get('psm',args.psm),route.get('rotation',0))
                            if not lines: raise ValueError('Fallback OCR returned no text')
                        else: raise
                    for li,line in enumerate(lines,1): line.update({'id':f'{key}-l{li:04d}','source':{'page':n,'bbox':line['bbox'],'method':method}})
                    region.update({'method':method,'status':'complete','lines':lines})
                except Exception as exc: region.update({'method':method,'status':'failed','error':str(exc)})
                save(cache,region)
            if region['status']=='failed': failures.append({'region':key,'error':region['error']})
            record['regions'].append(region)
        records.append(record)
    doc.close()
    raw={'schema':'pdf-raw/1','source_name':src.name,'source_sha256':source_hash,'selected_pages':selection,'pages':records,'failures':failures}
    if policy: raw['publication_input']=policy
    save(out/'raw.json',raw); save(out/'state.json',{'source_path':str(src),'source_sha256':source_hash,'selected_pages':selection,
         'stage':'extraction-failed' if failures else 'extracted','cached_regions_reused':reused,'failures':failures,
         **({'publication_input':policy} if policy else {})})
    print(f'Extracted {len(selection)} pages; reused {reused} regions; failures {len(failures)} -> {out}/raw.json'); return 2 if failures else 0
def index_raw(raw): return {l['id']:l for p in raw['pages'] for r in p['regions'] for l in r['lines']}
def draft(args):
    work=Path(args.work); raw=load(work/'raw.json'); blocks=[]
    if raw.get('semantic_blocks'):
        from mineru_draft import candidate_blocks
        blocks=candidate_blocks(raw)
    for p in raw['pages']:
        for r in p['regions']:
            if raw.get('semantic_blocks'): continue
            groups=[]
            for l in r['lines']:
                if groups and groups[-1][-1]['block']==l['block']: groups[-1].append(l)
                else: groups.append([l])
            for group in groups: blocks.append({'id':f'b{len(blocks)+1:04d}','kind':'paragraph','sources':[l['id'] for l in group],'joins':[' ']*(len(group)-1)})
    plan={'schema':'pdf-review/1','raw_sha256':sha(work/'raw.json'),'source_sha256':raw['source_sha256'],'reviewed':False,'review_evidence':[],
          'metadata':{'title':Path(raw['source_name']).stem,'language':'und','creator':''},'labels':{'notes':'Notes','contents':'Contents','return':'Return'},
          'chapters':[{'id':'document','title':Path(raw['source_name']).stem,'heading_sources':[],'blocks':blocks}],
          'notes':[],'omissions':[],'region_resolutions':[],'issues':['Unreviewed draft: verify order, paragraphs, headings, notes, assets and language.'],
          'structure_rules':{'fragment':True,'parts_mapping':'No inferred chapters','printed_page_offset':None}}
    if raw.get('publication_input'):
        policy=raw['publication_input']
        original_pages=sorted({entry['page'] for entry in policy['exclusions'] if entry['role']=='printed-toc'})
        plan['structure_rules']['publication']={'toc':{'source':'pdf-bookmarks','entries':[],
            'omissions':[],'original_pages':original_pages,'placement':{},'evidence':''},'images':[]}
        plan['issues'].append('Publication input exclusions are active; map local PDF bookmarks, original contents position and cover images before normalization.')
    path=work/'review.json'
    if path.exists(): raise ValueError('review.json already exists; preserve ongoing review')
    save(path,plan); print(f'Created unreviewed plan -> {path}')
def valid_id(value):
    if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*',value): raise ValueError(f'Unsafe/invalid ID: {value}')
    return value
def slice_spans(line,start=0,end=None):
    text=text_of(line); end=len(text) if end is None else end
    if not 0<=start<=end<=len(text): raise ValueError(f'Invalid source slice {line["id"]} {start}:{end}')
    result=[]; pos=0
    for s in line['spans']:
        a=max(start-pos,0); b=min(end-pos,len(s['text']))
        if a<b: result.append({'text':s['text'][a:b],'styles':s.get('styles',[])})
        pos+=len(s['text'])
    return result
def resolve_inline(items,idx,sources):
    result=[]
    for item in items:
        if not isinstance(item,dict): raise ValueError('Inline items must be objects')
        if 'line' in item:
            if item['line'] not in sources: raise ValueError('Inline source must be listed in block sources')
            result.extend(slice_spans(idx[item['line']],item.get('start',0),item.get('end')))
        elif 'text' in item:
            if not item.get('evidence'): raise ValueError('Literal text/correction needs source evidence')
            result.append(item)
        elif 'note' in item or 'asset' in item or 'link' in item or 'citation' in item or 'ref' in item: result.append(item)
        else: raise ValueError(f'Invalid inline item {item}')
    for item in result:
        if set(item.get('styles',[]))-{'bold','italic','underline','emphasis-dot','sup','sub'}: raise ValueError('Unknown text style')
        spec=item.get('asset')
        if spec and spec.get('crop_geometry_verified') is False and not spec.get('path') and not spec.get('xref'):
            raise ValueError('Formula/resource needs a precise source-verified crop bbox or returned image: '+spec['id'])
    return result
def resolve_block(block,idx,used):
    b=dict(block); valid_id(b['id']); sources=b.get('sources',[])
    for s in sources:
        if s not in idx: raise ValueError(f'Unknown source line: {s}')
        used.add(s)
    if not sources and not b.get('source_region'): raise ValueError(f'Block {b["id"]} needs line or region provenance')
    b['provenance']=[idx[s]['source']|{'line_id':s} for s in sources]
    if b.get('source_region'): b['provenance'].append(b['source_region'])
    if 'inline' in b:
        inline=resolve_inline(b['inline'],idx,sources)
    else:
        inline=[]; joins=b.get('joins',[' ']*(len(sources)-1))
        if len(joins)!=max(0,len(sources)-1): raise ValueError('One explicit join per pair of source lines')
        for i,s in enumerate(sources):
            if i: inline.append({'text':joins[i-1],'styles':[]})
            inline.extend(slice_spans(idx[s]))
    for edit in b.get('edits',[]):
        if not edit.get('evidence'): raise ValueError('Edit needs source evidence')
        old,new=edit['old'],edit['new']; text=''.join(i.get('text','') for i in inline)
        if text.count(old)!=1 or any('text' not in i for i in inline): raise ValueError('Edits require one text match; use source slices around links/assets')
        if any(i.get('styles') for i in inline) and 'style_resolution' not in edit: raise ValueError('Styled edit needs style_resolution or inline slices')
        inline=[{'text':text.replace(old,new,1),'styles':edit.get('style_resolution',[])}]
    if b.get('styles'):
        if not b.get('style_evidence'): raise ValueError('Restored styles need visual evidence')
        for item in inline:
            if 'text' in item: item['styles']=list(dict.fromkeys(item.get('styles',[])+b['styles']))
    for item in inline:
        if set(item.get('styles',[]))-{'bold','italic','underline','emphasis-dot','sup','sub'}: raise ValueError('Unknown text style')
    b['inline']=inline
    if b.get('items') is not None: b['items']=[resolve_inline(item,idx,sources) for item in b['items']]
    if b.get('rows') is not None:
        rows=[]
        for row in b['rows']:
            cells=[]
            for cell in row:
                if isinstance(cell,list): cell=resolve_inline(cell,idx,sources)
                elif isinstance(cell,dict): cell=dict(cell,inline=resolve_inline(cell.get('inline',[]),idx,sources))
                elif not isinstance(cell,str): raise ValueError('Invalid table cell')
                cells.append(cell)
            rows.append(cells)
        b['rows']=rows
    return b
def normalize(args):
    work=Path(args.work); raw=load(work/'raw.json'); plan=load(args.plan or work/'review.json'); idx=index_raw(raw); used=set(); ids=set()
    if plan['raw_sha256']!=sha(work/'raw.json') or plan['source_sha256']!=raw['source_sha256']: raise ValueError('Review/source hash mismatch; recheck and rebind changed extraction')
    if plan.get('reviewed') and not plan.get('review_evidence'): raise ValueError('Reviewed plan needs review_evidence')
    book={k:plan.get(k) for k in ['metadata','labels','reviewed','review_evidence','issues','structure_rules','source_sha256','raw_sha256']}
    book.update({'schema':'epub-book/1','metadata_provenance':plan.get('metadata_provenance',[]),'source_name':raw['source_name'],'selected_pages':raw['selected_pages'],'chapters':[],'notes':[],
                 'omissions':plan.get('omissions',[]),'region_resolutions':plan.get('region_resolutions',[]),
                 'semantic_resolutions':plan.get('semantic_resolutions',[]),'backend':raw.get('backend','local'),
                 'mineru_jobs':raw.get('mineru_jobs',[]),'mineru_result':raw.get('mineru_result',raw.get('mineru'))})
    if raw.get('publication_input'): book['publication_input']=raw['publication_input']
    elif (work/'publication-input.json').exists():
        from publication_input import load_plan
        state=load(work/'state.json')
        with pdf_module().open(state['source_path']) as source_doc:
            policy=load_plan(args,Path(state['source_path']),source_doc,work)
        if policy: book['publication_input']=policy
    def claim(id):
        valid_id(id)
        if id in ids: raise ValueError(f'Duplicate ID {id}')
        ids.add(id)
    for c in plan['chapters']:
        claim(c['id']); chapter=dict(c)
        for s in c.get('heading_sources',[]):
            if s not in idx: raise ValueError('Unknown chapter heading source')
            used.add(s)
        chapter['heading_provenance']=[idx[s]['source']|{'line_id':s} for s in c.get('heading_sources',[])]
        if plan.get('reviewed') and not c.get('heading_sources') and not c.get('heading_evidence'): raise ValueError('Chapter title needs source evidence, including fragment labels')
        chapter['blocks']=[]
        for b in c['blocks']: claim(b['id']); chapter['blocks'].append(resolve_block(b,idx,used))
        book['chapters'].append(chapter)
    chapters={c['id'] for c in book['chapters']}
    for note in plan.get('notes',[]):
        claim(note['id'])
        if note['chapter'] not in chapters: raise ValueError('Note belongs to unknown chapter')
        if not note.get('association_evidence'): raise ValueError('Note association needs evidence')
        n=dict(note); n['blocks']=[]
        for b in note['blocks']: claim(b['id']); n['blocks'].append(resolve_block(b,idx,used))
        book['notes'].append(n)
    for omission in plan.get('omissions',[]):
        if not omission.get('reason') or not omission.get('evidence'): raise ValueError('Omissions need reason and evidence')
        for s in omission['sources']:
            if s not in idx: raise ValueError('Unknown omitted source')
            if s in used: raise ValueError(f'Content also omitted: {s}')
            used.add(s)
    missing=set(idx)-used
    if missing: raise ValueError(f'{len(missing)} unaccounted lines, e.g. {sorted(missing)[:8]}')
    if raw.get('semantic_blocks'):
        semantic_ids={item['id'] for item in raw['semantic_blocks']}; covered=set()
        for group in book['chapters']+book['notes']:
            for block in group['blocks']: covered.update(block.get('mineru_blocks',[]))
        for omission in plan.get('omissions',[]): covered.update(omission.get('mineru_blocks',[]))
        for resolution in book['semantic_resolutions']:
            if not resolution.get('evidence'): raise ValueError('MinerU semantic resolution needs source evidence')
            covered.add(resolution['block'])
        if covered-semantic_ids: raise ValueError('Unknown MinerU semantic block ID')
        if semantic_ids-covered: raise ValueError('Unaccounted MinerU semantic blocks: '+str(sorted(semantic_ids-covered)[:8]))
    resolutions={r['region']:r for r in plan.get('region_resolutions',[])}
    for p in raw['pages']:
        area=sum((r['bbox'][2]-r['bbox'][0])*(r['bbox'][3]-r['bbox'][1]) for r in p['regions'])
        key=f'p{p["page"]:04d}-unrouted'
        if area<.999*p['width']*p['height'] and not resolutions.get(key,{}).get('evidence'): raise ValueError(f'Unrouted areas need resolution: {key}')
        for r in p['regions']:
            if r['status']=='failed' and not resolutions.get(r['id'],{}).get('evidence'): raise ValueError(f'Failed region needs source-verified resolution: {r["id"]}')
    book['extraction']=[{'page':p['page'],'regions':[{k:r.get(k) for k in ['id','bbox','method','status','issues','error']} for r in p['regions']]} for p in raw['pages']]
    from epub_publication import apply_publication
    if not getattr(args,'minimum_structure',False): book=apply_publication(book,work)
    save(work/('book.minimum.json' if getattr(args,'minimum_structure',False) else 'book.json'),book); print(f'Normalized {len(book["chapters"])} chapters -> {work}'); return book
def prepare(args):
    from types import SimpleNamespace
    from translation_contract import prepare_translation_book,persist_source
    work=Path(args.work)
    if (work/'book.source.json').exists():
        raise ValueError('Source snapshot already exists; use revise for evidence-bearing corrections')
    book=normalize(SimpleNamespace(work=args.work,plan=args.plan,minimum_structure=True))
    persist_source(prepare_translation_book(book,work),work)
    print('Minimum structure prepared; source verification and independent proofreading remain pending')


def revise(args):
    from translation_contract import revise_source
    revise_source(args.work,load(args.changes))
    print('Source revision recorded; reconcile the translation cache')


def revise_structure_command(args):
    from translation_contract import revise_structure
    revise_structure(args.work,args.plan,load(args.id_mapping),args.evidence)
    print('Structure revision and explicit unit lineage recorded; reconcile the cache')


def main():
    from epub_build import build,check
    parser=argparse.ArgumentParser(description=__doc__); sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('probe'); p.add_argument('--tesseract'); p.add_argument('--output'); p.set_defaults(func=probe)
    for name,fn in [('inspect',inspect),('extract',extract)]:
        p=sub.add_parser(name); p.add_argument('input'); p.add_argument('--out',required=True); p.add_argument('--pages',default='all'); p.set_defaults(func=fn)
        p.add_argument('--publication-plan',help='Local source-bound packaging, printed-TOC and term-index exclusions; defaults to WORK/publication-input.json if present')
        if name=='extract':
            p.add_argument('--routes'); p.add_argument('--language',default='ch'); p.add_argument('--dpi',type=int,default=300); p.add_argument('--psm',type=int,default=3); p.add_argument('--tesseract')
            p.add_argument('--backend',choices=['mineru-local','mineru','local'],default='mineru-local'); p.add_argument('--allow-upload',action='store_true')
            p.add_argument('--mineru-model',choices=['vlm','pipeline'],default='vlm'); p.add_argument('--mineru-api-base',default='https://mineru.net')
            p.add_argument('--mineru-wait',type=int,default=30); p.add_argument('--mineru-chunk-pages',type=int,default=100)
            p.add_argument('--mineru-no-ocr',action='store_true'); p.add_argument('--mineru-batch-id')
            p.add_argument('--mineru-local-root',default=os.environ.get('AINIEE_MINERU_ROOT')); p.add_argument('--mineru-local-cli')
            p.add_argument('--mineru-local-config'); p.add_argument('--mineru-local-env')
            p.add_argument('--mineru-local-timeout',type=float,default=3600)
            p.add_argument('--mineru-tier',choices=['standard','advanced'],default='standard')
            p.add_argument('--mineru-batch-pages',type=int,default=50); p.add_argument('--mineru-reference-pages',type=int,default=2)
    from mineru_flow import import_result
    p=sub.add_parser('import-mineru'); p.add_argument('input'); p.add_argument('--result',required=True); p.add_argument('--out',required=True); p.add_argument('--page-map'); p.set_defaults(func=import_result)
    p=sub.add_parser('draft'); p.add_argument('--work',required=True); p.set_defaults(func=draft)
    p=sub.add_parser('normalize'); p.add_argument('--work',required=True); p.add_argument('--plan'); p.set_defaults(func=normalize)
    p=sub.add_parser('prepare'); p.add_argument('--work',required=True); p.add_argument('--plan'); p.set_defaults(func=prepare)
    p=sub.add_parser('revise'); p.add_argument('--work',required=True); p.add_argument('--changes',required=True); p.set_defaults(func=revise)
    p=sub.add_parser('revise-structure'); p.add_argument('--work',required=True); p.add_argument('--plan',required=True); p.add_argument('--id-mapping',required=True); p.add_argument('--evidence',required=True); p.set_defaults(func=revise_structure_command)
    p=sub.add_parser('build'); p.add_argument('--book'); p.add_argument('--translation-manifest'); p.add_argument('--report-dir'); p.add_argument('--work',required=True); p.add_argument('--output',required=True); p.add_argument('--allow-unreviewed',action='store_true'); p.add_argument('--formula-renderer'); p.set_defaults(func=build)
    p=sub.add_parser('check'); p.add_argument('input'); p.add_argument('--epubcheck'); p.add_argument('--output'); p.set_defaults(func=check)
    args=parser.parse_args()
    try:
        result=args.func(args)
        return result if isinstance(result,int) else 0
    except (Exception,KeyboardInterrupt) as exc:
        if args.command=='extract' and args.backend=='mineru-local':
            # Model/source values can occur in import exceptions. Detailed
            # diagnostics stay in WORK; only a status is emitted publicly.
            import traceback
            import uuid
            logs=Path(args.out)/'mineru/local/errors'; logs.mkdir(parents=True,exist_ok=True)
            (logs/('flow-'+uuid.uuid4().hex+'.txt')).write_text(traceback.format_exc(),encoding='utf-8')
            cancelled=isinstance(exc,KeyboardInterrupt)
            state_path=Path(args.out)/'state.json'
            try: state=load(state_path) if state_path.exists() else {}
            except Exception: state={}
            state.update(stage='extraction-cancelled' if cancelled else 'extraction-failed',
                         default_backend='mineru-local',error_code=type(exc).__name__,content_verified=False)
            save(state_path,state)
            print('Local MinerU: status='+state['stage']+' check=failed',file=sys.stderr)
            return 130 if cancelled else 2
        if isinstance(exc,(ValueError,FileNotFoundError,KeyError)):
            print('ERROR: '+str(exc),file=sys.stderr); return 2
        raise
if __name__=='__main__': sys.exit(main())
