"""MinerU-first routing, prepared PDF selections and source-bound result assembly."""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import pdf_to_epub as p

def page_mapping(value,count):
    """Unlike a selection, a derivative-to-source map has significant order."""
    result=[]
    for part in value.split(','):
        bounds=part.strip().split('-')
        if len(bounds)==1: group=[int(bounds[0])]
        elif len(bounds)==2:
            first,last=map(int,bounds)
            if first>last: raise ValueError('Page-map ranges must increase; use comma-separated pages for another order')
            group=list(range(first,last+1))
        else: raise ValueError('Invalid page-map range')
        if any(not 1<=n<=count for n in group): raise ValueError('Page map is outside source PDF')
        result.extend(group)
    return result

def remap_asset(spec, key):
    if spec:
        spec['id']=key+'-'+spec['id']

def remap_page(imported, task):
    """Namespace a returned derivative region without changing original records."""
    key=task['key']; pg=imported['pages'][0]
    if pg['page']!=task['page'] or len(pg['regions'])!=1:
        raise ValueError('MinerU imported page/region does not match prepared selection')
    region=deepcopy(pg['regions'][0]); region.update(id=key,route=task['route'])
    line_map={line['id']:f'{key}-l{i:04d}' for i,line in enumerate(region['lines'],1)}
    for line in region['lines']:
        line['id']=line_map[line['id']]
        if line.get('block'): line['block']=key+'-'+line['block']
        for candidate in line.get('mineru_inline',[]): remap_asset(candidate.get('asset'),key)
    semantic=[]
    for original in imported.get('semantic_blocks',[]):
        if original['page']!=task['page']: continue
        item=deepcopy(original); item['id']=key+'-'+item['id']
        for field in ('sources','caption_sources','footnote_sources'):
            if field in item: item[field]=[line_map[s] for s in item[field]]
        if item.get('parent_id'): item['parent_id']=key+'-'+item['parent_id']
        if 'children' in item: item['children']=[key+'-'+s for s in item['children']]
        if 'items' in item: item['items']=[[line_map[s] for s in group] for group in item['items']]
        remap_asset(item.get('asset'),key); semantic.append(item)
    return region,semantic,line_map

def mineru_language(value):
    return {'eng':'en','chi_sim':'ch','chi_sim+eng':'ch','eng+chi_sim':'ch',
            'chi_tra':'chinese_cht','chi_tra+eng':'chinese_cht'}.get(value,value)

def prepared_input(doc, source, tasks, directory):
    if len(tasks)==len(doc) and all(t['page']==i+1 and not t.get('clip') for i,t in enumerate(tasks)):
        return source
    key=p.digest({'source':p.sha(source),'selection':tasks})[:24]
    target=directory/(key+'.pdf'); directory.mkdir(parents=True,exist_ok=True)
    if target.exists(): return target
    derivative=p.pdf_module().open()
    for task in tasks:
        n=task['page']-1
        if task.get('clip'):
            rect=p.rect_check(doc[n],task['clip'])
            page=derivative.new_page(width=rect.width,height=rect.height)
            page.show_pdf_page(page.rect,doc,n,clip=rect)
        else: derivative.insert_pdf(doc,from_page=n,to_page=n)
    derivative.save(target,garbage=3,deflate=True,no_new_id=True); derivative.close()
    return target

def write_state(work, source, raw, jobs, reused=0):
    failures=raw.get('failures',[])
    p.save(work/'raw.json',raw)
    p.save(work/'state.json',{'source_path':str(source),'source_sha256':raw['source_sha256'],
        'selected_pages':raw['selected_pages'],'stage':'extraction-failed' if failures else 'extracted',
        'cached_regions_reused':reused,'failures':failures,'mineru_jobs':jobs,'default_backend':'mineru'})

def import_result(args):
    from mineru_import import read_bundle
    source=Path(args.input).resolve(); work=Path(args.out); work.mkdir(parents=True,exist_ok=True)
    doc=p.pdf_module().open(source)
    mapping=page_mapping(args.page_map,len(doc)) if args.page_map else None
    doc.close()
    raw=read_bundle(args.result,work,source,page_map=mapping)
    write_state(work,source,raw,[],0)
    print(f'Imported MinerU structured result: {len(raw["pages"])} pages -> {work}/raw.json')

def extract(args):
    from mineru_backend import ensure_bundle
    from mineru_import import read_bundle
    source=Path(args.input).resolve(); work=Path(args.out); work.mkdir(parents=True,exist_ok=True)
    doc=p.pdf_module().open(source); selection=p.pages(args.pages,len(doc))
    routes=p.load(args.routes) if args.routes else {}
    records={n:{'page':n,'width':doc[n-1].rect.width,'height':doc[n-1].rect.height,'regions':[]} for n in selection}
    mineru_tasks=[]; semantic=[]; jobs=[]; failures=[]; reused=0; results=[]
    for n in selection:
        configs=routes.get(str(n),[{'method':'mineru'}]); rects=[]
        if not configs: raise ValueError(f'Page {n}: empty routing list')
        for ri,route in enumerate(configs,1):
            rect=p.rect_check(doc[n-1],route.get('bbox'))
            if any((rect&other).get_area()>.1 for other in rects): raise ValueError(f'Page {n}: overlapping extraction regions')
            rects.append(rect); key=f'p{n:04d}-r{ri:02d}'; method=route.get('method','mineru')
            if method in {'mineru','auto'}:
                if route.get('rotation'): raise ValueError('MinerU region rotation needs a separately verified derivative; do not silently change source geometry')
                mineru_tasks.append({'page':n,'clip':list(rect) if route.get('bbox') else None,'key':key,'route':route})
                continue
            # Explicit native/OCR routes preserve the local implementation and its caches.
            if method not in {'native','ocr'}: raise ValueError('Unknown extraction route: '+method)
            region={'id':key,'bbox':list(rect),'route':route,'method':method,'status':'failed','lines':[],'issues':[]}
            language={'ch':'chi_sim+eng','en':'eng','chinese_cht':'chi_tra+eng'}.get(args.language,args.language)
            fingerprint=p.digest({'local':'1.0.0','pdf':p.sha(source),'page':n,'route':route,'language':language,
                                  'dpi':args.dpi,'psm':args.psm,'tesseract':p.tesseract_path(args.tesseract)})
            cache=work/'cache'/(key+'.json'); old=p.load(cache) if cache.exists() else {}
            if old.get('fingerprint')==fingerprint and old.get('status')=='complete': region=old; reused+=1
            else:
                try:
                    try:
                        lines=p.native(doc[n-1],rect) if method=='native' else p.ocr(doc[n-1],rect,work,key,p.tesseract_path(args.tesseract),language,args.dpi,route.get('psm',args.psm),route.get('rotation',0))
                        if not lines: raise ValueError(method+' returned no text')
                    except Exception as exc:
                        if method!='native' or route.get('fallback')!='ocr': raise
                        region['issues'].append('Native failure -> OCR: '+str(exc)); method='ocr'
                        lines=p.ocr(doc[n-1],rect,work,key,p.tesseract_path(args.tesseract),language,args.dpi,route.get('psm',args.psm),route.get('rotation',0))
                    for li,line in enumerate(lines,1): line.update(id=f'{key}-l{li:04d}',source={'page':n,'bbox':line['bbox'],'method':method})
                    region.update(method=method,status='complete',lines=lines)
                except Exception as exc: region['error']=str(exc)
                region['fingerprint']=fingerprint; p.save(cache,region)
            records[n]['regions'].append(region)
    # Whole-page tasks batch together; clipped regions are isolated so their geometry stays unambiguous.
    batches=[]; pending=[]
    limit=args.mineru_chunk_pages
    if not 1<=limit<=100: raise ValueError('MinerU chunk size must be 1..100 pages')
    for task in mineru_tasks:
        if task['clip']:
            if pending: batches.append(pending); pending=[]
            batches.append([task])
        else:
            pending.append(task)
            if len(pending)>=limit: batches.append(pending); pending=[]
    if pending: batches.append(pending)
    # PDF size is checked after slicing. Split oversized batches, never upload unrelated pages.
    for batch in list(batches):
        path=prepared_input(doc,source,batch,work/'mineru/inputs')
        if path.stat().st_size>190_000_000:
            if len(batch)==1: raise ValueError('A single selected page exceeds safe MinerU upload size')
            batches.remove(batch)
            for task in batch:
                small=prepared_input(doc,source,[task],work/'mineru/inputs')
                if small.stat().st_size>190_000_000: raise ValueError('A single selected page exceeds safe MinerU upload size')
                batches.append([task])
    if args.mineru_batch_id and len(batches)!=1: raise ValueError('--mineru-batch-id can adopt only one explicitly matching selection')
    for bi,batch in enumerate(batches):
        path=prepared_input(doc,source,batch,work/'mineru/inputs')
        options={'model':args.mineru_model,'language':mineru_language(args.language),'ocr':not args.mineru_no_ocr,'api_base':args.mineru_api_base}
        result=ensure_bundle(path,work/'mineru/jobs',options,allow_upload=args.allow_upload,
                             wait_seconds=args.mineru_wait,batch_id=args.mineru_batch_id)
        jobs.append({k:str(result[k]) if isinstance(result[k],Path) else result[k] for k in ['status','batch_id','request_fingerprint','checkpoint','progress','message'] if k in result})
        if result['status']=='done':
            boxes=[t['clip'] or list(doc[t['page']-1].rect) for t in batch]
            imported=read_bundle(result['bundle'],work,source,page_map=[t['page'] for t in batch],source_boxes=boxes)
            if len(imported['pages'])!=len(batch): raise ValueError('MinerU returned page count does not match prepared selection')
            result_metadata=deepcopy(imported.get('mineru',{})); result_metadata['regions']=[]
            for task,pg in zip(batch,imported['pages']):
                region,items,line_map=remap_page(dict(imported,pages=[pg]),task)
                records[task['page']]['regions'].append(region)
                semantic.extend(items)
                result_metadata['regions'].append({'region':task['key'],'page':task['page'],'line_map':line_map})
                reused+=int(bool(result.get('cached')))
            results.append(result_metadata)
        else:
            error=result.get('message') or result.get('error') or ('MinerU '+result['status']+'; resume with the same arguments; no fallback was selected')
            for task in batch:
                records[task['page']]['regions'].append({'id':task['key'],'bbox':task['clip'] or list(doc[task['page']-1].rect),'method':'mineru','route':task['route'],'status':'failed','lines':[],'issues':[],'error':error})
    doc.close()
    for record in records.values():
        record['regions'].sort(key=lambda r:r['id'])
        for region in record['regions']:
            if region['status']=='failed': failures.append({'region':region['id'],'error':region.get('error')})
    raw={'schema':'pdf-raw/1','source_name':source.name,'source_sha256':p.sha(source),'selected_pages':selection,
         'pages':[records[n] for n in selection],'failures':failures,'semantic_blocks':semantic,
         'backend':'mineru','mineru_jobs':jobs,'mineru_result':results}
    write_state(work,source,raw,jobs,reused)
    print(f'MinerU extraction: {len(selection)} pages; {len(semantic)} semantic blocks; {len(failures)} unresolved regions -> {work}/raw.json')
    return 2 if failures else 0
