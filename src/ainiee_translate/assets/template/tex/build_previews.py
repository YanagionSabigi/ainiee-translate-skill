"""Rebuild the six previews with local XeLaTeX (no shell escape)."""
from pathlib import Path
import subprocess
import shutil
import tempfile
from concurrent.futures import ThreadPoolExecutor

root = Path(__file__).resolve().parent
sources = sorted(root.glob('*/*/main.tex'))
sources += list(root.glob('rosepine/*/white.tex'))


def build(source):
    with tempfile.TemporaryDirectory(prefix='.preview-', dir=root) as temporary:
        for _ in range(3):
            subprocess.run(
                ['xelatex', '-no-shell-escape', '-interaction=batchmode',
                 '-halt-on-error', '-output-directory=' + temporary, source.name],
                cwd=source.parent, check=True,
            )
        shutil.copy2(Path(temporary) / source.with_suffix('.pdf').name,
                     source.with_suffix('.pdf'))
    print(source.relative_to(root), 'OK')


with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(build, sources))
