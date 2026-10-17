"""PDF orchestration delegates to the actual pdf-to-epub CLI."""
import sys
from .pdf_bridge import run_cli


def main(argv=None):
    result = run_cli(*(sys.argv[1:] if argv is None else argv))
    print(result.stdout, end='')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
