#!/usr/bin/env python3
"""Portable equivalent of build.sh's rsync --delete and byte-for-byte drift guard."""
import argparse
from pathlib import Path
import shutil
import sys


def files(root):
    return {p.relative_to(root): p for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.relative_to(root).parts}


def build(repo: Path, *, check=False):
    repo = Path(repo).resolve()
    source = repo / 'src/ainiee_translate'
    target = repo / 'skills/ainiee-translate/scripts/ainiee_translate'
    if not source.is_dir() or not target.resolve().is_relative_to(repo) or target.is_symlink():
        raise ValueError('Invalid canonical source/bundle directories')
    src, dst = files(source), files(target)
    if any(p.is_symlink() for p in list(source.rglob('*')) + list(target.rglob('*'))):
        raise ValueError('Source and bundle must not contain symlinks')
    differences = sorted(str(k) for k in set(src) | set(dst)
                         if k not in src or k not in dst or src[k].read_bytes() != dst[k].read_bytes())
    if check:
        if differences:
            raise ValueError('Bundle differs from src: ' + ', '.join(differences))
        return
    # Mutations are confined to this verified absolute bundle directory.
    target.mkdir(parents=True, exist_ok=True)
    for relative in dst.keys() - src.keys():
        path = target / relative
        if not path.resolve().is_relative_to(target.resolve()):
            raise ValueError('Bundle deletion escapes intended directory')
        path.unlink()
    for relative, path in src.items():
        destination = target / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    build(repo, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true')
    args = parser.parse_args()
    try:
        build(Path(__file__).parent, check=args.check)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print('src and bundled scripts are in sync')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
