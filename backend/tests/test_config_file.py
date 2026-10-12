import importlib
import json
import sys
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def environment(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    path=tmp_path/'.snapmind'
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(path))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    with TestClient(module.app) as client:yield client,path

def payload(**values):
    return {'name':'Test model','vendor':'custom','provider':'openai-compatible','baseUrl':'https://example.invalid/v1','model':'test-model','vision':False,**values}

def test_configuration_file_contains_individual_enabled_flags(environment):
    client,path=environment
    assert client.get('/api/settings/models').status_code==200
    document=json.loads(path.read_text(encoding='utf-8'))
    assert document['schemaVersion']==1 and document['activeModelId'] is None
    assert all(m['enabled'] is False for m in document['models'])
    assert client.put('/api/settings/models/custom',json=payload()).status_code==200
    assert client.put('/api/settings/models/second',json=payload(name='Second')).status_code==200
    for model in ('custom','second'):
        assert client.put('/api/settings/models/active',json={'activeId':model}).status_code==200
        document=json.loads(path.read_text(encoding='utf-8'))
        assert document['activeModelId']==model
        assert [m['id'] for m in document['models'] if m['enabled']]==[model]
    client.put('/api/settings/models/active',json={'activeId':None})
    assert not any(m['enabled'] for m in json.loads(path.read_text(encoding='utf-8'))['models'])

@pytest.mark.skipif(os.name!='nt',reason='Windows key cache')
def test_partial_draft_writes_real_key_but_preview_hides_it(environment):
    client,path=environment
    key='test-only-config-file-key'
    result=client.put('/api/settings/models/deepseek/draft',json=payload(name='DeepSeek',vendor='deepseek',model='',apiKey=key))
    assert result.status_code==200
    public=next(m for m in result.json()['profiles'] if m['id']=='deepseek')
    assert public['hasApiKey'] and not public['saved'] and not public['enabled']
    document=json.loads(path.read_text(encoding='utf-8'))
    assert next(m for m in document['models'] if m['id']=='deepseek')['apiKey']==key
    assert key not in client.get('/api/settings/config').text
    assert key in client.get('/api/settings/config?reveal_keys=true').text
    assert client.put('/api/settings/models/active',json={'activeId':'deepseek'}).status_code==400
    client.put('/api/settings/models/deepseek/draft',json=payload(name='DeepSeek',vendor='deepseek',model='test-model'))
    assert client.put('/api/settings/models/active',json={'activeId':'deepseek'}).status_code==200
    client.put('/api/settings/models/deepseek/draft',json=payload(name='DeepSeek',vendor='deepseek',model='test-model',apiKey=key))
    assert client.get('/api/settings/models').json()['activeId']=='deepseek'
    client.put('/api/settings/models/deepseek/draft',json=payload(name='DeepSeek',vendor='deepseek',model='changed'))
    assert client.get('/api/settings/models').json()['activeId'] is None

def test_file_edits_are_read_and_multiple_enabled_are_rejected(environment):
    client,path=environment
    client.put('/api/settings/models/custom',json=payload())
    data=json.loads(path.read_text(encoding='utf-8'))
    model=next(m for m in data['models'] if m['id']=='custom')
    model['model']='from-file';model['enabled']=True
    path.write_text(json.dumps(data),encoding='utf-8')
    result=client.get('/api/settings/models').json()
    assert result['activeId']=='custom'
    assert next(m for m in result['profiles'] if m['id']=='custom')['model']=='from-file'
    data['models'].append({**model,'id':'second','enabled':True})
    path.write_text(json.dumps(data),encoding='utf-8')
    assert client.get('/api/settings/models').status_code==400

def test_failed_write_preserves_previous_configuration(environment,monkeypatch):
    client,path=environment
    client.put('/api/settings/models/custom',json=payload())
    before=path.read_bytes()
    monkeypatch.setattr('backend.app.config_file.os.replace',lambda *args:(_ for _ in ()).throw(OSError('test-only-write-failure')))
    result=client.put('/api/settings/models/custom',json=payload(model='changed'))
    assert result.status_code==500
    assert path.read_bytes()==before
    assert not list(path.parent.glob('.snapmind.*.tmp'))
