"""Loopback-only HTTP API. No business source-file writes."""
import json
import mimetypes
import secrets
import sys
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from .model import ROOT, ReviewError, safe_path
from .storage import Store, file_lock


class ReviewServer(ThreadingHTTPServer):
    daemon_threads=True
    def server_close(self):
        super().server_close()
        if getattr(self,'lease',None):
            self.lease.__exit__(None,None,None);self.lease=None


def make_server(root,port=0):
    store=Store(root)
    if store.package['base_commit']:
        from .gitops import verify_baseline
        verify_baseline(root,store.package)
    lease=file_lock(store.root/'.server.lock',timeout=0)
    lease.__enter__()
    try:
        server=ReviewServer(('127.0.0.1',port),Handler)
        server.store=store;server.token=secrets.token_urlsafe(32);server.lease=lease
        return server
    except Exception:
        lease.__exit__(None,None,None);raise


class Handler(BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass

    def respond(self,status,body,mime='application/json; charset=utf-8',asset=False):
        if isinstance(body,(dict,list)):body=json.dumps(body,ensure_ascii=False).encode('utf-8')
        elif isinstance(body,str):body=body.encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type',mime);self.send_header('Content-Length',str(len(body)))
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Cache-Control','no-store')
        self.send_header('Content-Security-Policy',"default-src 'none'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; font-src 'self'; script-src "+("'none'" if asset else "'self'")+"; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'")
        self.end_headers();self.wfile.write(body)

    def fail(self,error):self.respond(error.status,{'error':str(error)})

    def checked(self,write=False):
        host=f'127.0.0.1:{self.server.server_port}'
        if self.headers.get('Host')!=host:raise ReviewError('主机地址不匹配',403)
        if not secrets.compare_digest(self.headers.get('X-Review-Token',''),self.server.token):raise ReviewError('审核会话无效，请使用启动时给出的完整链接',403)
        if write and self.headers.get('Origin')!='http://'+host:raise ReviewError('写入来源不匹配',403)

    def body(self):
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16*1024*1024:raise ValueError()
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError()
            return data
        except (ValueError,UnicodeError):raise ReviewError('请求必须是有效的 JSON 对象')

    def do_GET(self):
        try:
            path=unquote(urlsplit(self.path).path)
            if self.headers.get('Host')!=f'127.0.0.1:{self.server.server_port}':raise ReviewError('主机地址不匹配',403)
            if path=='/api/state':
                self.checked();return self.respond(200,self.server.store.state())
            if path=='/api/ping':
                self.checked()
                with self.server.store.lock():revision=self.server.store._drafts()['revision']
                return self.respond(200,{'revision':revision})
            if path=='/':file=ROOT/'web/index.html';asset=False;mime='text/html; charset=utf-8'
            elif path.startswith('/static/'):
                file=safe_path(ROOT/'web',path.removeprefix('/static/'));asset=False
                mime={'js':'text/javascript; charset=utf-8','css':'text/css; charset=utf-8'}.get(file.suffix[1:],mimetypes.guess_type(file.name)[0] or 'application/octet-stream')
            elif path.startswith('/assets/'):
                # Only declared assets are readable, never arbitrary package JSON.
                relative=path.removeprefix('/assets/')
                found=next((a for a in self.server.store.package['assets'] if a['path']==relative),None)
                if not found:raise ReviewError('资源不存在',404)
                file=safe_path(self.server.store.root,relative);asset=True;mime=found['media_type']
            else:raise ReviewError('页面不存在',404)
            if not file.is_file():raise ReviewError('文件不存在',404)
            self.respond(200,file.read_bytes(),mime,asset)
        except ReviewError as exc:self.fail(exc)
        except (OSError,ValueError) as exc:self.fail(ReviewError(str(exc)))

    def do_PUT(self):self.mutate()
    def do_POST(self):self.mutate()
    def mutate(self):
        try:
            self.checked(True);data=self.body();path=urlsplit(self.path).path;store=self.server.store
            if path=='/api/drafts' and self.command=='PUT':result=store.save(data['drafts'],data['expected_revision'])
            elif path=='/api/submit' and self.command=='POST':result=store.submit(data['item_ids'],data['expected_revision'])
            elif path=='/api/bulk-preview' and self.command=='POST':
                with store.lock():result={'eligible':store.bulk_candidates(data['item_ids'])}
            elif path=='/api/bulk' and self.command=='POST':result=store.bulk_accept(data['item_ids'],data['expected_revision'])
            elif path=='/api/compare' and self.command=='POST':
                from .gitops import compare
                result=compare(store.root,data)
            elif path=='/api/import-results' and self.command=='POST':
                from .transfer import import_results
                result=import_results(store.root,data)
            elif path=='/api/resolve' and self.command=='POST':result=store.resolve_conflict(data['target_id'],data['submission_id'],data['item_id'],data['expected_revision'])
            else:raise ReviewError('接口不存在',404)
            self.respond(200,result)
        except ReviewError as exc:self.fail(exc)
        except (KeyError,TypeError,ValueError) as exc:self.fail(ReviewError(f'请求字段不完整或类型错误：{exc}'))
        except OSError as exc:self.fail(ReviewError(f'保存失败：{exc}',500))


def serve(root,port=0,open_browser=True):
    server=make_server(root,port)
    url=f'http://127.0.0.1:{server.server_port}/?key={server.token}'
    print(json.dumps({'url':url,'package':str(server.store.root)},ensure_ascii=False),flush=True)
    if open_browser:webbrowser.open(url)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
