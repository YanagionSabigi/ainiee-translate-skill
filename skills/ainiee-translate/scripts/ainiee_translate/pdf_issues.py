"""Version-bound human decisions, separate from detailed diagnostics."""
import copy
from collections import defaultdict


def issue_ledger(book, issues):
    ids = [i.get('id') for i in issues]
    if not all(ids) or len(ids) != len(set(ids)):
        raise ValueError('Missing/duplicate issue ID')
    return {'schema': 'pdf-issues/1', 'document_id': book['document_id'], 'revision': book['revision'],
            'issues': copy.deepcopy(issues), 'decisions': []}


def decide_issue(ledger, issue_id, *, action, reason, actor, book):
    if ledger.get('document_id') != book['document_id'] or ledger.get('revision') != book['revision']:
        raise ValueError('Issue decision revision does not match current book')
    issue = next((i for i in ledger['issues'] if i['id'] == issue_id), None)
    if not issue:
        raise ValueError('Unknown issue ID')
    if (issue.get('kind') != 'semantic_reference' or action != 'plain_text' or not issue.get('ref_id')
            or issue.get('status', 'unresolved') != 'unresolved'):
        raise ValueError('Only unresolved semantic references permit a plain-text waiver')
    if not reason.strip() or not actor.strip():
        raise ValueError('Decision requires actor and reason')
    binding = {}
    if 'references' in book:
        ref = next((r for r in book['references'] if r['ref_id'] == issue['ref_id']), None)
        if ref is None or ref.get('status') not in ('pending', 'text_only'):
            raise ValueError('Decision requires an existing unresolved semantic reference')
        from .pdf_bridge import contract
        binding = {'reference_sha256': contract().content_digest(ref),
                   'source_units': {u['unit_id']: u['source_sha256'] for u in book['units']
                                    if u.get('block_id') == ref['block_id']}}
    result = copy.deepcopy(ledger)
    result['decisions'] = [d for d in result['decisions'] if d['issue_id'] != issue_id]
    result['decisions'].append({'issue_id': issue_id, 'ref_id': issue['ref_id'], 'action': action,
        'reason': reason, 'actor': actor, 'document_id': book['document_id'], 'revision': book['revision'], **binding})
    return result


def publication_decisions(ledger, book):
    """Only explicit human decisions produce the publisher's semantic waiver."""
    from .pdf_bridge import contract
    if ledger['document_id'] != book['document_id']:
        raise ValueError('Decision document mismatch')
    refs={r['ref_id']:r for r in book.get('references',[])}
    issues={i['id']: i for i in ledger.get('issues', [])}
    decisions=[]
    for record in ledger.get('decisions',[]):
        issue = issues.get(record.get('issue_id'), {})
        if (record.get('action') != 'plain_text' or not record.get('actor') or not record.get('reason')
                or record.get('document_id') != book['document_id']
                or issue.get('kind') != 'semantic_reference' or issue.get('ref_id') != record.get('ref_id')
                or type(record.get('revision')) is not int or record['revision'] > book['revision']):
            continue
        ref=refs.get(record['ref_id'])
        if ref is None or ref['status'] not in ('pending', 'text_only'):
            continue
        related={u['unit_id']:u['source_sha256'] for u in book['units'] if u.get('block_id')==ref['block_id']}
        if (record.get('reference_sha256') != contract().content_digest(ref)
                or record.get('source_units') != related):
            continue
        decisions.append(dict(ref_id=ref['ref_id'],action='text_only',source_revision=record['revision'],
            reference_sha256=record['reference_sha256'],source_units=related,
            approved_by=record['actor'],evidence=record['reason']))
    return {'schema':'pdf-decisions/1','revision':book['revision'],'decisions':decisions}


def main(argv=None):
    import argparse,json
    from pathlib import Path
    from .artifact_io import write_json
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action',choices=['report','decide'])
    for key in ('book','ledger','output'): parser.add_argument('--'+key,required=True)
    for key in ('id','actor','reason','decisions-output'): parser.add_argument('--'+key)
    args=parser.parse_args(argv)
    book=json.loads(Path(args.book).read_text(encoding='utf8'))
    path=Path(args.ledger)
    ledger=json.loads(path.read_text(encoding='utf8')) if path.exists() else issue_ledger(book,[
        dict(id='R-'+r['ref_id'],kind='semantic_reference',cause='Unresolved '+r['kind'],
             location=r['block_id'],ref_id=r['ref_id'],suggestion='确认目标；或明确批准保留文字不建链接')
        for r in book.get('references',[]) if r['status']=='pending'])
    if args.action=='decide':
        ledger=decide_issue(ledger,args.id,action='plain_text',reason=args.reason or '',actor=args.actor or '',book=book)
        if not args.decisions_output: raise ValueError('Decision requires --decisions-output')
        write_json(args.decisions_output,publication_decisions(ledger,book))
    write_json(path,ledger)
    Path(args.output).write_text(render_issue_summary(ledger),encoding='utf8')
    return 0


def render_issue_summary(ledger):
    resolved = {d['issue_id'] for d in ledger.get('decisions', []) if d.get('revision') == ledger['revision']}
    groups = defaultdict(list)
    for issue in ledger['issues']:
        if issue['id'] not in resolved and issue.get('status', 'unresolved') == 'unresolved':
            groups[(issue.get('kind', ''), issue.get('cause', 'Unknown issue'))].append(issue)
    lines = ['| 问题 | 数量 | 定位索引 | 建议/待选处理 |', '| --- | ---: | --- | --- |']
    def esc(s):
        return str(s).replace('|', '\\|').replace('\n', ' ')
    for (_, cause), issues in groups.items():
        locations = '; '.join(f"{i['id']} ({i.get('location', '?')})" for i in issues)
        suggestions = '; '.join(dict.fromkeys(i.get('suggestion', '待决定') for i in issues))
        lines.append(f'| {esc(cause)} | {len(issues)} | {esc(locations)} | {esc(suggestions)} |')
    return '\n'.join(lines) + '\n'


if __name__ == '__main__':
    raise SystemExit(main())
