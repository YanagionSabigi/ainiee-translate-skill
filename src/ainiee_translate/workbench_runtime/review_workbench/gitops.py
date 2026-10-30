"""Scope-limited Git checkpoints without changing HEAD or the user's index."""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path

from .model import ReviewError, validate_package, safe_path
from .storage import Store, atomic_json, read_json, fingerprint


def git(root,*args,env=None,check=True,input=None):
    result=subprocess.run(['git','-C',str(root),*args],capture_output=True,input=input,env=env)
    if check and result.returncode:
        raise ReviewError('Git: '+result.stderr.decode('utf-8',errors='replace').strip())
    return result


def snapshot(project,paths,label):
    project=Path(project).resolve()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',label): raise ReviewError('Git 基准标识不合法')
    if git(project,'rev-parse','--is-inside-work-tree',check=False).returncode:
        git(project,'init')
    repo=Path(git(project,'rev-parse','--show-toplevel').stdout.decode().strip()).resolve()
    normalized=[]
    for name in paths:
        path=safe_path(project,name)
        if not path.is_file() or path.is_symlink() or '.git' in path.relative_to(repo).parts:
            raise ReviewError('校对范围只能包含明确的普通文件')
        relative=path.relative_to(repo).as_posix()
        if git(repo,'check-ignore','-q','--',relative,check=False).returncode==0:
            raise ReviewError(f'文件被 Git 忽略，请调用方先整理材料：{relative}')
        normalized.append(relative)
    if not normalized: raise ReviewError('校对范围不能为空')
    gitdir=Path(git(repo,'rev-parse','--absolute-git-dir').stdout.decode().strip())
    fd,name=tempfile.mkstemp(prefix='review-index-',dir=gitdir);os.close(fd);os.unlink(name)
    env={**os.environ,'GIT_INDEX_FILE':name}
    try:
        head=git(repo,'rev-parse','--verify','HEAD',check=False)
        if head.returncode==0: git(repo,'read-tree','HEAD',env=env)
        else: git(repo,'read-tree','--empty',env=env)
        git(repo,'add','--',*normalized,env=env)
        tree=git(repo,'write-tree',env=env).stdout.decode().strip()
        args=['commit-tree',tree]
        if head.returncode==0: args+=['-p',head.stdout.decode().strip()]
        commit=git(repo,*args,input=f'Review baseline: {label}\n'.encode()).stdout.decode().strip()
        git(repo,'update-ref',f'refs/review-workbench/{label}',commit)
        return commit
    finally:
        if os.path.exists(name):os.unlink(name)


def prepare(project,input_path,scope_path,destination):
    project=Path(project).resolve();source=Path(input_path).resolve();destination=Path(destination).resolve()
    if not destination.is_relative_to(project): raise ReviewError('审核包必须位于明确的项目目录内')
    if destination.exists(): raise ReviewError('输出审核包已存在，请为新一轮使用新目录')
    data=validate_package(read_json(source),source.parent)
    scope=read_json(scope_path)
    if not isinstance(scope,list) or not all(isinstance(p,str) for p in scope): raise ReviewError('scope 必须是相对文件路径数组')
    # Prepare validates the scope before creating any output.
    for p in scope:
        if not safe_path(project,p).is_file():raise ReviewError('校对范围文件不存在')
    destination.mkdir(parents=True)
    try:
        data=copy.deepcopy(data)
        for asset in data['assets']:
            src=safe_path(source.parent,asset['path']);dst=safe_path(destination,asset['path'])
            dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
            asset['sha256']=hashlib.sha256(dst.read_bytes()).hexdigest()
        data['base_commit']=None
        ref='round-'+uuid.uuid4().hex
        data['git']={'ref':f'refs/review-workbench/{ref}','scope':scope,'portable':False}
        atomic_json(destination/'package.json',data)
        own=[(destination/'package.json').relative_to(project).as_posix()]+[safe_path(destination,a['path']).relative_to(project).as_posix() for a in data['assets']]
        sha=snapshot(project,list(dict.fromkeys(scope+own)),ref)
        data['base_commit']=sha
        atomic_json(destination/'package.json',data)
        Store(destination)
        return data
    except Exception:
        # Leave generated materials for inspection; never remove business files.
        raise


def verify_baseline(root,data):
    if not data.get('base_commit'): raise ReviewError('审核包缺少 Git 基准')
    root=Path(root).resolve()
    if data.get('git',{}).get('portable'):
        repo=root;commit=data['git']['ref']
    else:
        result=git(root,'rev-parse','--show-toplevel',check=False)
        if result.returncode:raise ReviewError('找不到审核包的 Git 仓库')
        repo=Path(result.stdout.decode().strip());commit=data['base_commit']
    if git(repo,'cat-file','-e',commit+'^{commit}',check=False).returncode:
        raise ReviewError('Git 基准不存在')
    relative=(root/'package.json').relative_to(repo).as_posix()
    historical=git(repo,'show',f'{commit}:{relative}',check=False)
    if historical.returncode:raise ReviewError('Git 基准中缺少审核材料')
    material=json.loads(historical.stdout.decode('utf-8'))
    # base_commit cannot include its own commit ID; metadata is filled after checkpoint.
    for key in ('base_commit','origin_commit','git'): material.pop(key,None)
    expected=copy.deepcopy(data)
    for key in ('base_commit','origin_commit','git'): expected.pop(key,None)
    if material!=expected:raise ReviewError('审核材料与 Git 基准不一致',409)


def text_of(blocks):
    return '\n'.join((b.get('text') if b['type'] in ('text','tex') else json.dumps(b.get('rows') if b['type']=='table' else {'asset_id':b['asset_id']},ensure_ascii=False,sort_keys=True)) for b in blocks)


def git_diff(before,after):
    with tempfile.TemporaryDirectory(prefix='review-diff-') as tmp:
        a=Path(tmp)/'base.txt';b=Path(tmp)/'result.txt';a.write_text(text_of(before),encoding='utf-8');b.write_text(text_of(after),encoding='utf-8')
        result=subprocess.run(['git','diff','--no-index','--no-ext-diff','--no-textconv','--',str(a),str(b)],capture_output=True)
        if result.returncode not in (0,1):raise ReviewError('Git diff 执行失败')
        lines=result.stdout.decode('utf-8',errors='replace').splitlines()
        return '\n'.join(line for line in lines if not line.startswith(('diff --git','index ','--- ','+++ ')))


def compare(root,current):
    from .history import active_entries,signature
    store=Store(root);data=store.package
    verify_baseline(root,data)
    if not isinstance(current,dict) or current.get('package_id')!=data['package_id'] or current.get('base_commit')!=data['base_commit']:
        raise ReviewError('当前工作稿投影的审核包或 Git 基准不匹配',409)
    targets=current.get('targets',[])
    if not isinstance(targets,list) or any(not isinstance(t,dict) or set(t)!={'target_id','blocks'} for t in targets):raise ReviewError('工作稿投影格式错误')
    if len({t['target_id'] for t in targets})!=len(targets):raise ReviewError('工作稿目标重复')
    by_target={t['target_id']:t['blocks'] for t in targets}
    items={i['id']:i for i in data['items']}
    with store.lock():
        revision=store._drafts()['revision']
        submissions=store.submissions()
        history_hash=fingerprint(submissions)
    results=[];conflicts=[];seen={}
    for submission,d in active_entries(submissions):
            item=items[d['item_id']];target=d['target_id']
            entry={'item_id':d['item_id'],'target_id':target,'submission_id':submission['submission_id'],
                   'action':d['action'],'baseline':item['baseline'],'decision':d}
            if d['action']=='comment':entry['status']='needs_agent'
            elif target not in by_target:entry['status']='missing_current'
            else:
                actual=by_target[target];desired=d['blocks'];base=item['baseline']
                # Validate current blocks against the same block schema and identity.
                probe=copy.deepcopy(data);probe['items']=[copy.deepcopy(item)]
                probe['items'][0]['proposal']=actual;validate_package(probe,root)
                entry['current']=actual
                entry['status']='satisfied' if actual==desired else 'ready' if actual==base else 'conflict'
                entry['diff']=git_diff(actual,desired)
                prior=seen.setdefault(target,[])
                if any(p['blocks']!=desired for p in prior):
                    conflicts.append({'target_id':target,'reason':'different_human_decisions','submission_ids':list(dict.fromkeys([p['submission_id'] for p in prior]+[submission['submission_id']]))})
                    entry['status']='conflict'
                    for old in results:
                        if old['target_id']==target and old['action']!='comment':old['status']='conflict'
                prior.append({'blocks':desired,'submission_id':submission['submission_id']})
                if entry['status']=='conflict':conflicts.append({'target_id':target,'item_id':item['id'],'reason':'diverged','submission_ids':[submission['submission_id']]})
            results.append(entry)
    grouped={}
    for entry in results:grouped.setdefault(entry['target_id'],[]).append(entry)
    for target,entries in grouped.items():
        if len({signature(e['decision']) for e in entries})>1:
            for entry in entries:entry['status']='conflict'
            if not any(c['target_id']==target and c['reason']=='different_human_decisions' for c in conflicts):
                conflicts.append({'target_id':target,'reason':'different_human_decisions','submission_ids':[e['submission_id'] for e in entries]})
    output={'package_id':data['package_id'],'base_commit':data['base_commit'],'items':results,'conflicts':conflicts}
    with store.lock():
        if store._drafts()['revision']!=revision or fingerprint(store.submissions())!=history_hash:
            raise ReviewError('比较期间审核结果已更新，请重新运行比较',409)
        atomic_json(store.root/'comparison.json',output)
    return output
