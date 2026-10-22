"""Optional, read-only WeRead gateway. No authentication in saved snapshots."""
import json
from pathlib import Path
import re
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from .reading_round import now, revision

GATEWAY = 'https://i.weread.qq.com/api/agent/gateway'


def skill_version(skill_dir):
    text = (Path(skill_dir) / 'SKILL.md').read_text(encoding='utf8')
    match = re.search(r'^version:\s*[\"\']?([\w.\-]+)', text, re.M)
    if not match:
        raise ValueError('Official skill document has no version; verify official source')
    return match.group(1)


def _http(body, headers):
    request = Request(GATEWAY, json.dumps(body).encode(), headers, method='POST')
    # At most three transport attempts; application errors never silently retry.
    for attempt in range(3):
        try:
            with urlopen(request, timeout=30) as response:
                return json.load(response)
        except HTTPError as exc:
            if exc.code < 500 or attempt==2:
                raise ValueError(f'WeRead HTTP {exc.code}; no snapshot saved') from None
        except (URLError, TimeoutError):
            if attempt==2:
                raise ValueError('WeRead transport unavailable; no snapshot saved') from None
        time.sleep(.25 * (attempt+1))


def _redact(value, secret):
    if isinstance(value, dict):
        return {k:_redact(v,secret) for k,v in value.items()
                if k.lower().replace('_','') not in ('authorization','apikey','accesskey','token','headers')}
    if isinstance(value,list): return [_redact(v,secret) for v in value]
    if isinstance(value,str): return value.replace(secret,'[REDACTED]') if secret else value
    return value


def gateway_request(api_name, *, api_key, skill_version, transport=None, **params):
    if api_name not in ('/book/bookmarklist','/review/list/mine','/shelf/sync'):
        raise ValueError('Only read-only proofreading endpoints are allowed')
    if not api_key or not skill_version:
        raise ValueError('Configure WEREAD_API_KEY locally and provide official skill version')
    body = dict(api_name=api_name, skill_version=skill_version, **params)
    reply = (transport or _http)(body, {'Authorization':'Bearer '+api_key,'Content-Type':'application/json'})
    if not isinstance(reply,dict): raise ValueError('Malformed WeRead response')
    if 'upgrade_info' in reply:
        raise ValueError('WeRead upgrade required; verify the official skill source before retrying')
    if reply.get('errcode',0) != 0:
        raise ValueError('WeRead API rejected request; verify local account authorization')
    return body, _redact(reply,api_key)


def fetch_snapshot(*, api_key, book_id, skill_version, transport=None):
    requests=[]
    def call(name, **params):
        body, reply = gateway_request(name,api_key=api_key,skill_version=skill_version,transport=transport,**params)
        requests.append(body); return reply
    highlights=call('/book/bookmarklist',bookId=book_id)
    if not isinstance(highlights.get('updated'), list):
        raise ValueError('Incomplete highlight response')
    pages=[]; cursor=0; seen={0}
    for _ in range(10000):
        page=call('/review/list/mine',bookid=book_id,synckey=cursor,count=100)
        if not isinstance(page.get('reviews'),list) or page.get('hasMore') not in (0,1,False,True):
            raise ValueError('Incomplete personal reviews response')
        pages.append(page)
        if not page['hasMore']: break
        cursor=page.get('synckey')
        if not isinstance(cursor,(str,int)) or cursor in seen:
            raise ValueError('Personal review cursor did not advance')
        seen.add(cursor)
    else: raise ValueError('Review pagination limit exceeded')
    return dict(schema='weread-snapshot/1',created_at=now(),snapshot_id=revision(),book_id=str(book_id),
                skill_version=skill_version,requests=requests,responses=dict(highlights=highlights,reviews=pages),
                completeness=dict(reviews_complete=True,highlights_complete=False,deletion_semantics_verified=False))
