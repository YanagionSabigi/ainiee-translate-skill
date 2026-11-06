"""Plan figure placement after reviewed or explicit body references.

The caller supplies one chapter or note container at a time. No source objects
are changed: captions in ``inline`` remain on their figure, and explicitly
bound ``caption_for`` paragraphs move as intact siblings after that figure.
"""
from __future__ import annotations

from collections import defaultdict
import re
import unicodedata


_LABEL = re.compile(
    r'(?:图|(?<![a-z0-9])(?:figure|fig\.?))\s*'
    r'(?P<number>\d+(?:\s*[-.]\s*\d+)*)'
    r'(?![a-z0-9]|\s*[-.]\s*\d)', re.IGNORECASE)


def _text(block):
    return ''.join(item.get('text', '') for item in block.get('inline', [])
                   if 'note' not in item and 'asset' not in item)


def _normalized(text):
    return unicodedata.normalize('NFKC', text).translate(str.maketrans({'–': '-', '—': '-', '−': '-'}))


def _label(block):
    declared = block.get('figure_label')
    if 'figure_label' in block and not isinstance(declared, str):
        raise ValueError(f'Figure {block["id"]}: figure_label must be a string')
    text = _normalized(declared if declared is not None else _text(block)).strip()
    match = _LABEL.match(text)
    if declared is not None and (not match or match.end() != len(text)):
        raise ValueError(f'Figure {block["id"]}: invalid figure_label; use a complete figure label')
    return re.sub(r'\s+', '', match['number']) if match else None


def _caption_role(block):
    return any('caption' in str(block.get(field, '')).lower()
               for field in ('semantic_role', 'role')) or block.get('kind') == 'caption'


def _body(block):
    return (block.get('kind') in {'paragraph', 'quote'}
            and 'caption_for' not in block and not _caption_role(block))


def _references_figure(item, ident):
    return (item.get('link') == ident or
            (item.get('relation_kind') == 'crossref' and
             isinstance(item.get('citation'), list) and ident in item['citation']))


def plan_figure_layout(blocks: list[dict]) -> tuple[list[dict], list[dict]]:
    """Return ordered blocks and auditable placements, or fail without guessing.

    Anchors resolve by ``after_block`` plus ``placement_evidence``, otherwise
    the earliest inline ``link`` or unique caption/declared-label mention.
    Repeated figure labels require explicit reviewed anchors. The first body
    paragraph or quote that mentions a figure wins; original body order and
    the original figure order for a shared anchor are preserved.
    """
    by_id = {}
    for block in blocks:
        ident = block.get('id')
        if not isinstance(ident, str) or not ident or ident in by_id:
            raise ValueError('Figure placement requires unique nonempty block IDs')
        by_id[ident] = block
    figures = [b for b in blocks if b.get('kind') == 'figure']
    figure_ids = {b['id'] for b in figures}
    captions = defaultdict(list)
    caption_ids = set()
    for block in blocks:
        if 'caption_for' in block:
            target = block['caption_for']
            if block.get('kind') != 'paragraph' or not isinstance(target, str) or target not in figure_ids:
                raise ValueError(f'Block {block["id"]}: caption_for requires a same-container figure and paragraph caption')
            captions[target].append(block)
            caption_ids.add(block['id'])
        elif (block.get('kind') != 'figure' and _caption_role(block) and
              not any(word in str(block.get(field, '')).lower()
                      for word in ('table', 'formula') for field in ('semantic_role', 'role'))):
            raise ValueError(f'Block {block["id"]}: detached caption needs an explicit caption_for figure binding')

    labels = {}
    for figure in figures:
        candidates = {_label(b) for b in [figure, *captions[figure['id']]]}
        candidates.discard(None)
        if len(candidates) > 1:
            raise ValueError(f'Figure {figure["id"]}: conflicting bound caption labels need source review')
        labels[figure['id']] = next(iter(candidates), None)
    label_owners = defaultdict(list)
    for ident, label in labels.items():
        if label is not None:
            label_owners[label].append(ident)
    body = [b for b in blocks if _body(b)]
    caption_texts = {re.sub(r'\s+', ' ', _normalized(_text(b))).strip()
                     for figure in figures for b in [figure, *captions[figure['id']]] if _text(b).strip()}
    for block in body:
        if re.sub(r'\s+', ' ', _normalized(_text(block))).strip() in caption_texts:
            raise ValueError(f'Block {block["id"]}: text duplicates a figure caption; review caption_for binding')
    body_labels = {b['id']: {re.sub(r'\s+', '', match['number'])
                              for match in _LABEL.finditer(_normalized(_text(b)))} for b in body}
    after = defaultdict(list)
    placements = []
    for figure in figures:
        ident = figure['id']
        label = labels[ident]
        if 'after_block' in figure:
            target = figure['after_block']
            anchor = by_id.get(target) if isinstance(target, str) else None
            evidence = figure.get('placement_evidence')
            if not isinstance(evidence, str) or not evidence.strip():
                raise ValueError(f'Figure {ident}: after_block needs nonempty placement_evidence')
            if anchor is None or not _body(anchor):
                raise ValueError(f'Figure {ident}: after_block must name a body paragraph/quote in the same container')
            method = 'explicit'
        else:
            if label is not None and len(label_owners[label]) > 1:
                raise ValueError(f'Figure {ident}: ambiguous figure label {label}; supply reviewed after_block')
            anchor = next((b for b in body if any(_references_figure(item, ident)
                          for item in b.get('inline', [])) or
                          label is not None and label in body_labels[b['id']]), None)
            if anchor is None:
                if label is None:
                    raise ValueError(f'Figure {ident}: no figure label or explicit reference; supply reviewed after_block')
                raise ValueError(f'Figure {ident}: no body mention of figure label {label}; supply reviewed after_block')
            method = 'link' if any(_references_figure(item, ident) for item in anchor.get('inline', [])) else 'label'
        after[anchor['id']].append(figure)
        record = {'figure': ident, 'after_block': anchor['id'], 'method': method,
                  'caption_blocks': [b['id'] for b in captions[ident]]}
        if label is not None:
            record['label'] = label
        placements.append(record)

    ordered = []
    for block in blocks:
        if block['id'] in figure_ids or block['id'] in caption_ids:
            continue
        ordered.append(block)
        for figure in after[block['id']]:
            ordered.append(figure)
            ordered.extend(captions[figure['id']])
    return ordered, placements
