"""Atomic JSON storage, revision checks, and immutable human submissions."""
import contextlib
import copy
import hashlib
import json
import os
import tempfile
import threading
import time
import uuid
from pathlib import Path

from .model import ReviewError, validate_schema, validate_package, resolve_decision, has_human_draft


def read_json(path):
    try: return json.loads(Path(path).read_text(encoding='utf-8'))
    except (ValueError, OSError) as exc: raise ReviewError(f'无法读取 JSON：{Path(path).name} ({exc})') from exc


def atomic_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True,exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix='.'+path.name, suffix='.tmp')
    try:
        with os.fdopen(fd,'w',encoding='utf-8',newline='\n') as f:
            json.dump(data,f,ensure_ascii=False,indent=2); f.write('\n'); f.flush(); os.fsync(f.fileno())
        os.replace(tmp,path)
    finally:
        if os.path.exists(tmp): os.unlink(tmp)


def fingerprint(data):
    return hashlib.sha256(json.dumps(data,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()


@contextlib.contextmanager
def file_lock(path, timeout=5):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    with open(path,'a+b') as f:
        f.seek(0,os.SEEK_END)
        if f.tell()==0: f.write(b' '); f.flush()
        deadline=time.monotonic()+timeout
        while True:
            try:
                f.seek(0)
                if os.name=='nt':
                    import msvcrt
                    msvcrt.locking(f.fileno(),msvcrt.LK_NBLCK,1)
                else:
                    import fcntl
                    fcntl.flock(f,fcntl.LOCK_EX|fcntl.LOCK_NB)
                break
            except OSError:
                if time.monotonic()>=deadline: raise ReviewError('审核包正被其他操作占用',409)
                time.sleep(.05)
        try: yield
        finally:
            f.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(f.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(f,fcntl.LOCK_UN)


class Store:
    def __init__(self,root):
        self.root=Path(root).resolve()
        self.package=validate_package(read_json(self.root/'package.json'),self.root)
        self.material_hash=fingerprint(self.package)
        self.asset_stats={}
        self.mutex=threading.RLock()
        with self.lock():
            if not (self.root/'drafts.json').exists():
                atomic_json(self.root/'drafts.json',{'schema_version':'1','package_id':self.package['package_id'],
                    'base_commit':self.package['base_commit'],'material_hash':self.material_hash,'revision':0,'items':{}})
            self._drafts()

    @contextlib.contextmanager
    def lock(self):
        with self.mutex, file_lock(self.root/'.review.lock'):
            self._recover()
            yield

    def _recover(self):
        """Roll forward a durable intent before exposing any package state.

        Called only with the package lock held. Replaying the same intent is
        safe even when the previous process died after its last data write.
        """
        pending=self.root/'.pending-operation.json'
        if not pending.exists():return
        intent=read_json(pending)
        self._assert_frozen()
        if intent.get('material_hash')!=self.material_hash:
            raise ReviewError('未完成操作与审核材料不匹配',409)
        draft=intent['drafts'];submissions=intent['submissions']
        validate_schema(draft,'drafts')
        if (draft['package_id'],draft['base_commit'],draft['material_hash'])!=(self.package['package_id'],self.package['base_commit'],self.material_hash):
            raise ReviewError('未完成操作的草稿基准不匹配',409)
        # Check every immutable record before changing any file.
        for submission in submissions:
            validate_schema(submission,'submission')
            if (submission['package_id'],submission['base_commit'])!=(self.package['package_id'],self.package['base_commit']):
                raise ReviewError('未完成操作的提交基准不匹配',409)
            target=self.root/'submissions'/f"{submission['submission_id']}.json"
            if target.exists() and read_json(target)!=submission:
                raise ReviewError('未完成操作与已有提交冲突',409)
        for submission in submissions:
            target=self.root/'submissions'/f"{submission['submission_id']}.json"
            if not target.exists():atomic_json(target,submission)
        atomic_json(self.root/'drafts.json',draft)
        atomic_json(self.root/'comparison.json',intent['comparison'])
        pending.unlink()

    def _commit(self,draft,submissions,comparison):
        """Record a complete operation, then apply it under the caller's lock.

        Once the intent is durable, subsequent access completes the operation
        even if the original request never received its success response.
        """
        atomic_json(self.root/'.pending-operation.json',{
            'material_hash':self.material_hash,'drafts':draft,
            'submissions':submissions,'comparison':comparison})
        self._recover()

    def _assert_frozen(self):
        if fingerprint(read_json(self.root/'package.json'))!=self.material_hash:
            raise ReviewError('审核材料已改变，请建立新一轮审核',409)
        from .model import safe_path
        for asset in self.package['assets']:
            if not asset.get('sha256'):continue
            path=safe_path(self.root,asset['path'])
            try:stat=path.stat()
            except OSError:raise ReviewError('审核资源缺失',409)
            key=(stat.st_size,stat.st_mtime_ns)
            if self.asset_stats.get(asset['id'])!=key:
                if hashlib.sha256(path.read_bytes()).hexdigest()!=asset['sha256']:raise ReviewError('审核资源已改变，请建立新一轮审核',409)
                self.asset_stats[asset['id']]=key

    def _drafts(self):
        self._assert_frozen()
        data=read_json(self.root/'drafts.json')
        validate_schema(data,'drafts')
        if data['material_hash']!=self.material_hash or data['package_id']!=self.package['package_id'] or data['base_commit']!=self.package['base_commit']:
            raise ReviewError('草稿与审核材料不匹配',409)
        return data

    def submissions(self):
        return [read_json(p) for p in sorted((self.root/'submissions').glob('*.json'))]

    def state(self):
        with self.lock():
            return {'package':copy.deepcopy(self.package),'drafts':self._drafts(),'submissions':self.submissions(),
                    'comparison':read_json(self.root/'comparison.json') if (self.root/'comparison.json').exists() else None}

    def save(self,draft,expected_revision):
        with self.lock():
            current=self._drafts()
            if type(expected_revision)!=int or expected_revision!=current['revision']:
                raise ReviewError('另一个页面已修改草稿，请先比较或重新加载',409)
            validate_schema(draft,'drafts')
            if (draft['package_id'],draft['base_commit'],draft['material_hash'])!=(current['package_id'],current['base_commit'],current['material_hash']):
                raise ReviewError('草稿基准不匹配',409)
            items={i['id']:i for i in self.package['items']}
            if not set(draft['items'])<=set(items): raise ReviewError('未知审核条目')
            for key,value in draft['items'].items():
                from .model import validate_quotes
                validate_quotes(items[key],value.get('quotes',[]))
            result=copy.deepcopy(draft); result['revision']=current['revision']+1
            atomic_json(self.root/'drafts.json',result)
            return result

    def bulk_candidates(self,ids):
        drafts=self._drafts()['items']
        submitted={d['item_id'] for s in self.submissions() for d in s['decisions']}
        return [i['id'] for i in self.package['items'] if i['id'] in ids and not i['requires_human']
                and i['id'] not in submitted and not has_human_draft(drafts.get(i['id'],{}))]

    def bulk_accept(self,ids,expected_revision):
        with self.lock():
            draft=self._drafts()
            if draft['revision']!=expected_revision: raise ReviewError('草稿已更新',409)
            eligible=self.bulk_candidates(ids)
            items={i['id']:i for i in self.package['items']}
            for key in eligible:
                draft['items'][key]={'mode':'accept' if items[key].get('proposal') is not None else 'keep'}
            draft['revision']+=1
            atomic_json(self.root/'drafts.json',draft)
            return {'drafts':draft,'accepted':eligible}

    def submit(self,ids,expected_revision):
        with self.lock():
            current=self._drafts()
            if current['revision']!=expected_revision: raise ReviewError('草稿已更新',409)
            if not ids or len(set(ids))!=len(ids): raise ReviewError('提交范围为空或重复')
            items={i['id']:i for i in self.package['items']}
            if not set(ids)<=set(items): raise ReviewError('未知审核条目')
            decisions=[resolve_decision(items[key],current['items'].get(key,{})) for key in ids]
            result={'schema_version':'1','package_id':self.package['package_id'],'base_commit':self.package['base_commit'],
                    'submission_id':uuid.uuid4().hex,'decisions':decisions}
            validate_schema(result,'submission')
            current['revision']+=1
            from .transfer import history_conflicts
            summary=history_conflicts(self,self.submissions()+[result])
            self._commit(current,[result],summary)
            return result

    def resolve_conflict(self,target_id,submission_id,item_id,expected_revision):
        from .history import active_entries
        with self.lock():
            draft=self._drafts()
            if draft['revision']!=expected_revision:raise ReviewError('草稿已更新',409)
            entries=active_entries(self.submissions())
            chosen=next((d for s,d in entries if s['submission_id']==submission_id and d['item_id']==item_id and d['target_id']==target_id),None)
            if chosen is None:raise ReviewError('待选择的决定不存在或已被解决',409)
            result={'schema_version':'1','package_id':self.package['package_id'],'base_commit':self.package['base_commit'],
                    'submission_id':uuid.uuid4().hex,'decisions':[copy.deepcopy(chosen)],
                    'resolves':[{'submission_id':s['submission_id'],'target_id':target_id} for s,d in entries if d['target_id']==target_id]}
            # Multiple items in the same submission may concern one target.
            result['resolves']=list({(r['submission_id'],r['target_id']):r for r in result['resolves']}.values())
            validate_schema(result,'submission')
            for item in self.package['items']:
                if item['target_id']==target_id and item['id']!=item_id and item['id'] in draft['items']:
                    draft['items'][item['id']]['mode']=None
            draft['items'][item_id]={'mode':chosen['action'],'comment':chosen.get('instruction',''),'quotes':chosen.get('quotes',[]),'touched':chosen['action']=='edit','edits':{b['id']:b.get('rows') if b['type']=='table' else b.get('text') for b in chosen.get('blocks',[]) if b['type']!='image'}}
            draft['revision']+=1
            from .transfer import history_conflicts
            summary=history_conflicts(self,self.submissions()+[result])
            self._commit(draft,[result],summary)
            return result
