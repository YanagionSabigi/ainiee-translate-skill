"""Explicit, source-keyed review evidence; never infer semantic families from spelling."""
import json
from pathlib import Path


def load_review_data(rows, path=None):
    if not path:
        # Legacy tables may contain homographs; index/hash binding keeps them distinct.
        return {}
    sources = [r.get('src') for r in rows]
    if any(not isinstance(s, str) or not s.strip() for s in sources) or len(set(sources)) != len(sources):
        raise ValueError('术语原词必须非空且唯一')
    result = {}
    if path:
        data = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(data, dict) or set(data) != {'terms'} or not isinstance(data['terms'], list):
            raise ValueError('审核信息必须为 terms 数组')
        for entry in data['terms']:
            if not isinstance(entry, dict) or set(entry) - {'src', 'category', 'context', 'page', 'base', 'requires_human'}:
                raise ValueError('审核信息含未知字段')
            source = entry.get('src')
            if not isinstance(source, str) or source not in sources or source in result:
                raise ValueError('审核信息原词重复或不存在')
            info = {k: entry.get(k, '') for k in ('category', 'context')}
            if any(not isinstance(v, str) for v in info.values()):
                raise ValueError('分类和上下文必须为文本')
            page = entry.get('page')
            if page is not None and (type(page) is not int or page < 1):
                raise ValueError('PDF 物理页码必须为从 1 开始的整数')
            info.update(source=source, page=page)
            if 'base' in entry:
                base = entry['base']
                if not isinstance(base, str) or base not in sources or base == source:
                    raise ValueError('派生基础词不存在或指向自身')
                info['base'] = base
            if type(entry.get('requires_human', False)) is not bool:
                raise ValueError('requires_human 必须为布尔值')
            result[source] = (info, entry.get('requires_human', False))
    # Flatten chains to the root family, rejecting cycles before preparing any output.
    for source, (info, _) in result.items():
        current, seen = info.get('base'), {source}
        while current:
            if current in seen:
                raise ValueError('派生关系形成循环')
            seen.add(current)
            parent = result.get(current, ({}, False))[0].get('base')
            if not parent:
                break
            current = parent
        if current:
            info['base'] = current
    return result


def term_review_info(row, metadata):
    info, required = metadata.get(row['src'], ({}, False))
    info = dict(source=row['src'], category=row.get('category', ''), context='', page=None) | info
    missing = not all(isinstance(info[k], str) and info[k].strip() for k in ('category', 'context')) or info['page'] is None
    return info, required or missing or not row.get('dst', '').strip()
