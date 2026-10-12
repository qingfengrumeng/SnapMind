import importlib
import sys
import json
import sqlite3
import os
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from fastapi.testclient import TestClient
from backend.app.model_profiles import ActiveSelection,set_active

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    sys.modules.pop('backend.app.main',None)
    mod=importlib.import_module('backend.app.main')
    with TestClient(mod.app) as value:yield value

def config(**changes):
    return {'name':'Local test','vendor':'custom','provider':'openai-compatible','baseUrl':'http://127.0.0.1:8999/v1','model':'test-vision','vision':False,**changes}

def save(client,id='custom',**changes):
    result=client.put('/api/settings/models/'+id,json=config(**changes))
    assert result.status_code==200,result.text
    return result.json()

def test_multiple_profiles_only_one_explicitly_enabled(client):
    original=client.get('/api/settings/models').json()
    assert original['activeId'] is None
    assert {p['id'] for p in original['profiles']}=={'deepseek','kimi','qwen','doubao','glm','custom'}
    assert client.put('/api/settings/models/active',json={'activeId':'deepseek'}).status_code==400
    assert save(client)['activeId'] is None
    assert save(client,'second',name='Second model',model='other-model')['activeId'] is None
    assert client.put('/api/settings/models/active',json={'activeId':'custom'}).json()['activeId']=='custom'
    assert client.put('/api/settings/models/active',json={'activeId':'second'}).json()['activeId']=='second'
    current=client.get('/api/settings/models').json()
    assert current['activeId']=='second' and len([p for p in current['profiles'] if p['saved']])==2
    assert client.put('/api/settings/models/active',json={'activeId':'unknown'}).status_code==400
    assert client.get('/api/settings/models').json()['activeId']=='second'
    assert client.put('/api/settings/models/active',json={'activeId':None}).json()['activeId'] is None

def test_atomic_selection_and_no_profile_loss(client):
    save(client);save(client,'second',model='other-model')
    path=sys.modules['backend.app.main'].DB
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda id:set_active(path,ActiveSelection(activeId=id)),['custom','second']*12))
    current=client.get('/api/settings/models').json()
    assert current['activeId'] in ('custom','second')
    assert len([p for p in current['profiles'] if p['saved']])==2

def test_active_configuration_changes_require_explicit_reenable(client):
    save(client)
    client.put('/api/settings/models/active',json={'activeId':'custom'})
    assert save(client)['activeId']=='custom'
    assert save(client,model='changed-model')['activeId'] is None
    assert client.put('/api/settings/models/active',json={'activeId':'custom'}).json()['activeId']=='custom'
    assert save(client,model='changed-model',vision=True)['activeId'] is None

def test_legacy_migration_never_auto_enables(client):
    assert client.put('/api/settings/model',json={'provider':'ollama','baseUrl':'http://127.0.0.1:11434','model':'old-model'}).status_code==200
    data=client.get('/api/settings/models').json()
    legacy=next(p for p in data['profiles'] if p['id']=='legacy')
    assert legacy['model']=='old-model' and legacy['saved'] and data['activeId'] is None

@pytest.mark.skipif(os.name!='nt',reason='DPAPI storage')
def test_keys_do_not_leak_and_are_per_profile(client):
    save(client,apiKey='test-key-one')
    save(client,'second',apiKey='test-key-two')
    public=client.get('/api/settings/models').text
    assert 'test-key' not in public and 'apiKeyProtected' not in public
    save(client,model='updated')
    path=sys.modules['backend.app.main'].DB
    with sqlite3.connect(path) as db:data=json.loads(db.execute("SELECT body FROM app_settings WHERE name='model_profiles'").fetchone()[0])
    from backend.app.model_profiles import unprotect_key
    first=next(p for p in data['profiles'] if p['id']=='custom')
    second=next(p for p in data['profiles'] if p['id']=='second')
    assert unprotect_key(first['apiKeyProtected'])=='test-key-one'
    assert unprotect_key(second['apiKeyProtected'])=='test-key-two'
    assert 'test-key' not in json.dumps(data)
    client.put('/api/settings/models/active',json={'activeId':'custom'})
    save(client,clearApiKey=True)
    profiles=client.get('/api/settings/models').json()['profiles']
    assert client.get('/api/settings/models').json()['activeId'] is None
    assert not next(p for p in profiles if p['id']=='custom')['hasApiKey']
    assert next(p for p in profiles if p['id']=='second')['hasApiKey']

@pytest.fixture
def fake_service(monkeypatch):
    requests=[]
    class FakeClient:
        def __init__(self,**kwargs):assert kwargs['follow_redirects'] is False
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,**kwargs):
            requests.append(('get',url,kwargs))
            return httpx.Response(200,json={'data':[{'id':'test-vision'}]})
        async def post(self,url,**kwargs):
            requests.append(('post',url,kwargs))
            return httpx.Response(200,json={'choices':[{'message':{'content':'actual test reply'}}],'usage':{'prompt_tokens':80,'completion_tokens':12}})
    monkeypatch.setattr('backend.app.model_profiles.httpx.AsyncClient',FakeClient)
    return requests

def test_connection_does_not_save_or_activate_or_send_images(client,fake_service):
    result=client.post('/api/settings/models/custom/test',json=config(model='test-vision'))
    assert result.status_code==200 and result.json()['modelAvailable'] is True
    assert fake_service[0][0]=='get' and fake_service[0][1].endswith('/v1/models')
    data=client.get('/api/settings/models').json()
    assert data['activeId'] is None and not next(p for p in data['profiles'] if p['id']=='custom')['saved']
    assert client.get('/api/usage').json()['requests']==0

def test_enabled_model_handles_requests_and_tracks_real_usage(client,fake_service):
    from backend.tests.test_api import session
    save(client,vision=True)
    client.put('/api/settings/models/active',json={'activeId':'custom'})
    response=client.post('/api/chat',json={'session':session('custom'),'action':'explain','prompt':'read image'})
    assert response.status_code==200,response.text
    result=json.loads([line[6:] for line in response.text.splitlines() if line.startswith('data: ')][-1])['message']
    assert result['text']=='actual test reply' and result['demo'] is False
    assert fake_service[0][0]=='post'
    assert fake_service[0][2]['json']['messages'][-1]['content'][1]['type']=='image_url'
    usage=client.get('/api/usage').json()
    assert usage['inputTokens']==80 and usage['outputTokens']==12 and usage['requests']==1

def test_vision_permission_blocks_image_processing(client,fake_service):
    from backend.tests.test_api import session
    save(client,vision=False);client.put('/api/settings/models/active',json={'activeId':'custom'})
    response=client.post('/api/chat',json={'session':session('custom'),'action':'ocr','prompt':'read image'})
    assert response.status_code==400 and not fake_service
    client.post('/api/chat',json={'session':session('custom'),'action':'chat','prompt':'hello'})
    content=fake_service[0][2]['json']['messages'][-1]['content']
    assert isinstance(content,str)

def test_connection_errors_do_not_expose_service_body(client,monkeypatch):
    class Unauthorized:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,*args,**kwargs):return httpx.Response(401,text='upstream secret credentials')
    monkeypatch.setattr('backend.app.model_profiles.httpx.AsyncClient',Unauthorized)
    result=client.post('/api/settings/models/custom/test',json=config())
    assert result.status_code==200 and not result.json()['ok'] and '认证失败' in result.json()['error']
    assert result.json()['latencyMs']>=0
    assert 'upstream secret' not in result.text
    assert client.get('/api/settings/models').json()['activeId'] is None

def test_models_fetch_returns_all_pages_without_saving(client,monkeypatch):
    requests=[]
    class Pages:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def get(self,url,**kwargs):
            requests.append(kwargs)
            page=len(requests)
            return httpx.Response(200,json={'data':[{'id':f'model-{i}'} for i in range((page-1)*600,page*600)],'has_more':page==1,'last_id':'model-599'})
    monkeypatch.setattr('backend.app.model_profiles.httpx.AsyncClient',Pages)
    response=client.post('/api/settings/models/custom/models',json=config(model='',apiKey='synthetic-list-key'))
    assert response.status_code==200 and len(response.json()['models'])==1200
    assert requests[1]['params']=={'after':'model-599'}
    assert all(request['headers']['Authorization']=='Bearer synthetic-list-key' for request in requests)
    registry=client.get('/api/settings/models').json()
    assert registry['activeId'] is None
    assert all('models' not in profile for profile in registry['profiles'])

def test_models_fetch_requires_key_before_requesting_provider(client,monkeypatch):
    def unexpected_client(**kwargs):
        raise AssertionError('No provider request is allowed without an API key')
    monkeypatch.setattr('backend.app.model_profiles.httpx.AsyncClient',unexpected_client)
    response=client.post('/api/settings/models/custom/models',json=config(model=''))
    assert response.status_code==400 and 'API Key' in response.json()['detail']

def test_key_portal_uses_only_verified_url(client,monkeypatch):
    from backend.app.model_profiles import KEY_PORTALS
    opened=[]
    monkeypatch.setattr('backend.app.model_profiles.webbrowser.open',lambda url,**kwargs:opened.append(url) or True)
    assert client.post('/api/settings/key-portals/qwen/open').status_code==200
    assert opened==[KEY_PORTALS['qwen']] and 'bailian.console.aliyun.com' in opened[0]
    assert client.post('/api/settings/key-portals/doubao/open').status_code==200
    assert 'console.volcengine.com/ark/' in opened[-1]
    assert client.post('/api/settings/key-portals/unknown/open').status_code==400
    assert len(opened)==2

def test_removing_ollama_preserves_old_configuration_privately(client):
    path=sys.modules['backend.app.main'].DB
    old={'activeId':'ollama','profiles':[{'id':'ollama','name':'Ollama','vendor':'ollama','provider':'ollama','baseUrl':'http://127.0.0.1:11434','model':'local-model','saved':True,'vision':False}]}
    with sqlite3.connect(path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS app_settings (name TEXT PRIMARY KEY,body TEXT NOT NULL)')
        db.execute("INSERT INTO app_settings VALUES('model_profiles',?)",(json.dumps(old),))
    response=client.get('/api/settings/models').json()
    assert response['activeId'] is None and not any(p['vendor']=='ollama' for p in response['profiles'])
    assert {p['id'] for p in response['profiles']}=={'deepseek','kimi','qwen','doubao','glm','custom'}
    save(client)
    with sqlite3.connect(path) as db:data=json.loads(db.execute("SELECT body FROM app_settings WHERE name='model_profiles'").fetchone()[0])
    assert data['retiredProfiles'][0]['model']=='local-model'
