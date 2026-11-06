"""Rebuild the authored layout reference with the skill's production builder.

This deliberately starts from authored normalized content, not PDF extraction.
The temporary state contains local paths and is never shipped in the example.
"""
from argparse import Namespace
import json
from pathlib import Path
import shutil
import sys
import tempfile

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / 'publication_skill' / 'scripts'))
import epub_build as builder


def main():
    source = HERE / 'source.json'
    with tempfile.TemporaryDirectory(prefix='example-') as tmp:
        work = Path(tmp)
        shutil.copytree(HERE / 'assets', work / 'assets')
        builder.save(work / 'state.json', {'source_path': str(source)})
        builder.save(work / 'raw.json', {'schema': 'authored-example/1',
                                        'source_sha256': builder.sha(source)})
        book = json.loads(source.read_text(encoding='utf-8'))
        book.update(source_sha256=builder.sha(source),
                    raw_sha256=builder.sha(work / 'raw.json'))
        builder.save(work / 'book.json', book)
        builder.build(Namespace(work=str(work), output=str(HERE / 'reference.epub'),
                                allow_unreviewed=False, formula_renderer=None))
        shutil.copyfile(work / 'conversion-report.json', HERE / 'conversion-report.json')


if __name__ == '__main__':
    main()
