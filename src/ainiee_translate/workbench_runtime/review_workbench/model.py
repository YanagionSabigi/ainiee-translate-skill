"""Protocol validation and deterministic interpretation of human decisions."""
import copy
import hashlib
import json
import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path, PurePosixPath

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parent.parent
ID = re.compile(r'^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$')


class ReviewError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def validate_schema(data, name):
    schema = json.loads((ROOT/'schemas'/f'{name}.schema.json').read_text(encoding='utf-8'))
    errors = sorted(Draft202012Validator(schema).iter_errors(data), key=lambda e: str(e.path))
    if errors:
        e = errors[0]
        raise ReviewError(f"{'/'.join(map(str, e.path)) or name}: {e.message}")


def safe_path(root, relative):
    if not isinstance(relative, str) or '\\' in relative or ':' in relative:
        raise ReviewError('资源路径必须是包内相对路径')
    pure = PurePosixPath(relative)
    if pure.is_absolute() or '..' in pure.parts or not pure.parts:
        raise ReviewError('资源路径越界')
    root = Path(root).resolve()
    result = (root/relative).resolve()
    if not result.is_relative_to(root):
        raise ReviewError('资源路径越界')
    return result


def validate_package(data, root=None):
    validate_schema(data, 'package')
    for values, label in [(data['items'],'条目'),(data['groups'],'目录'),(data['assets'],'资源'),(data['facets'],'筛选')]:
        ids = [v['id'] for v in values]
        if len(ids) != len(set(ids)): raise ReviewError(f'{label}编号重复')
    groups = {g['id'] for g in data['groups']}
    assets = {a['id']: a for a in data['assets']}
    if len({a['path'] for a in assets.values()})!=len(assets):raise ReviewError('资源路径重复')
    facets = {f['id']: {v['id'] for v in f['options']} for f in data['facets']}
    for asset in assets.values():
        if not asset['path'].startswith('assets/'):raise ReviewError('资源必须放在 assets/ 目录')
        if root is not None:
            path = safe_path(root, asset['path'])
            if not path.is_file(): raise ReviewError(f"缺少资源：{asset['path']}")
            if asset.get('sha256') and hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:
                raise ReviewError('资源内容与审核基准不一致',409)
        else: safe_path(Path.cwd(), asset['path'])
        if asset.get('full_asset_id') and asset['full_asset_id'] not in assets:
            raise ReviewError('缺少整页资源')
    targets = {}
    for item in data['items']:
        if item['group_id'] not in groups: raise ReviewError('条目目录不存在')
        for key, values in item['facets'].items():
            if key not in facets or not set(values) <= facets[key]: raise ReviewError('筛选值不存在')
        expected = {b['id']: b['type'] for b in item['before']}
        for version in ('before', 'baseline', 'proposal', 'evidence'):
            blocks = item.get(version) or []
            if len({b['id'] for b in blocks}) != len(blocks): raise ReviewError('内容块编号重复')
            if version in ('baseline','proposal') and item.get(version) is not None:
                if {b['id']:b['type'] for b in blocks} != expected: raise ReviewError('对照版本内容块不对应')
            for b in blocks:
                if b['type'] == 'image' and b['asset_id'] not in assets: raise ReviewError('内容块资源不存在')
                if b['type']=='table' and len({len(row) for row in b['rows']}) > 1: raise ReviewError('表格每行列数必须相同')
        previous = targets.setdefault(item['target_id'], item['baseline'])
        if previous != item['baseline']: raise ReviewError('同一目标的基准不一致')
    return data


def validate_quotes(item, quotes):
    for q in quotes:
        if q['item_id'] != item['id']: raise ReviewError('引用条目不匹配')
        blocks = item.get(q['version']) or []
        block = next((b for b in blocks if b['id']==q['block_id']), None)
        if not block or block['type'] not in ('text','tex'): raise ReviewError('引用内容块不存在')
        # Offsets use Unicode code points; the browser converts from UTF-16.
        if q['start'] < 0 or q['end'] <= q['start'] or block['text'][q['start']:q['end']] != q['text']:
            raise ReviewError('引用位置与原文不一致')


def resolve_decision(item, draft):
    mode = draft.get('mode')
    result = {'item_id':item['id'], 'target_id':item['target_id'], 'action':mode}
    if mode in ('accept','keep'):
        blocks = item.get('proposal') if mode=='accept' else item['before']
        if blocks is None: raise ReviewError('此项没有推荐方案')
        result['blocks'] = copy.deepcopy(blocks)
    elif mode=='edit':
        if not draft.get('touched'): raise ReviewError('请填写修改内容')
        blocks = copy.deepcopy(item.get('proposal') or item['before'])
        editable = [b for b in blocks if b['type'] != 'image']
        if not editable: raise ReviewError('此项没有可编辑内容')
        edits = draft.get('edits', {})
        if set(edits) != {b['id'] for b in editable}: raise ReviewError('请完整填写所有可编辑内容块')
        for b in editable:
            value = edits[b['id']]
            if b['type']=='table':
                if not isinstance(value,list) or not value or any(not isinstance(row,list) or not row or any(not isinstance(c,str) for c in row) for row in value) or len({len(row) for row in value})!=1:
                    raise ReviewError('表格结构不合法')
                b['rows']=value
            else:
                if not isinstance(value,str) or not value.strip(): raise ReviewError('修改内容不能为空')
                b['text']=value
        result['blocks']=blocks
    elif mode=='comment':
        if not isinstance(draft.get('comment'),str) or not draft['comment'].strip(): raise ReviewError('请填写修改意见')
        validate_quotes(item,draft.get('quotes',[]))
        result.update(instruction=draft['comment'].strip(),quotes=copy.deepcopy(draft.get('quotes',[])),processing='needs_agent')
    else: raise ReviewError('请选择处理方式')
    if 'blocks' in result:
        validate_tex(tuple(b['text'] for b in result['blocks'] if b['type']=='tex'))
    return result


@lru_cache(maxsize=2048)
def validate_tex(texts):
    if not texts:return
    node=shutil.which('node')
    if not node:raise ReviewError('提交公式需要 Node.js；普通文本审核不受影响。可先用修改意见反馈。')
    try:
        result=subprocess.run([node,str(ROOT/'web/scripts/validate-tex.cjs')],input=json.dumps(texts).encode(),capture_output=True,timeout=8)
        payload=json.loads(result.stdout)
    except (OSError,ValueError,subprocess.TimeoutExpired) as exc:raise ReviewError('公式校验未完成，请检查本地 Node.js 和公式资源') from exc
    if result.returncode or not payload.get('valid'):
        raise ReviewError('公式无法渲染：'+str(payload.get('error','未知错误'))[:1000])


def has_human_draft(draft):
    return bool(draft.get('mode') or draft.get('comment','').strip() or draft.get('touched') or draft.get('quotes') or draft.get('edits'))
