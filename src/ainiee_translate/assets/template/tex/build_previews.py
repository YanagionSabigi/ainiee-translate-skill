"""Rebuild the four previews with local XeLaTeX (no shell escape)."""
from pathlib import Path
import subprocess
from concurrent.futures import ThreadPoolExecutor

root = Path(__file__).resolve().parent
sources = sorted(root.glob('*/*/main.tex'))
sources += list(root.glob('rosepine/book/white.tex'))


def build(source):
    for _ in range(3):
        subprocess.run(
            ['xelatex', '-no-shell-escape', '-interaction=batchmode',
             '-halt-on-error', source.name],
            cwd=source.parent, check=True,
        )
    print(source.relative_to(root), 'OK')


with ThreadPoolExecutor(max_workers=4) as pool:
    list(pool.map(build, sources))
