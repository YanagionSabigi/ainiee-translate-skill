"""Render the six actual LaTeX examples for the user template guide."""
from pathlib import Path
import shutil
import subprocess

root = Path(__file__).resolve().parents[1] / 'src/ainiee_translate/assets'
target = root / 'docs/images'
target.mkdir(parents=True, exist_ok=True)
renderer = shutil.which('pdftoppm')
if not renderer:
    raise SystemExit('pdftoppm is required to rebuild the template screenshots')

for source, page, name in [
    ('rosepine/book/main.pdf', 5, 'rosepine-book'),
    ('rosepine/article/main.pdf', 3, 'rosepine-article'),
    ('rosepine/book/white.pdf', 5, 'rosepine-white-book'),
    ('rosepine/article/white.pdf', 3, 'rosepine-white-article'),
    ('mathtranslations/book/main.pdf', 5, 'mathtranslations-book'),
    ('mathtranslations/article/main.pdf', 3, 'mathtranslations-article'),
]:
    subprocess.run([renderer, '-f', str(page), '-l', str(page), '-singlefile',
                    '-scale-to', '1200', '-png', str(root / 'template/tex' / source),
                    str(target / name)], check=True)
    print(name, 'page', page)
