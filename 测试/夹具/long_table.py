"""Synthetic long-table stress case; never real source-comparison evidence."""


def add_long_table(book, header_kind='plain', row_count=120):
    header = [{'text': 'Part'}]
    if header_kind == 'note':
        header.append({'note': 'n1', 'id': 'table-header-note', 'evidence': 'Synthetic header note'})
    elif header_kind == 'reference':
        header.append({'link': 'p1', 'text': 'See first', 'id': 'table-header-ref', 'evidence': 'Synthetic header reference'})
    book['chapters'][1]['blocks'].append({
        'id': 'long-table', 'kind': 'table', 'header_rows': 1,
        'inline': [{'text': 'Synthetic long table'}],
        'rows': [[{'inline': header}, 'Count']] + [[f'Part {i:03d}', str(i)] for i in range(1, row_count + 1)],
        'table_evidence': 'Synthetic rectangular table for page-break and anchor regression',
        'provenance': [{'page': 3, 'bbox': [20, 20, 400, 60]}],
    })
