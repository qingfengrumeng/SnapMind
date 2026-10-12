import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module
from backend.tests.test_speech import config
from backend.app import speech_models as catalog


@pytest.mark.parametrize('kind,expected',[('asr',['fun-asr-realtime','metadata-asr']),('tts',['cosyvoice-v3','metadata-tts'])])
def test_authenticated_pagination_and_kind_filter(module,monkeypatch,kind,expected):
    requests=[];client_class=httpx.AsyncClient
    def handle(request):
        requests.append(request)
        assert request.headers['Authorization']=='Bearer fixture-key'
        assert set(request.url.params.get_list('capabilities'))==set(catalog.CAPABILITIES[kind])
        records=[{'model':'metadata-asr','capabilities':['Realtime-ASR']},{'model':'metadata-tts','capabilities':['TTS']},
                 {'model':'qwen-plus','capabilities':['TG']},{'model':'qwen-omni','capabilities':['TTS','Multimodal-Omni']},
                 {'model':'misleading-asr','capabilities':['TG']}]
        if request.url.params['page_no']=='2':records=[{'id':'fun-asr-realtime'},{'id':'cosyvoice-v3'},{'id':'qwen-plus'},{'id':'qwen-audio-chat'}]
        return httpx.Response(200,json={'output':{'models':records,'total':200,'page_size':100}})
    monkeypatch.setattr(catalog.httpx,'AsyncClient',lambda **kwargs:client_class(**kwargs,transport=httpx.MockTransport(handle)))
    client=TestClient(module.app)
    body=config(kind=kind,sampleRate=16000,model='',baseUrl='wss://ws-fixture.cn-beijing.maas.aliyuncs.com/api-ws/v1/inference')
    result=client.post('/api/settings/speech/draft/models',json=body)
    assert result.status_code==200,result.text
    assert result.json()['models']==expected and result.json()['kind']==kind
    assert len(requests)==2 and str(requests[0].url).startswith('https://ws-fixture.cn-beijing.maas.aliyuncs.com/api/v1/models?')


def test_uses_saved_key_without_saving_draft(module,monkeypatch):
    client=TestClient(module.app);body=config(kind='asr',sampleRate=16000,model='qwen3-asr-flash-realtime')
    assert client.put('/api/settings/speech/kept',json=body).status_code==200
    client_class=httpx.AsyncClient
    def handle(request):
        assert request.headers['Authorization']=='Bearer fixture-key'
        return httpx.Response(200,json={'data':[{'id':'qwen3-asr-flash-realtime'},{'id':'qwen-tts'},{'id':'qwen-max'}]})
    monkeypatch.setattr(catalog.httpx,'AsyncClient',lambda **kwargs:client_class(**kwargs,transport=httpx.MockTransport(handle)))
    result=client.post('/api/settings/speech/kept/models',json=body|{'apiKey':'','model':''})
    assert result.json()['models']==['qwen3-asr-flash-realtime']
    assert client.get('/api/settings/speech').json()['profiles'][-1]['model']=='qwen3-asr-flash-realtime'
    assert client.post('/api/settings/speech/kept/models',json=body|{'clearApiKey':True}).status_code==400


@pytest.mark.parametrize('status,payload',[(404,{}),(401,{'message':'fixture-key secret'}),(200,{'output':{'models':'invalid'}}),(200,{'success':False,'message':'fixture-key'})])
def test_errors_are_honest_and_do_not_expose_credentials(module,monkeypatch,status,payload):
    client_class=httpx.AsyncClient
    monkeypatch.setattr(catalog.httpx,'AsyncClient',lambda **kwargs:client_class(**kwargs,transport=httpx.MockTransport(lambda _:httpx.Response(status,json=payload))))
    result=TestClient(module.app).post('/api/settings/speech/draft/models',json=config())
    assert result.status_code==400 and 'fixture-key' not in result.text


def test_empty_catalog_never_substitutes_a_builtin_list(module,monkeypatch):
    client_class=httpx.AsyncClient
    monkeypatch.setattr(catalog.httpx,'AsyncClient',lambda **kwargs:client_class(**kwargs,transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'output':{'models':[],'total':0}}))))
    assert TestClient(module.app).post('/api/settings/speech/draft/models',json=config()).json()['models']==[]
