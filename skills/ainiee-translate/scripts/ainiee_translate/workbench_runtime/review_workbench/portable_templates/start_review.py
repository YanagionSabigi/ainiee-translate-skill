"""Small recipient entry point; never installs or downloads at startup."""
from pathlib import Path
import argparse
import sys


def main():
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if sys.version_info < (3, 11):
        print('需要 Python 3.11 或更新版本。安装方法见 OPEN-ME.txt。')
        return 1
    parser = argparse.ArgumentParser(description='启动本机校对网页')
    parser.add_argument('--port', type=int, default=0)
    parser.add_argument('--no-open', action='store_true')
    parser.add_argument('--check', action='store_true', help='仅检查 Python 与依赖，不启动网页')
    args = parser.parse_args()
    try:
        import jsonschema
        from importlib.metadata import version
        parts = tuple(int(p) for p in version('jsonschema').split('.')[:2])
        if not (4, 23) <= parts < (5, 0):
            raise ImportError('jsonschema 版本不符合要求')
    except (ImportError, ValueError):
        print('Python 已找到，但校对依赖缺失或版本不符合要求。')
        print('请先完整解压审核包，在解压目录运行：')
        print('  python -m pip install -r requirements.txt')
        print('详细步骤和离线安装方法见 OPEN-ME.txt。安装后再双击启动入口。')
        return 1
    if args.check:
        print('环境检查通过。Python 与校对依赖可用。')
        return 0
    print('正在启动本机校对服务（不会安装依赖或联网下载）…', flush=True)
    try:
        from review_workbench.server import serve
        serve(Path(__file__).resolve().parent, args.port, not args.no_open)
    except Exception as error:
        print('启动未完成：' + str(error))
        print('请保留此提示，并查看 OPEN-ME.txt 或联系材料提供者。')
        return 1
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
