"""Portable, allowlisted exports and data-only imports."""
import copy
import json
import os
import shutil
import stat
import subprocess
import tempfile
import zipfile
from pathlib import Path

from .model import ROOT, ReviewError, validate_schema, resolve_decision, safe_path, has_human_draft
from .storage import Store, atomic_json, read_json, fingerprint
from .gitops import git, snapshot, verify_baseline


def copy_runtime(destination):
    destination=Path(destination)
    for folder in ('review_workbench','web','schemas','examples','skill'):
        shutil.copytree(ROOT/folder,destination/folder,ignore=shutil.ignore_patterns('__pycache__','*.pyc'))
    shutil.copyfile(ROOT/'requirements.txt',destination/'requirements.txt')
    shutil.copyfile(ROOT/'LICENSE',destination/'LICENSE')


def export_skill(output):
    output=Path(output).resolve()
    if output.exists():raise ReviewError('安装包已存在，请换一个文件名')
    output.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='review-skill-',dir=output.parent) as tmp:
        base=Path(tmp);target=base/'review-workbench'
        shutil.copytree(ROOT/'skill/review-workbench',target)
        copy_runtime(target/'runtime')
        with zipfile.ZipFile(output,'w',zipfile.ZIP_DEFLATED) as archive:
            for file in base.rglob('*'):
                if file.is_file():archive.write(file,file.relative_to(base).as_posix())
    return output


def result_envelope(store):
    return {'schema_version':'1','package_id':store.package['package_id'],'base_commit':store.package['base_commit'],'submissions':store.submissions()}


def export_package(root,output,results_only=False,wheels=False):
    store=Store(root);output=Path(output).resolve()
    if output.exists():raise ReviewError('导出文件已存在，请换一个文件名')
    output.parent.mkdir(parents=True,exist_ok=True)
    verify_baseline(store.root,store.package)
    with tempfile.TemporaryDirectory(prefix='review-export-',dir=output.parent) as tmp:
        stage=Path(tmp)
        with store.lock():
            draft=copy.deepcopy(store._drafts());submissions=store.submissions();data=copy.deepcopy(store.package)
            if results_only:atomic_json(stage/'results.json',result_envelope(store))
            else:
                data['origin_commit']=data.get('origin_commit') or data['base_commit']
                data['git']={'ref':'refs/review-workbench/portable','scope':['package.json']+[a['path'] for a in data['assets']],'portable':True}
                atomic_json(stage/'package.json',data)
                for asset in data['assets']:
                    src=safe_path(store.root,asset['path']);dst=safe_path(stage,asset['path'])
                    dst.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(src,dst)
                draft['material_hash']=fingerprint(data);atomic_json(stage/'drafts.json',draft)
                for s in submissions:atomic_json(stage/'submissions'/f"{s['submission_id']}.json",s)
        if not results_only:
            copy_runtime(stage)
            (stage/'start_review.py').write_text('from pathlib import Path\nfrom review_workbench.__main__ import main\nimport sys\nif __name__ == "__main__":\n    main(["serve",str(Path(__file__).resolve().parent),*sys.argv[1:]])\n',encoding='utf-8')
            (stage/'OPEN-ME.txt').write_text('校对包\n\n需要 Python 3.11+ 和 Git；提交公式决定还需 Node.js（无需 npm）。\n首次运行：python -m pip install -r requirements.txt\n启动：python start_review.py\n\n离线依赖（若含 wheels/）：python -m pip install --no-index --find-links wheels -r requirements.txt\n\n回传结果：python -m review_workbench export . --results-only --out ../results.zip\n也可在网页“记录”中下载结果 JSON。\n',encoding='utf-8')
            if wheels:
                result=subprocess.run([os.sys.executable,'-m','pip','download','--only-binary=:all:','-r',str(stage/'requirements.txt'),'-d',str(stage/'wheels')],capture_output=True)
                if result.returncode:raise ReviewError('下载离线依赖失败：'+result.stderr.decode(errors='replace'))
            git(stage,'init');git(stage,'config','user.name','Review Workbench');git(stage,'config','user.email','review-workbench@localhost')
            snapshot(stage,data['git']['scope'],'portable')
        # Create the ZIP outside stage to avoid recursively including itself.
        fd,pending=tempfile.mkstemp(prefix='.review-export-',suffix='.zip',dir=output.parent);os.close(fd)
        try:
            with zipfile.ZipFile(pending,'w',zipfile.ZIP_DEFLATED) as archive:
                for path in stage.rglob('*'):
                    if path.is_file():archive.write(path,path.relative_to(stage).as_posix())
            os.replace(pending,output)
        finally:
            if os.path.exists(pending):os.unlink(pending)
    return output


def read_results(source):
    if isinstance(source,dict):return source
    source=Path(source)
    if source.is_dir():
        p=read_json(source/'package.json')
        return {'schema_version':'1','package_id':p['package_id'],'base_commit':p['base_commit'],'submissions':[read_json(f) for f in sorted((source/'submissions').glob('*.json'))]}
    if source.suffix.lower()!='.zip':return read_json(source)
    try:
        with zipfile.ZipFile(source) as archive:
            members=archive.infolist()
            if len(members)>10000 or sum(m.file_size for m in members)>256*1024*1024:raise ReviewError('审核包过大')
            names=[]
            for member in members:
                safe_path(Path.cwd(),member.filename)
                if stat.S_ISLNK(member.external_attr>>16):raise ReviewError('审核包包含符号链接')
                names.append(member.filename)
            if len(names)!=len(set(names)):raise ReviewError('审核包包含重复路径')
            if 'results.json' in names:return json.loads(archive.read('results.json'))
            if 'package.json' not in names:raise ReviewError('审核包缺少身份信息')
            package=json.loads(archive.read('package.json'))
            return {'schema_version':'1','package_id':package['package_id'],'base_commit':package['base_commit'],
                    'submissions':[json.loads(archive.read(n)) for n in names if n.startswith('submissions/') and n.endswith('.json')]}
    except (zipfile.BadZipFile,ValueError,KeyError) as exc:raise ReviewError('结果包格式不合法') from exc


def history_conflicts(store,submissions=None):
    from .history import active_entries,signature
    by_target={};entries=[];conflicts=[];items={i['id']:i for i in store.package['items']}
    for s,d in active_entries(store.submissions() if submissions is None else submissions):
            e={'item_id':d['item_id'],'target_id':d['target_id'],'submission_id':s['submission_id'],'action':d['action'],
               'status':'needs_agent' if d['action']=='comment' else 'missing_current','baseline':items[d['item_id']]['baseline'],'decision':d}
            entries.append(e)
            by_target.setdefault(d['target_id'],[]).append(e)
    for target,values in by_target.items():
        if len({signature(v['decision']) for v in values})>1:
            for e in values:e['status']='conflict'
            conflicts.append({'target_id':target,'reason':'different_human_decisions','submission_ids':[e['submission_id'] for e in values]})
    return {'package_id':store.package['package_id'],'base_commit':store.package['base_commit'],'items':entries,'conflicts':conflicts}


def import_results(root,source):
    store=Store(root);incoming=read_results(source)
    if not isinstance(incoming,dict) or incoming.get('schema_version')!='1' or incoming.get('package_id')!=store.package['package_id'] or incoming.get('base_commit')!=store.package['base_commit']:
        raise ReviewError('回传结果的审核包或 Git 基准不匹配',409)
    submissions=incoming.get('submissions')
    if not isinstance(submissions,list):raise ReviewError('回传结果缺少 submissions 数组')
    items={i['id']:i for i in store.package['items']}
    staged={}
    for s in submissions:
        validate_schema(s,'submission')
        if s['package_id']!=store.package['package_id'] or s['base_commit']!=store.package['base_commit']:raise ReviewError('提交基准不匹配',409)
        if len({d['item_id'] for d in s['decisions']})!=len(s['decisions']):raise ReviewError('提交包含重复条目')
        for d in s['decisions']:
            if d['item_id'] not in items:raise ReviewError('提交包含未知条目')
            item=items[d['item_id']]
            draft={'mode':d['action'],'comment':d.get('instruction',''),'quotes':d.get('quotes',[]),'touched':True}
            if d['action']=='edit':
                draft['edits']={b['id']:b.get('rows') if b['type']=='table' else b.get('text') for b in d['blocks'] if b['type']!='image'}
            if resolve_decision(item,draft)!=d:raise ReviewError('决定与本轮展示内容不一致',409)
        if s['submission_id'] in staged and staged[s['submission_id']]!=s:raise ReviewError('结果包内提交编号冲突',409)
        staged[s['submission_id']]=s
    imported=0;duplicates=0
    with store.lock():
        draft=store._drafts()
        all_submissions={s['submission_id']:s for s in store.submissions()}
        all_submissions.update(staged)
        edges={key:set() for key in all_submissions}
        for key,s in all_submissions.items():
            for r in s.get('resolves',[]):
                previous=all_submissions.get(r['submission_id'])
                if not previous or r['submission_id']==key or not any(d['target_id']==r['target_id'] for d in previous['decisions']) or not any(d['target_id']==r['target_id'] for d in s['decisions']):
                    raise ReviewError('冲突解决引用无效',409)
                edges[key].add(r['submission_id'])
        visiting=set();visited=set()
        def visit(key):
            if key in visiting:raise ReviewError('冲突解决引用形成循环',409)
            if key in visited:return
            visiting.add(key)
            for previous in edges[key]:visit(previous)
            visiting.remove(key);visited.add(key)
        for key in edges:visit(key)
        for key,s in staged.items():
            target=store.root/'submissions'/f'{key}.json'
            if target.exists() and read_json(target)!=s:raise ReviewError('提交编号相同但内容不同',409)
        new_submissions=[]
        for key,s in staged.items():
            target=store.root/'submissions'/f'{key}.json'
            if target.exists():duplicates+=1
            else:new_submissions.append(s);imported+=1
        summary=history_conflicts(store,list(all_submissions.values()))
        if imported:
            conflicting={c['target_id'] for c in summary['conflicts']}
            for entry in summary['items']:
                d=entry['decision'];key=d['item_id']
                if d['target_id'] not in conflicting and not has_human_draft(draft['items'].get(key,{})):
                    draft['items'][key]={'mode':d['action'],'comment':d.get('instruction',''),'quotes':d.get('quotes',[]),'touched':d['action']=='edit','edits':{b['id']:b.get('rows') if b['type']=='table' else b.get('text') for b in d.get('blocks',[]) if b['type']!='image'}}
            draft['revision']+=1
            store._commit(draft,new_submissions,summary)
        else:atomic_json(store.root/'comparison.json',summary)
    return {'imported':imported,'duplicates':duplicates,'conflicts':summary['conflicts']}
