"""Command line entry points for skills and human reviewers."""
import argparse
import json
import sys
from pathlib import Path
from .model import ReviewError, validate_package
from .storage import read_json


def main(argv=None):
    if hasattr(sys.stdout,'reconfigure'):sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr,'reconfigure'):sys.stderr.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(prog='review-workbench',description='本地通用校对工作台')
    sub=parser.add_subparsers(dest='command',required=True)
    p=sub.add_parser('prepare',help='准备冻结审核包与 Git 基准');p.add_argument('--project',required=True);p.add_argument('--input',required=True);p.add_argument('--scope',required=True);p.add_argument('--out',required=True)
    p=sub.add_parser('serve',help='启动本机审核网页');p.add_argument('package');p.add_argument('--port',type=int,default=0);p.add_argument('--no-open',action='store_true')
    p=sub.add_parser('export',help='导出可迁移包或仅结果');p.add_argument('package');p.add_argument('--out',required=True);p.add_argument('--results-only',action='store_true');p.add_argument('--offline-deps',action='store_true')
    p=sub.add_parser('import-results',help='导入回传决定');p.add_argument('package');p.add_argument('--from',dest='source',required=True)
    p=sub.add_parser('compare',help='用 Git 对照当前稿与人工决定');p.add_argument('package');p.add_argument('--current',required=True)
    p=sub.add_parser('validate',help='验证审核输入');p.add_argument('input')
    p=sub.add_parser('demo',help='创建可交互的示例审核项目');p.add_argument('--out',required=True)
    p=sub.add_parser('export-skill',help='生成带运行资源的独立 skill 安装包');p.add_argument('--out',required=True)
    args=parser.parse_args(argv)
    try:
        if args.command=='prepare':
            from .gitops import prepare
            result=prepare(args.project,args.input,args.scope,args.out)
        elif args.command=='serve':
            from .server import serve
            return serve(args.package,args.port,not args.no_open)
        elif args.command=='export':
            from .transfer import export_package
            result={'path':str(export_package(args.package,args.out,args.results_only,args.offline_deps))}
        elif args.command=='import-results':
            from .transfer import import_results
            result=import_results(args.package,args.source)
        elif args.command=='compare':
            from .gitops import compare
            result=compare(args.package,read_json(args.current))
        elif args.command=='demo':
            from .demo import create_demo
            result={'package':str(create_demo(args.out))}
        elif args.command=='export-skill':
            from .transfer import export_skill
            result={'path':str(export_skill(args.out))}
        else:
            path=Path(args.input);validate_package(read_json(path),path.parent);result={'valid':True}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ReviewError,OSError) as exc:
        print(str(exc),file=sys.stderr);raise SystemExit(1)


if __name__=='__main__':main()
