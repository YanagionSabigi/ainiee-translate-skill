import json
import pytest

def test_gateway_flat_body_and_version():
    from ainiee_translate.weread_client import fetch_snapshot
    calls=[]
    def transport(body, headers):
        calls.append(body)
        assert headers['Authorization']=='Bearer SECRET'
        if body['api_name']=='/book/bookmarklist': return {'updated':[], 'chapters':[]}
        return {'reviews':[], 'hasMore':0, 'synckey':1}
    s=fetch_snapshot(api_key='SECRET', book_id='imported', skill_version='9.8.7', transport=transport)
    assert calls[0]=={'api_name':'/book/bookmarklist','skill_version':'9.8.7','bookId':'imported'}
    assert calls[1]=={'api_name':'/review/list/mine','skill_version':'9.8.7','bookid':'imported','synckey':0,'count':100}
    assert s['completeness']['reviews_complete'] is True
    assert s['completeness']['highlights_complete'] is False

def test_reviews_all_pages_and_cursor_stall():
    from ainiee_translate.weread_client import fetch_snapshot
    def transport(b,h):
        if b['api_name']=='/book/bookmarklist': return {'updated':[]}
        if b['synckey']==0: return {'reviews':[{'review':{'reviewId':'a'}}], 'hasMore':1,'synckey':2}
        return {'reviews':[{'review':{'reviewId':'b'}}], 'hasMore':0,'synckey':3}
    s=fetch_snapshot(api_key='KEY', book_id='b', skill_version='v', transport=transport)
    assert len(s['responses']['reviews'])==2
    def stalled(b,h): return {'updated':[]} if b['api_name']=='/book/bookmarklist' else {'reviews':[],'hasMore':1,'synckey':0}
    with pytest.raises(ValueError, match='cursor'):
        fetch_snapshot(api_key='KEY',book_id='b',skill_version='v',transport=stalled)

def test_key_never_serialized():
    from ainiee_translate.weread_client import fetch_snapshot
    def transport(b,h): return {'updated':[], 'Authorization':'Bearer secret-key', 'debug':'secret-key'} if b['api_name']=='/book/bookmarklist' else {'reviews':[], 'hasMore':0}
    s=fetch_snapshot(api_key='secret-key',book_id='b',skill_version='v',transport=transport)
    assert 'secret-key' not in json.dumps(s)
    assert 'Authorization' not in json.dumps(s)

@pytest.mark.parametrize('reply', [{'errcode':-1,'errmsg':'bad'},{'upgrade_info':{'message':'upgrade'}},{'reviews':[]}])
def test_api_error_or_upgrade_not_complete_snapshot(reply):
    from ainiee_translate.weread_client import fetch_snapshot
    def t(b,h): return reply if b['api_name']=='/review/list/mine' else {'updated':[]}
    with pytest.raises(ValueError): fetch_snapshot(api_key='key',book_id='b',skill_version='v',transport=t)
