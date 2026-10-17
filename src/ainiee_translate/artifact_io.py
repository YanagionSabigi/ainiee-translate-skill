"""Shared local artifact IO; contains no PDF extraction logic."""
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile


def sha256(path):
    with Path(path).open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def write_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.' + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.write('\n')
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def safe_relative(name):
    path = PurePosixPath(name)
    if (not name or '\\' in name or ':' in name or name.startswith('/')
            or any(p in ('', '.', '..') for p in name.split('/'))
            or any(p.endswith((' ', '.')) or re.fullmatch(r'(?i)(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\..*)?', p)
                   or any(ord(c) < 32 or c in '<>"|?*' for c in p) for p in path.parts)):
        raise ValueError(f'Unsafe relative member path: {name!r}')
    return path.as_posix()
