"""Exact frozen-EPUB matching with reversible local string offsets."""
import copy
import html
import re
import unicodedata
from itertools import product
from bs4 import BeautifulSoup
from .artifact_io import digest
from .reading_round import (load_round, load_segments, load_issues, read, child, normalized,
                            round_lock, save_state, immutable, revision, record)


def normalize_with_offsets(text):
    units=[]
    for token in re.finditer(r'<[^>]*>|&(?:#\d+|#x[0-9a-fA-F]+|\w+);|.',text,re.S):
        raw=token.group()
        if raw.startswith('<') and raw.endswith('>'): continue
        for char in html.unescape(raw):
            if unicodedata.combining(char) and units:
                old,a,_=units.pop(); units.append((old+char,a,token.end()))
            else: units.append((char,token.start(),token.end()))
    chars=[]; offsets=[]
    for cluster,a,b in units:
        for char in unicodedata.normalize('NFC',cluster):
            if char.isspace():
                if not chars: continue
                if chars[-1]==' ':
                    offsets[-1]=(offsets[-1][0],b); continue
                char=' '
            chars.append(char); offsets.append((a,b))
    if chars and chars[-1]==' ': chars.pop(); offsets.pop()
    return ''.join(chars),offsets


def _candidates(round_dir,issue):
    r=load_round(round_dir); segments=load_segments(round_dir)
    blocks=read(child(round_dir,'edition/source-manifest.json'))['spine']
    query=normalize_with_offsets(issue['note']['excerpt'])[0]
    if not query: return []
    chapter_map=(r.get('style_profile') or {}).get('chapter_map',{})
    verified_href=chapter_map.get(str(issue['note'].get('chapter_uid')))
    groups={}
    for b in blocks:
        if verified_href and b['href']!=verified_href: continue
        groups.setdefault(b['href'],[]).append(b)
    found=[]
    for href,chapter in groups.items():
        for separator in (' ', ''):
            text=''; spans=[]
            for b in chapter:
                if text: text+=separator
                visible,unused=normalize_with_offsets(b['visible_text'])
                matching=[s for s in segments if any(l['href']==href and l['block_index']==b['block_index'] for l in s['locators'])]
                precise=[s for s in matching if s.get('item_id')==b['item_id']]
                matching=precise or matching
                begin=len(text); text+=visible
                spans.append((begin,len(text),matching,b))
            start=0
            while (pos:=text.find(query,start))>=0:
                stop=pos+len(query); start=pos+1; choices=[]; valid=True
                for a,b,ss,block in spans:
                    if b<=pos or a>=stop: continue
                    lo=max(pos,a)-a; hi=min(stop,b)-a
                    options=[]
                    for s in ss:
                        for locator in s['locators']:
                            if locator['href']!=href or locator['block_index']!=block['block_index']: continue
                            original=BeautifulSoup(s.get('original_html') or '', 'html.parser').find()
                            if original and original.get('id') and block.get('element_id') and original.get('id')!=block['element_id']: continue
                            norm,offsets=normalize_with_offsets(s['target_text'])
                            begin=locator.get('text_start',0); end=locator.get('text_end',begin+len(norm))
                            left=max(lo,begin); right=min(hi,end)
                            if left>=right or not offsets: continue
                            options.append((left,right,dict(segment_id=s['segment_id'],start=offsets[left-begin][0],
                                           end=offsets[right-begin-1][1],href=href,block_index=block['block_index'])))
                    # Full-overlap alternatives are ambiguity; disjoint inline pieces
                    # of the same rendered paragraph are one multi-segment selection.
                    boundaries=sorted({x for left,right,_ in options for x in (left,right)})
                    if not options: valid=False; break
                    for left,right in zip(boundaries,boundaries[1:]):
                        covering=[o for begin,end,o in options if begin<=left and end>=right]
                        if covering: choices.append(covering)
                if valid and choices:
                    # Keep bounded explicit alternatives, never select the best guess.
                    count=1
                    for options in choices: count*=len(options)
                    if count>256: continue
                    for combination in product(*choices):
                        selected=[]
                        for item in combination:
                            if item not in selected: selected.append(item)
                        if selected and selected not in found: found.append(selected)
    return found


def match_issues(round_dir):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir)
        for i in issues['issues']:
            if i['status'] not in ('needs_location','stale'): continue
            candidates=_candidates(round_dir,i)
            i['matching']=dict(edition_id=r['edition_id'],annotation_revision=i['annotation_revision'],
                               candidates=candidates,selected=candidates[0] if len(candidates)==1 else None)
            i['status']='needs_assessment' if len(candidates)==1 else 'needs_location'
        save_state(round_dir,r,issues)
        return issues


def record_match_override(round_dir,mapping):
    with round_lock(round_dir):
        r=load_round(round_dir); issues=load_issues(round_dir)
        issue=next((i for i in issues['issues'] if i['issue_id']==mapping.get('issue_id')),None)
        if (issue is None or mapping.get('edition_id')!=r['edition_id']
                or mapping.get('annotation_revision')!=issue['annotation_revision']
                or not mapping.get('actor','').strip() or not mapping.get('evidence','').strip()):
            raise ValueError('Location override needs current edition/revision, actor and location evidence')
        selected=mapping.get('segments')
        candidates=_candidates(round_dir,issue)
        if selected not in candidates:
            raise ValueError('Selected ranges do not match the frozen excerpt and candidate evidence')
        linked=mapping.get('linked_review_ids',[]); discarded=mapping.get('discarded_review_ids',[])
        if linked or discarded:
            possible={t['review_id']:t for t in issue['note'].get('link_candidates',[])}
            if (set(linked)&set(discarded) or not (set(linked)|set(discarded))<=set(possible)
                    or len(linked)!=len(set(linked)) or len(discarded)!=len(set(discarded))):
                raise ValueError('Thought-link resolution must select known candidate review IDs once')
            previous=r.get('link_overrides',{}).get(issue['external_key'],{})
            base=previous.get('external_note_sha256',digest(issue['note']))
            issue['note']['thoughts'].extend(copy.deepcopy(possible[k]) for k in linked)
            issue['note']['thoughts'].sort(key=lambda t:str(t['review_id']))
            issue['note']['link_candidates']=[t for k,t in possible.items() if k not in set(linked)|set(discarded)]
            issue['note']['needs_link']=bool(issue['note']['link_candidates'])
            r.setdefault('link_overrides',{})[issue['external_key']]=dict(external_note_sha256=base,
                resolved_note=copy.deepcopy(issue['note']),actor=mapping['actor'],evidence=mapping['evidence'])
        immutable(round_dir,'locations',revision(),record('reading-location/1',r,**mapping))
        issue['matching']=dict(edition_id=r['edition_id'],annotation_revision=issue['annotation_revision'],
                              candidates=candidates,selected=copy.deepcopy(selected),override=copy.deepcopy(mapping))
        issue['current_assessment_revision']=None
        issue['status']='needs_link' if issue['note'].get('needs_link') else 'needs_assessment'
        save_state(round_dir,r,issues)
        return issues
