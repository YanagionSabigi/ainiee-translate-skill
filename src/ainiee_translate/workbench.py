"""AiNiee glossary and WeRead review packages, served by the offline workbench."""
import argparse
import json
from pathlib import Path
import sys

from .workbench_bridge import runtime, load_project, compare_project


def main(argv=None):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    g = commands.add_parser('glossary', help='准备术语表校对')
    g.add_argument('--locked', required=True)
    g.add_argument('--proposals')
    g.add_argument('--out', required=True)
    r = commands.add_parser('reading', help='准备微信读书反馈校对')
    for name in ('round', 'cache', 'out'):
        r.add_argument('--' + name, required=True)
    r.add_argument('--report-revision')
    s = commands.add_parser('serve', help='启动本机工作台')
    s.add_argument('project')
    s.add_argument('--port', type=int, default=0)
    s.add_argument('--no-open', action='store_true')
    for name in ('compare', 'apply'):
        p = commands.add_parser(name, help='比较当前稿' if name == 'compare' else '核验并消费正式提交')
        p.add_argument('project')
        p.add_argument('--cache')
        p.add_argument('--locked')
        if name == 'apply':
            p.add_argument('--instruction-file', required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == 'glossary':
            from .workbench_glossary import prepare_glossary
            result = prepare_glossary(args.locked, args.out, args.proposals)
        elif args.command == 'reading':
            from .workbench_reading import prepare_reading
            result = prepare_reading(args.round, args.cache, args.out, args.report_revision)
        else:
            store, binding = load_project(args.project)
            if args.command == 'serve':
                return runtime().server.serve(store.root, args.port, not args.no_open) or 0
            from .workbench_glossary import glossary_targets, apply_glossary
            from .workbench_reading import reading_targets, apply_reading
            kind = binding['kind']
            if kind not in ('glossary', 'reading'):
                raise ValueError('未知业务校对包')
            path = (args.locked or binding['locked']) if kind == 'glossary' else (args.cache or binding['cache'])
            if args.command == 'compare':
                targets = (glossary_targets if kind == 'glossary' else reading_targets)(binding, path)
                result = compare_project(args.project, targets)
            else:
                instruction = json.loads(Path(args.instruction_file).read_text(encoding='utf-8'))
                result = (apply_glossary if kind == 'glossary' else apply_reading)(args.project, path, instruction)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result.get('conflicts') else 0
    except (ValueError, OSError, KeyError, TypeError) as exc:
        print('校对工作台：' + str(exc), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
