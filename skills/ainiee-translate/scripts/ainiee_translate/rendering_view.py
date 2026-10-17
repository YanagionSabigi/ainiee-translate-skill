"""Ephemeral template view of the bound epub-book/2, never a saved book model."""
from pathlib import Path
import mimetypes
from .pdf_bridge import contract, publisher_module
from .artifact_io import sha256


def rendering_view(book, *, manifest, work, asset_dir):
    if book.get('schema') != 'epub-book/2':
        raise ValueError('Template publication requires epub-book/2 binding')
    if manifest is None or work is None:
        raise ValueError('Formal publication requires a manifest and source WORK binding')
    contract().validate_translation_binding(book,manifest,work)
    source=contract().compile_relationships(book,manifest,work)
    source=publisher_module('epub_publication').apply_publication(source,work)
    # The publisher alone interprets PDF crops, returned assets and verified math.
    asset_dir=Path(asset_dir); asset_dir.mkdir(parents=True,exist_ok=True)
    material=publisher_module('epub_build').materialize_assets(source,Path(work),asset_dir,[],None)
    view={'schema':'ainiee-render/1','metadata':dict(source['metadata']),
          'translated_book_sha256':contract().content_digest(book),'translation_manifest_sha256':contract().content_digest(manifest),
          'source_sha256':source['source_sha256'],'translation_complete':True,
          'chapters':[],'blocks':[],'notes':[],'assets':[],
          'toc':{'placement':{'before':source['chapters'][0]['id']},'entries':[]},
          'provenance':{'work':str(asset_dir.resolve())},'publication_order':[]}
    for ident,entry in material.items():
        path=asset_dir/entry['href']; spec=entry['source']
        view['assets'].append(dict(id=ident,path=entry['href'],sha256=sha256(path),
            media_type=mimetypes.guess_type(path.name)[0] or 'image/png',width_em=spec.get('width_em',24)))
    references={}
    def textual(ident,items,chapter,kind='paragraph',**extra):
        text=[]; nodes={}
        for index,item in enumerate(items):
            if 'note' in item:
                node=dict(kind='note',note_id=item['note'],ref_id=item['id'],number=item.get('label',''))
                references.setdefault(item['note'],[]).append(item['id'])
            elif 'citation' in item:
                node=dict(kind='reference',targets=item['citation'],ref_id=item['id'],text=item.get('text',''),
                          target_labels=item.get('target_labels',[]))
                for target in item['citation']: references.setdefault(target,[]).append(item['id'])
            elif 'link' in item:
                node=dict(kind='reference',targets=[item['link']],ref_id=item.get('id',f'{ident}-ref-{index}'),text=item.get('text',''))
                references.setdefault(item['link'],[]).append(node['ref_id'])
            elif 'asset' in item:
                spec=item['asset']
                node=(dict(kind='math',tex=spec['tex'],verified=True) if spec.get('tex_verified') and spec.get('tex')
                      else dict(kind='image',asset_id=spec['id']))
            else:
                value=item.get('text','')
                if item.get('styles'):
                    node=dict(kind='styled',text=value,styles=item['styles'])
                elif '⟦AT:' in value or '<i>' in value or '</i>' in value or '<b>' in value or '</b>' in value:
                    node=dict(kind='literal',text=value)
                else:
                    text.append(value); continue
            token=f'⟦AT:inline:{ident}-{index}⟧'; text.append(token); nodes[token]=node
        value=''.join(text)
        result=dict(id=ident,chapter_id=chapter,kind=kind,source_text=value,target_text=value,
                    protected_tokens=list(nodes),inlines=nodes,**extra)
        view['blocks'].append(result)
        return result
    def convert(block,chapter):
        kind=block['kind']; ident=block['id']
        if kind=='table':
            if block.get('inline'): textual(ident+'-caption',block['inline'],chapter,'caption')
            rows=[]
            for ri,row in enumerate(block['rows']):
                cells=[]
                for ci,cell in enumerate(row):
                    if isinstance(cell,dict) and (cell.get('rowspan',1)!=1 or cell.get('colspan',1)!=1):
                        raise ValueError('Template semantic table spans need a reviewed table-image fallback')
                    inline=cell.get('inline',[]) if isinstance(cell,dict) else cell if isinstance(cell,list) else [{'text':cell}]
                    cid=f'{ident}-cell-{ri}-{ci}'; textual(cid,inline,chapter,'table-cell'); cells.append(cid)
                rows.append(cells)
            view['blocks'].append(dict(id=ident,chapter_id=chapter,kind='table',rows=rows))
        elif kind in ('figure','formula','table-image'):
            spec=block['asset']
            node=dict(id=ident,chapter_id=chapter,kind='formula' if kind=='formula' else 'figure',asset_id=spec['id'])
            if kind=='formula':
                node.update(tex=spec.get('tex'),verified=bool(spec.get('tex_verified')),fallback_reason='Publisher verified source resource')
            view['blocks'].append(node)
            if block.get('inline'): textual(ident+'-caption',block['inline'],chapter,'caption')
        elif kind in ('list','ordered-list'):
            # Preserve each item as a separate block, with explicit original order.
            textual(ident,[],chapter)
            for index,items in enumerate(block['items'],1):
                textual(f'{ident}-item-{index}',[{'text':f'{index}. ' if kind=='ordered-list' else '• '}]+items,chapter)
        elif kind in ('paragraph','heading','quote','verse'):
            textual(ident,block.get('inline',[]),chapter,kind,level=block.get('level',2))
        else: raise ValueError('Unsupported template content kind: '+kind)
    for chapter in source['chapters']:
        view['chapters'].append(dict(id=chapter['id'],source_title=chapter['title'],display_title=chapter['title'],note_order=[]))
        for block in chapter['blocks']: convert(block,chapter['id'])
    for note in source['notes']:
        start=len(view['blocks'])
        for block in note['blocks']: convert(block,note['chapter'])
        note_ids=[b['id'] for b in view['blocks'][start:] if b['kind']!='table-cell']
        view['notes'].append(dict(id=note['id'],chapter_id=note['chapter'],block_ids=note_ids,
            number=note['label'],original_label=note.get('original_label'),references=references.get(note['id'],[])))
        next(c for c in view['chapters'] if c['id']==note['chapter'])['note_order'].append(note['id'])
    view['reference_returns']={target:ids for target,ids in references.items() if target not in {n['id'] for n in source['notes']}}
    publication=source.get('publication')
    if publication:
        view['toc']['placement']=publication['toc']['placement']
        for chapter in publication['toc']['entries']:
            for entry in [chapter]+chapter['sections']:
                view['toc']['entries'].append(dict(target=entry['target'],level=1 if entry is chapter else 2,display_title=entry['title']))
        for image in publication['images']:
            view['publication_order'].append(dict(kind='front-image',role=image['role'],asset_id=image['asset']['id']))
    else:
        view['toc']['entries']=[dict(target=c['id'],level=1,display_title=c['title']) for c in source['chapters']]
    placement=view['toc']['placement']
    for chapter in source['chapters']:
        if placement.get('before')==chapter['id']: view['publication_order'].append(dict(kind='toc'))
        view['publication_order'].append(dict(kind='chapter',id=chapter['id']))
        if placement.get('after')==chapter['id']: view['publication_order'].append(dict(kind='toc'))
    return view
