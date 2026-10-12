import importlib
import json
import sys
import os
import sqlite3
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    sys.modules.pop('backend.app.main',None)
    mod=importlib.import_module('backend.app.main')
    with TestClient(mod.app) as client:
        yield client

def session(scenario='table'):
    return {'id':str(uuid4()),'title':'测试会话','scenario':scenario,'assets':[{'id':'asset-1','name':'表格.png','data':'data:image/png;base64,aGVsbG8=','width':100,'height':100,'scenario':scenario}],'messages':[],'formula':'x+y','rows':[{'label':'7 月','value':128}],'createdAt':'2026-10-05T00:00:00Z','updatedAt':'2026-10-05T00:00:00Z','pinned':False}

def test_full_session_roundtrip(client):
    s=session();s['messages']=[{'id':'msg-1','role':'user','text':'请校对','sources':['asset-1']}]
    assert client.put('/api/sessions/'+s['id'],json=s).status_code==200
    restored=client.get('/api/sessions').json()[0]
    assert restored==s
    s['rows'][0]['value']=181.5;s['formula']='x^2';s['title']='已校对'
    client.put('/api/sessions/'+s['id'],json=s)
    restored=client.get('/api/sessions').json()[0]
    assert restored['rows'][0]['value']==181.5 and restored['formula']=='x^2'
    assert client.delete('/api/sessions/'+s['id']).status_code==200
    assert client.get('/api/sessions').json()==[]

def test_model_config_validation_and_roundtrip(client):
    assert client.get('/api/settings/model').json()=={'provider':'openai-compatible','baseUrl':'','model':'','hasApiKey':False}
    config={'provider':'ollama','baseUrl':'http://127.0.0.1:11434/','model':'  test-vision  '}
    for url in ('file:///tmp/config','https://user:secret@example.com/v1','https://example.com/v1?api_key=secret','http://[invalid'):
        assert client.put('/api/settings/model',json={**config,'baseUrl':url}).status_code==400
    assert client.get('/api/settings/model').json()['model']==''
    result=client.put('/api/settings/model',json=config)
    assert result.status_code==200
    assert result.json()=={'provider':'ollama','baseUrl':'http://127.0.0.1:11434','model':'test-vision','hasApiKey':False}
    assert client.get('/api/settings/model').json()==result.json()
    assert client.put('/api/settings/model',json={**config,'model':'   '}).status_code==400

def test_usage_counts_actual_records_only(client):
    assert client.get('/api/usage').json()=={'inputTokens':0,'outputTokens':0,'requests':0,'models':[]}
    path=sys.modules['backend.app.main'].DB
    with sqlite3.connect(path) as db:
        db.executemany('INSERT INTO model_usage(id,model,input_tokens,output_tokens,created_at) VALUES(?,?,?,?,?)',[('test-1','vision-a',120,30,'2026-10-05'),('test-2','vision-a',80,20,'2026-10-05'),('test-3','vision-b',10,5,'2026-10-05')])
    data=client.get('/api/usage').json()
    assert data=={'inputTokens':210,'outputTokens':55,'requests':3,'models':[{'model':'vision-a','inputTokens':200,'outputTokens':50,'requests':2},{'model':'vision-b','inputTokens':10,'outputTokens':5,'requests':1}]}

@pytest.mark.skipif(os.name!='nt',reason='Windows DPAPI storage')
def test_model_key_protected_preserved_and_cleared(client):
    config={'provider':'openai-compatible','baseUrl':'https://example.invalid/v1','model':'test-vision','apiKey':'snapmind-test-only-key'}
    response=client.put('/api/settings/model',json=config)
    assert response.status_code==200 and response.json()['hasApiKey']
    assert 'snapmind-test-only-key' not in response.text
    db_path=sys.modules['backend.app.main'].DB
    with sqlite3.connect(db_path) as db:
        body=db.execute("SELECT body FROM app_settings WHERE name='model'").fetchone()[0]
    assert 'snapmind-test-only-key' not in body and json.loads(body)['apiKeyProtected']
    config.pop('apiKey')
    assert client.put('/api/settings/model',json=config).json()['hasApiKey']
    assert client.get('/api/settings/model').json()['hasApiKey']
    assert not client.put('/api/settings/model',json={**config,'clearApiKey':True}).json()['hasApiKey']
    assert not client.get('/api/settings/model').json()['hasApiKey']

def test_unconfigured_model_never_returns_or_persists_demo_responses(client):
    s=session()
    r=client.post('/api/chat',json={'session':s,'action':'table','prompt':'提取数据'})
    assert r.status_code==400 and '启用' in r.json()['detail']
    assert client.get('/api/sessions').json()==[]

def test_custom_image_never_gets_fake_recognition(client):
    s=session('custom')
    r=client.post('/api/chat',json={'session':s,'action':'formula','prompt':'识别图片'})
    assert r.status_code==400 and 'LLM' in r.json()['detail']

def test_validation_and_missing_material(client):
    s=session()
    assert client.put('/api/sessions/different',json=s).status_code==400
    s['assets'][0]['data']='data:image/svg+xml;base64,aaa'
    assert client.put('/api/sessions/'+s['id'],json=s).status_code==422
    s['assets']=[]
    assert client.post('/api/chat',json={'session':s,'action':'chat','prompt':'hi'}).status_code==400
    assert client.post('/api/chat',json={'session':s,'action':'unknown','prompt':'hi'}).status_code==422

def test_example_action_does_not_invent_unrelated_artifact(client):
    r=client.post('/api/chat',json={'session':session('table'),'action':'formula','prompt':'提取公式'})
    assert r.status_code==400 and 'LLM' in r.json()['detail']
