"""Explicit supersession is separate from chronology and preserves all history."""
from .storage import fingerprint


def signature(decision):
    if decision['action']=='comment':return fingerprint({'instruction':decision['instruction'],'quotes':decision['quotes']})
    return fingerprint({'blocks':decision['blocks']})


def active_entries(submissions):
    superseded={(r['submission_id'],r['target_id']) for s in submissions for r in s.get('resolves',[])}
    return [(s,d) for s in submissions for d in s['decisions'] if (s['submission_id'],d['target_id']) not in superseded]
