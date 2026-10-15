"""Immutable inline tokens, enabled only by extra.ainiee_pdf metadata."""
import hashlib
import re

TOKEN = re.compile(r'⟦AT:[^⟧]*⟧')
VALID_TOKEN = re.compile(r'⟦AT:[a-z][a-z0-9_-]*:[A-Za-z0-9_.-]+⟧')


def validate_protected_tokens(source: str, translated: str, *, expected: list[str]) -> list[str]:
    if any(not VALID_TOKEN.fullmatch(t) for t in expected) or len(expected) != len(set(expected)):
        return ['invalid_source_tokens']
    if TOKEN.findall(source) != expected:
        return ['source_token_mismatch']
    if TOKEN.findall(translated) != expected:
        return ['structure_tokens']
    # Malformed token prefixes must not introduce an unrecognized structural claim.
    if translated.count('⟦AT:') != len(expected):
        return ['structure_tokens']
    return []


def escape_collisions(text: str, *, reserved=()):
    mapping = {}
    def replace(match):
        if match[0] in reserved:
            return match[0]
        uid = hashlib.sha256(f'{match.start()}:{match[0]}'.encode()).hexdigest()[:24]
        token = f'⟦AT:literal:L{uid}⟧'
        mapping[token] = {'kind': 'literal', 'text': match[0]}
        return token
    return TOKEN.sub(replace, text), mapping


def check_item(source: str, translated: str, extra: dict | None) -> list[str]:
    meta = (extra or {}).get('ainiee_pdf')
    if meta is None:
        return []
    return validate_protected_tokens(source, translated, expected=meta.get('protected_tokens', []))
