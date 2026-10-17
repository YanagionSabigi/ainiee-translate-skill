"""Conservative review candidates from MinerU semantics; no inferred note binding."""
from html.parser import HTMLParser
import pdf_to_epub as p

def line_items(ids,index,separator=' '):
    result=[]
    for number,lid in enumerate(ids):
        if number and separator: result.append({'text':separator,'evidence':'Draft boundary separator; verify against source'})
        line=index[lid]; position=0
        for candidate in sorted((v for v in line.get('mineru_inline',[]) if v.get('asset')),key=lambda v:v.get('start',0)):
            start,end=candidate['start'],candidate['end']
            if not isinstance(start,int) or not isinstance(end,int) or not 0<=start<end<=len(p.text_of(line)):
                raise ValueError('MinerU inline candidate is outside source characters')
            if start<position: raise ValueError('Overlapping MinerU inline candidates')
            if start>position: result.append({'line':lid,'start':position,'end':start})
            if candidate.get('asset'): result.append({'asset':candidate['asset']})
            else: result.append({'line':lid,'start':start,'end':end})
            position=end
        if position<len(p.text_of(line)): result.append({'line':lid,'start':position})
    return result

class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True); self.rows=[]; self.row=None; self.cell=None; self.styles=[]; self.unsupported=False; self.depth=0; self.caption=[]; self.in_caption=False
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=='table':
            self.depth+=1
            if self.depth>1: self.unsupported=True
        elif tag=='tr': self.row=[]
        elif tag in {'td','th'}:
            try:
                self.cell={'inline':[],'header':tag=='th','rowspan':int(attrs.get('rowspan','1')),'colspan':int(attrs.get('colspan','1'))}
                if self.cell['rowspan']<1 or self.cell['colspan']<1: self.unsupported=True
            except ValueError: self.unsupported=True; self.cell={'inline':[]}
        elif tag in {'b','strong','i','em','u','sub','sup'}: self.styles.append({'b':'bold','strong':'bold','i':'italic','em':'italic','u':'underline'}.get(tag,tag))
        elif tag=='br': self.handle_data('\n')
        elif tag=='caption': self.in_caption=True
        elif tag not in {'thead','tbody','tfoot','caption','span','p','div'}: self.unsupported=True
    def handle_endtag(self,tag):
        if tag=='table': self.depth-=1
        elif tag=='caption': self.in_caption=False
        elif tag in {'td','th'}:
            if self.cell is not None and self.row is not None: self.row.append(self.cell)
            self.cell=None
        elif tag=='tr':
            if self.row: self.rows.append(self.row)
            self.row=None
        elif tag in {'b','strong','i','em','u','sub','sup'} and self.styles: self.styles.pop()
    def handle_data(self,data):
        item={'text':data,'styles':list(self.styles),'evidence':'MinerU returned table HTML; source comparison required'}
        if self.cell is not None: self.cell['inline'].append(item)
        elif self.in_caption: self.caption.append(item)

def candidate_blocks(raw):
    index=p.index_raw(raw); semantics=raw['semantic_blocks']; children={}
    for item in semantics:
        if item.get('parent_id'): children.setdefault(item['parent_id'],[]).append(item)
    def descendants(item):
        result=[item]
        for child in children.get(item['id'],[]): result+=descendants(child)
        return result
    blocks=[]; covered=set()
    for item in semantics:
        if item.get('parent_id'): continue
        family=descendants(item); foot_ids=set(item.get('footnote_sources',[]))
        ids=list(dict.fromkeys(item.get('sources',[]))); kind=item['type']
        block={'id':'candidate-'+item['id'],'kind':'paragraph','sources':ids,'mineru_blocks':[x['id'] for x in family],
               'semantic_role':item.get('mineru_type',kind),'source_region':{'page':item['page'],'bbox':item['bbox'],'evidence':'MinerU source geometry; review candidate'},
               'inline':line_items(ids,index)}
        if kind=='heading': block.update(kind='heading',level=max(2,min(6,item.get('heading_level') or 2)))
        elif kind in {'figure','formula','table'} and item.get('asset'):
            block['sources']=[s for s in ids if s not in foot_ids]
            block['inline']=line_items(item.get('caption_sources',[]),index)
            block['asset']=item['asset']; block['kind']={'figure':'figure','formula':'formula','table':'table-image'}[kind]
            if kind=='table' and item.get('table_html'):
                parser=TableParser(); parser.feed(item['table_html']); parser.close()
                if parser.rows and not parser.unsupported:
                    block.update(kind='table',rows=parser.rows,table_evidence='MinerU HTML candidate; verify cells/spans against source before review approval')
                    block.pop('asset',None)  # Cells render the table; do not materialize an unused image.
                    caption_text=''.join(x['text'] for x in parser.caption).strip()
                    separate_text=' '.join(p.text_of(index[s]) for s in item.get('caption_sources',[])).strip()
                    if caption_text and caption_text!=separate_text:
                        if block['inline']: block['inline'].append({'text':'\n','evidence':'Two distinct MinerU caption candidates; verify against source'})
                        block['inline']+=parser.caption
            if foot_ids:
                foot_sem=[x for x in family if set(x.get('sources',[])) and set(x['sources']).issubset(foot_ids)]
                block['mineru_blocks']=[s for s in block['mineru_blocks'] if s not in {x['id'] for x in foot_sem}]
                note_block={'id':block['id']+'-footnote','kind':'paragraph','sources':[s for s in ids if s in foot_ids],
                            'inline':line_items([s for s in ids if s in foot_ids],index),'mineru_blocks':[x['id'] for x in foot_sem],
                            'semantic_role':'visual-footnote-candidate'}
                blocks.append(block); covered.update(block['sources']); block=note_block
        elif kind in {'list','index'} and item.get('items'):
            block.update(kind='list',items=[line_items(group,index) for group in item['items']],inline=[])
        elif kind=='code': block['kind']='verse'; block['inline']=line_items(ids,index,'\n')
        blocks.append(block); covered.update(block['sources'])
    # Unknown/raw-only content stays visible. Nothing classified as discarded is silently omitted.
    for lid,line in index.items():
        if lid not in covered:
            blocks.append({'id':'remaining-'+lid,'kind':'paragraph','sources':[lid],'inline':line_items([lid],index),'semantic_role':line.get('role','unclassified')})
    return blocks
