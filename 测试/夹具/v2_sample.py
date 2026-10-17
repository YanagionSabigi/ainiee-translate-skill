"""Synthetic evidence for contract tests. These records are not real acceptance."""
import copy
import json
from pathlib import Path
import fitz
from ainiee_translate.artifact_io import write_json,sha256
from ainiee_translate.pdf_bridge import contract
from ainiee_translate.pdf_cache import book_to_cache_file,apply_cache_to_book
from ainiee_translate.pdf_review import export_review_tasks,import_review_results,build_translation_manifest
from ainiee_translate import cache_io
from ainiee_translate._vendor.ModuleFolders.Service.Cache.CacheProject import CacheProject


def make_bound(work,adjust=None):
    work=Path(work); work.mkdir(parents=True,exist_ok=True)
    pdf=work/'source.pdf'; doc=fitz.open(); doc.new_page();doc.new_page();p=doc.new_page(); p.insert_text((30,30),'One: Three objects. Two: Three objects. Note. Author (2020).')
    doc.set_toc([[1,'One',3],[1,'Two',3]]);doc.save(pdf); doc.close()
    provenance=[{'page':3,'bbox':[20,20,400,60]}]
    block=lambda id,text:dict(id=id,kind='paragraph',inline=[{'text':text}],provenance=copy.deepcopy(provenance))
    first=block('p1','Three objects.'); first['inline'] += [{'note':'n1','id':'rnote1','evidence':'synthetic association'}, {'citation':['bib1'],'id':'cite1','text':'Author (2020)','evidence':'synthetic author-year match'}]
    second=block('p2','Three objects.'); second['inline'] += [{'note':'n1','id':'rnote2','evidence':'synthetic cross chapter association'}, {'link':'p1','id':'cross1','text':'chapter one','evidence':'synthetic target'}]
    bib=block('bib1','Author (2020). Title.'); bib['role']='bibliography-entry'
    raw={'schema':'pdf-raw/1','pages':[]}
    review={'schema':'pdf-review/1','reviewed':False,'review_evidence':[]}
    write_json(work/'raw.json',raw); write_json(work/'review.json',review)
    write_json(work/'state.json',{'source_path':str(pdf.resolve()),'stage':'extracted'})
    write_json(work/'inspection.json',{'source_sha256':sha256(pdf),'page_count':3,'bookmarks':[[1,'One',3],[1,'Two',3]]})
    policy={'schema':'pdf-publication-input/1','source_sha256':sha256(pdf),
            'exclusions':[{'page':2,'role':'printed-toc','evidence':'synthetic printed contents'}],
            'excluded_pages':[2],'retained_regions':{}}
    book={'schema':'epub-book/1','source_sha256':sha256(pdf),'raw_sha256':sha256(work/'raw.json'),
          'metadata':{'title':'One','language':'zh'},'metadata_provenance':provenance,
          'source_name':pdf.name,'selected_pages':[3],'extraction':[],
          'reviewed':False,'review_evidence':[],'labels':{'contents':'目录','notes':'注释','return':'返回'},
          'issues':[],'omissions':[],'publication_input':policy,'structure_rules':{'publication':{
              'toc':{'source':'pdf-bookmarks','original_pages':[2],'placement':{'before':'c1'},
                     'evidence':'synthetic original position','entries':[{'bookmark_index':0,'target':'c1','level':1},{'bookmark_index':1,'target':'c2','level':1}],'omissions':[]},'images':[]}},
          'chapters':[{'id':'c1','title':'One','heading_provenance':provenance,'blocks':[first,bib]},
                      {'id':'c2','title':'Two','heading_provenance':provenance,'blocks':[second]}],
          'notes':[{'id':'n1','chapter':'c1','label':'1','original_label':'1','association_evidence':'synthetic note',
                    'blocks':[block('np','A note.')] }]}
    if adjust: adjust(book)
    book=contract().prepare_translation_book(book,work)
    contract().persist_source(book,work)
    cf=book_to_cache_file(book,storage_path='source.pdf')
    for item in cf.items:
        if item.extra['ainiee_pdf']['translation_policy']=='translate':
            item.translated_text={'One':'第一章','Two':'第二章','Three objects.':'三个物体。','A note.':'一条注释。','chapter one':'第一章','Author (2020)':'Author (2020)'}.get(item.source_text,item.source_text)
            item.translation_status=1
    project=CacheProject(files={'source.pdf':cf}); cache=work/'cache.json'; cache_io.save_cache(project,str(cache))
    glossary=work/'glossary.json'; prompt=work/'prompt.txt'; proof=work/'proof.json'
    write_json(glossary,{'characters':[],'terms':[],'non_translate':[]}); prompt.write_text('Translate faithfully into Chinese.',encoding='utf8')
    tasks=export_review_tasks(book,cf,work=work,prompt_path=prompt,glossary_path=glossary,context_id='synthetic-review',translation_context_id='synthetic-translator')
    results={'records':[dict(unit_id=u['unit_id'],source_sha256=u['source_sha256'],target_sha256=u['target_sha256'],context_id=tasks['context_id'],status='passed',findings=[],checks=tasks['required_checks'],evidence={'pdf_sha256':book['source_sha256'],'pages':[3],'observations':'Synthetic test evidence only'}) for u in tasks['units']]}
    ledger=import_review_results(book,cf,tasks,results,work=work,prompt_path=prompt,glossary_path=glossary)
    write_json(proof,ledger); cache_io.save_cache(project,str(cache))
    target=apply_cache_to_book(book,cf)
    context=dict(cache_path=cache,glossary_path=glossary,prompt_path=prompt,review_path=proof)
    manifest=build_translation_manifest(book,target,cf,work=work,**context)
    return book,target,cf,manifest,context
