"""Adapt frozen WeRead reports to human submissions and existing CAS transactions."""
import copy
import json
from pathlib import Path
import uuid

from .artifact_io import digest, text_sha256
from .reading_round import (load_round, load_issues, load_segments, current_items,
                            item_identity, read, child, round_lock)
from .reading_report import render_report, STATES
from .reading_decisions import record_decisions, apply_decisions
from .workbench_bridge import (block, package, prepare_project, load_project, compare_project,
                               instruction_text, application_lock, submitted_comparison)


def _parts(shown, frozen):
    if shown.get('assessment'):
        return shown['assessment']['segments']
    selected = (shown.get('matching') or {}).get('selected') or []
    return [frozen[s['segment_id']] for s in selected]


def prepare_reading(round_dir, cache, output, report_revision=None):
    round_dir = Path(round_dir).resolve()
    r = load_round(round_dir)
    report_revision = report_revision or r.get('latest_report_revision')
    if not report_revision:
        report_revision = render_report(round_dir).stem
    with round_lock(round_dir):
        r = load_round(round_dir)
        report = read(child(round_dir, f'reports/{report_revision}.json'))
        if report['edition_id'] != r['edition_id'] or report['project_id'] != r['project_id']:
            raise ValueError('报告与当前阅读版本不符')
        current_items(round_dir, cache)
        frozen = {s['segment_id']: s for s in load_segments(round_dir)}
        p = package('微信读书校对 · ' + r['storage_path'],
                    [dict(id='notes', title='微信阅读反馈'), dict(id='expanded', title='同类扩展发现')])
        binding = dict(kind='reading', round=str(round_dir), cache=str(Path(cache).resolve()),
                       project_id=r['project_id'], edition_id=r['edition_id'],
                       report_revision=report_revision, report_hash=digest(report), items={})
        for shown in report['issues']:
            iid = shown['issue_id']
            assessment = shown.get('assessment')
            parts = _parts(shown, frozen)
            before = [block(f'segment-{n + 1}', s.get('current_target_text', s.get('target_text', '')))
                      for n, s in enumerate(parts)] or [block('unlocated', shown['note']['excerpt'])]
            recommended = next((c for c in (assessment or {}).get('candidates', [])
                                if c['label'] == assessment['recommended_candidate']), None) if assessment else None
            by_segment = {e['segment_id']: e['replacement_text'] for e in recommended['edits']} if recommended else {}
            proposal = [block(b['id'], by_segment[s['segment_id']]) for b, s in zip(before, parts)] if recommended else None
            evidence = [block('excerpt', '手机阅读选区\n' + shown['note']['excerpt'])]
            for n, thought in enumerate(shown['note'].get('thoughts', [])):
                evidence.append(block(f'thought-{n}', '你的阅读想法\n' + thought['content']))
            for n, thought in enumerate(shown['note'].get('link_candidates', [])):
                evidence.append(block(f'unlinked-{n}', '待关联想法（尚未确认关联）\n' + thought['content']))
            for n, s in enumerate(parts):
                evidence.append(block(f'source-{n}', '原文\n' + s['source_text']))
            for candidate in (assessment or {}).get('candidates', []):
                evidence.append(block('candidate-' + candidate['label'], '候选 ' + candidate['label'] + '\n' + candidate['text']))
            if assessment:
                if assessment.get('uncertainties'):
                    evidence.append(block('uncertainties', '仍需核查\n' + '\n'.join(assessment['uncertainties'])))
                evidence.append(block('provenance', '原文核验记录\n' + json.dumps(assessment.get('evidence', []), ensure_ascii=False, indent=2)))
            target_id = 'segments-' + digest([s['segment_id'] for s in parts])[:24] if parts else iid
            state = STATES.get(shown['status'], shown['status'])
            p['items'].append(dict(id=iid, target_id=target_id,
                group_id='expanded' if shown.get('origin_issue_id') else 'notes', facets={},
                requires_human=True, before=before, baseline=copy.deepcopy(before), proposal=proposal,
                evidence=evidence, rationale=(assessment or {}).get('rationale', '需先完成定位和辨析，再决定译文。'),
                location=f'{iid} · {state} · ' + ', '.join(s.get('href', s['segment_id']) for s in parts)))
            binding['items'][iid] = dict(shown=shown, parts=parts, target_id=target_id,
                                        block_ids=[b['id'] for b in before])
    return prepare_project(output, p, binding)


def reading_targets(binding, cache):
    _, current = current_items(binding['round'], cache)
    targets = {}
    for info in binding['items'].values():
        blocks = []
        for bid, s in zip(info['block_ids'], info['parts']):
            it = current.get(s['text_index'])
            if (it is None or item_identity(it) != s['item_identity']
                    or text_sha256(it.source_text) != s['source_text_sha256']):
                break
            blocks.append(block(bid, it.translated_text))
        else:
            if blocks:
                targets[info['target_id']] = dict(target_id=info['target_id'], blocks=blocks)
    return list(targets.values())


def _stale(binding, info, r, issues):
    shown = info['shown']
    current = issues.get(shown['issue_id'])
    return (r['edition_id'] != binding['edition_id'] or r['project_id'] != binding['project_id']
            or current is None or current['annotation_revision'] != shown['annotation_revision']
            or current.get('current_assessment_revision') != shown.get('assessment_revision')
            or current['status'] in ('remote_deleted', 'out_of_scope', 'missing_unconfirmed', 'stale')
            or not shown.get('assessment'))


def apply_reading(project, cache, instruction):
    instruction_text(instruction)
    with application_lock(project):
        store, binding = load_project(project)
        if binding['kind'] != 'reading' or Path(cache).resolve() != Path(binding['cache']).resolve():
            raise ValueError('阅读校对包与缓存路径不符')
        rd = Path(binding['round'])
        report = read(child(rd, f"reports/{binding['report_revision']}.json"))
        if digest(report) != binding['report_hash']:
            raise ValueError('原报告已改变')
        with submitted_comparison(project, reading_targets(binding, cache)) as comparison:
            return _consume(cache, instruction, store, binding, comparison)


def _consume(cache, instruction, store, binding, comparison):
    rd = Path(binding['round'])
    # Runtime target IDs cover equal segment sets. Also reject conflicting
    # decisions on partially overlapping sets before the first business write.
    desired = {}
    for entry in comparison['items']:
        if entry['action'] == 'comment':
            continue
        info = binding['items'][entry['item_id']]
        for s, b in zip(info['parts'], entry['decision']['blocks']):
            desired.setdefault(s['segment_id'], []).append((entry, b['text']))
    for values in desired.values():
        if len({text for _, text in values}) > 1:
            for entry, _ in values:
                entry['status'] = 'conflict'
    result = dict(applied=0, kept=0, conflicts=0, needs_agent=[], results=[])
    for entry in comparison['items']:
        if entry['status'] == 'needs_agent':
            result['needs_agent'].append(entry)
            continue
        info = binding['items'][entry['item_id']]
        shown = info['shown']
        r = load_round(rd)
        issues = {i['issue_id']: i for i in load_issues(rd)['issues']}
        if entry['status'] in ('conflict', 'missing_current') or _stale(binding, info, r, issues):
            result['conflicts'] += 1
            result['results'].append(dict(item_id=entry['item_id'], result='conflict_or_stale'))
            continue
        did = uuid.uuid5(uuid.NAMESPACE_URL,
                         f"{binding['package_id']}:{entry['submission_id']}:{entry['item_id']}").hex
        action = {'accept': 'accept', 'keep': 'keep', 'edit': 'custom'}[entry['action']]
        decision = dict(issue_id=entry['item_id'], action=action, decision_id=did,
                        report_revision=binding['report_revision'], assessment_revision=shown['assessment_revision'],
                        annotation_revision=shown['annotation_revision'],
                        human_instruction=instruction['human_instruction'] + '\n网页正式提交：' + entry['action'],
                        human_reference=str((store.root / 'submissions' / (entry['submission_id'] + '.json')).resolve())
                                        + '\n' + instruction['human_reference'])
        if action == 'custom':
            values = {b['id']: b['text'] for b in entry['decision']['blocks']}
            decision['edits'] = [dict(segment_id=s['segment_id'], replacement_text=values[bid])
                                 for bid, s in zip(info['block_ids'], info['parts'])]
            decision['selected_text'] = '\n'.join(e['replacement_text'] for e in decision['edits'])
        try:
            existing = child(rd, f'decisions/{did}.json')
            if existing.exists():
                decision = read(existing)['decisions'][0]
            record_decisions(rd, dict(schema='reading-decisions/1', decisions=[decision]), resume=True)
            if action == 'keep':
                result['kept'] += 1
            else:
                applied = apply_decisions(rd, cache, decision_ids=[did])
                result['applied'] += applied['applied']
                result['conflicts'] += applied['conflicts']
            result['results'].append(dict(item_id=entry['item_id'], decision_id=did, result='processed'))
        except ValueError as exc:
            result['conflicts'] += 1
            result['results'].append(dict(item_id=entry['item_id'], result='conflict', reason=str(exc)))
    return result
