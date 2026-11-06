"""Build an authored compatibility fixture through production build and repair."""
from argparse import Namespace
import json
from pathlib import Path
import sys
import tempfile
import zipfile
import xml.etree.ElementTree as ET

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parents[3] / 'publication_skill' / 'scripts'))
import epub_build as builder
from epub_weread import repair


def main():
    source = HERE/'source.json'
    with tempfile.TemporaryDirectory(prefix='weread-example-', dir=HERE) as tmp:
        work = Path(tmp)
        builder.save(work/'state.json', {'source_path':str(source)})
        builder.save(work/'raw.json', {'schema':'authored-example/1'})
        book = json.loads(source.read_text(encoding='utf8'))
        book.update(source_sha256=builder.sha(source), raw_sha256=builder.sha(work/'raw.json'))
        builder.save(work/'book.json', book)
        original = work/'authored.epub'
        builder.build(Namespace(work=str(work), output=str(original), allow_unreviewed=False, formula_renderer=None))
        with zipfile.ZipFile(original) as z:
            data = {n:z.read(n) for n in z.namelist()}
        # The author deliberately supplies a legacy shaded container for repair.
        root = ET.fromstring(data['EPUB/ch1.xhtml'])
        body = root.find('{'+builder.X+'}body')
        quote = body.find('*[@id="quoted"]')
        credit = body.find('*[@id="credit"]')
        box = ET.Element('{'+builder.X+'}div', {'class':'bgc_cccccc', 'id':'quotation-box'})
        body.insert(list(body).index(quote), box)
        for node in (quote, credit): body.remove(node); box.append(node)
        credit.set('class', 'ta_right')
        data['EPUB/ch1.xhtml'] = builder.xml_bytes(root)
        data['EPUB/book.css'] += b'\n.bgc_cccccc{background-color:#ccc}.ta_right{text-align:right}th{background-color:#eee}\n'
        shaded = work/'shaded.epub'
        with zipfile.ZipFile(shaded,'w',zipfile.ZIP_DEFLATED) as z:
            for n,payload in data.items():
                z.writestr(n,payload,compress_type=zipfile.ZIP_STORED if n=='mimetype' else zipfile.ZIP_DEFLATED)
        output = work/'compatible.epub'
        repair(shaded, output, plain_callouts=True, split_at=['EPUB/ch1.xhtml#section-two'])
        checks = builder.check_epub(output)
        if checks['errors']: raise ValueError(checks['errors'])
        (HERE/'compatible.epub').write_bytes(output.read_bytes())
        builder.save(HERE/'checks.json', checks)
        print('Example:', builder.sha(output))


if __name__ == '__main__': main()
