"""Explicit boundary to the developer-selected pdf-to-epub implementation."""
from __future__ import annotations
import importlib
import os
from pathlib import Path
import subprocess
import sys


def skill_root() -> Path:
    explicit = os.environ.get('AINIEE_PDF_TO_EPUB')
    if explicit:
        candidates = [Path(explicit)]
    else:
        module = Path(__file__).resolve()
        candidates = [module.parent / 'publication_skill']
        candidates += [parent / 'pdf-to-epub-skill' for parent in module.parents]
    for root in candidates:
        if (root / 'scripts/pdf_to_epub.py').is_file():
            return root.resolve()
    raise FileNotFoundError('Set AINIEE_PDF_TO_EPUB to the pdf-to-epub development copy')


def publisher_module(name: str):
    scripts = skill_root() / 'scripts'
    existing = sys.modules.get(name)
    if existing is not None and Path(existing.__file__).resolve().parent != scripts:
        raise ValueError('Another pdf-to-epub implementation is already loaded; use a fresh process')
    if str(scripts) not in sys.path:
        sys.path.insert(0, str(scripts))
    return importlib.import_module(name)


def contract():
    return publisher_module('translation_contract')


def run_cli(*args, timeout=None):
    env = {**os.environ, 'PYTHONUTF8': '1', 'PYTHONDONTWRITEBYTECODE': '1'}
    proc = subprocess.run([sys.executable, '-B', str(skill_root() / 'scripts/pdf_to_epub.py'),
                           *(str(arg) for arg in args)], env=env, shell=False,
                          capture_output=True, text=True, encoding='utf8', errors='replace', timeout=timeout)
    if proc.returncode:
        raise ValueError(f'pdf-to-epub failed ({proc.returncode}): {proc.stderr.strip() or proc.stdout.strip()}')
    return proc
