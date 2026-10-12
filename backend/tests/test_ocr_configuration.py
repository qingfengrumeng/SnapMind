import base64
import importlib
import io
import json
import sys
from concurrent.futures import ThreadPoolExecutor
import httpx
import pytest
from PIL import Image
from fastapi.testclient import TestClient
from backend.app import paddle_ocr

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    with TestClient(module.app) as value:yield value,module,tmp_path

def config(**changes):
    return {'baseUrl':'https://ocr.example/ocr','model':'PP-OCRv5','apiKey':'synthetic-private-token','enabled':False,'assistLlm':True,'apiMode':'sync',**changes}

def asset():
    out=io.BytesIO();Image.new('RGB',(100,60),'white').save(out,format='PNG')
    return {'id':'ocr-fixture','name':'fixture.png','width':100,'height':60,'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(out.getvalue()).decode()}

def test_independent_configuration_masking_and_secret_preservation(client):
    c,_,root=client
    assert not c.get('/api/settings/ocr').json()['enabled']
    assert c.put('/api/settings/ocr',json=config(enabled=True)).status_code==200
    result=c.get('/api/settings/ocr').json()
    assert result['hasApiKey'] and result['apiKeyUrl']=='https://aistudio.baidu.com/paddleocr'
    assert 'synthetic-private-token' not in json.dumps(result)
    llm={'name':'Test LLM','vendor':'custom','provider':'openai-compatible','baseUrl':'http://127.0.0.1:9999/v1','model':'vision-fixture','vision':True}
    assert c.put('/api/settings/models/custom',json=llm).status_code==200
    assert c.put('/api/settings/models/active',json={'activeId':'custom'}).status_code==200
    assert c.get('/api/settings/ocr').json()['enabled']
    assert all(p['vendor']!='paddleocr' for p in c.get('/api/settings/models').json()['profiles'])
    assert c.get('/api/settings/config').json()['ocr']['apiKey']=='••••••••••'
    assert c.put('/api/settings/ocr',json=config(apiKey=None,assistLlm=False)).status_code==200
    document=json.loads((root/'.snapmind').read_text(encoding='utf-8'))
    assert document['ocr']['apiKey']=='synthetic-private-token'
    assert 'dailyLimit' not in document['ocr']
    assert 'models' not in result
    assert document['activeModelId']=='custom'
    assert c.put('/api/settings/ocr',json=config(apiKey=None,clearApiKey=True,enabled=True)).status_code==400
    assert c.put('/api/settings/ocr',json=config(apiKey=None,clearApiKey=True)).json()['hasApiKey'] is False

def test_concurrent_llm_and_ocr_writes_keep_both_groups(client):
    c,_,root=client
    llm={'name':'Test','vendor':'custom','provider':'openai-compatible','baseUrl':'http://127.0.0.1:9999/v1','model':'fixture','vision':False}
    with ThreadPoolExecutor(max_workers=2) as pool:
        writes=[pool.submit(c.put,'/api/settings/models/custom',json=llm),pool.submit(c.put,'/api/settings/ocr',json=config())]
        assert all(w.result().status_code==200 for w in writes)
    document=json.loads((root/'.snapmind').read_text(encoding='utf-8'))
    assert document['ocr']['apiKey']=='synthetic-private-token'
    assert next(m for m in document['models'] if m['id']=='custom')['model']=='fixture'

def test_ocr_and_multimodal_assistance_use_real_coordinates(client,monkeypatch):
    c,module,_=client
    c.put('/api/settings/ocr',json=config(enabled=True))
    real=httpx.AsyncClient; requests=[]
    def transport(req):
        requests.append(req)
        assert req.headers['Authorization']=='token synthetic-private-token'
        body=json.loads(req.content)
        assert body['fileType']==1 and body['useDocUnwarping'] is False
        assert body['file']==asset()['data'].split(',')[1]
        return httpx.Response(200,json={'errorCode':0,'result':{'ocrResults':[{'prunedResult':{'rec_texts':['fixture text'],'rec_scores':[.98],'rec_polys':[[[5,6],[45,6],[45,20],[5,20]]]}}]}})
    monkeypatch.setattr(paddle_ocr.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(transport),**kw))
    result=c.post('/api/capture/process',json={'asset':asset(),'action':'ocr'}).json()
    assert result['text']=='fixture text' and result['mode']=='paddleocr'
    assert result['regions'][0]['bbox']==[5,6,45,20]
    assert result['width']==100 and result['coordinateSpace']=='image-pixels'
    assert c.post('/api/capture/locate',json={'asset':asset()}).json()['regions']==result['regions']
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    async def complete(profile,session,assets,action,prompt,db):
        assert len(assets)==1 and 'image-pixels' in prompt and 'fixture text' in prompt
        assert '[5, 6, 45, 20]' in prompt
        return {'text':'assisted'}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/process',json={'asset':asset(),'action':'explain'}).json()['text']=='assisted'
    assert len(requests)==3

def test_layout_blocks_and_markdown_keep_positions():
    result=paddle_ocr.parse_result({'result':{'layoutParsingResults':[{'prunedResult':{'parsing_res_list':[{'block_label':'table','block_bbox':[10,20,80,50],'block_content':'cells'}]},'markdown':{'text':'| table |'}}]}})
    assert result['text']=='| table |'
    assert result['regions'][0]['bbox']==[10,20,80,50] and result['regions'][0]['label']=='table'

def test_connection_probe_sends_no_image_and_errors_hide_keys(client,monkeypatch):
    c,_,_=client;c.put('/api/settings/ocr',json=config())
    real=httpx.AsyncClient;status=405
    def transport(req):
        assert req.method=='HEAD' and not req.content
        return httpx.Response(status)
    monkeypatch.setattr(paddle_ocr.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(transport),**kw))
    result=c.post('/api/settings/ocr/test',json=config(apiKey=None)).json()
    assert result['ok'] and result['latencyMs']>=0 and result['authVerified'] is False
    status=401
    result=c.post('/api/settings/ocr/test',json=config(apiKey=None)).json()
    assert not result['ok'] and 'synthetic-private-token' not in str(result)


def test_model_list_is_explicit_authenticated_and_never_persisted(client,monkeypatch):
    from backend.app import ocr_model_catalog
    c,_,root=client
    assert c.post('/api/settings/ocr/models',json=config(apiKey=None)).status_code==400
    c.put('/api/settings/ocr',json=config(dailyLimit=123))
    before=(root/'.snapmind').read_text(encoding='utf-8')
    real=httpx.AsyncClient;calls=[]
    def transport(req):
        calls.append(req)
        assert req.method=='GET' and not req.content
        assert req.headers['Authorization']=='token synthetic-private-token'
        if req.url.path=='/openapi.json':
            return httpx.Response(200,json={'openapi':'3.1.0','paths':{'/catalog/models':{'get':{}}}})
        assert req.url.path=='/catalog/models'
        if req.url.params.get('after'):
            return httpx.Response(200,json={'data':[{'id':'remote-next'},{'id':'remote-model'}]})
        return httpx.Response(200,json={'data':[{'id':'remote-model'}],'has_more':True,'last_id':'cursor'})
    monkeypatch.setattr(ocr_model_catalog.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(transport),**kw))
    assert 'models' not in c.get('/api/settings/ocr').json()
    assert calls==[]
    result=c.post('/api/settings/ocr/models',json=config(apiKey=None)).json()
    assert result['models']==['remote-model','remote-next']
    assert len(calls)==3
    assert (root/'.snapmind').read_text(encoding='utf-8')==before
    assert c.get('/api/settings/ocr').json()['usage']['submitted']==0
    assert c.put('/api/settings/ocr',json=config(apiKey=None,model='remote-next')).status_code==200
    assert c.get('/api/settings/ocr').json()['dailyLimit']==123
    assert 'dailyLimit' not in c.get('/api/settings/config').json()['ocr']


def test_unsupported_ocr_catalog_keeps_manual_entry_and_hides_credentials(client,monkeypatch):
    from backend.app import ocr_model_catalog
    c,_,_=client
    real=httpx.AsyncClient
    def transport(req): return httpx.Response(404,json={'detail':'synthetic-private-token'})
    monkeypatch.setattr(ocr_model_catalog.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(transport),**kw))
    for url in ['https://ocr.example/ocr','https://paddleocr.aistudio-app.com/api/v2/ocr/jobs']:
        result=c.post('/api/settings/ocr/models',json=config(baseUrl=url))
        assert result.status_code==400
        assert '手动输入' in result.json()['detail']
        assert 'synthetic-private-token' not in result.text


def test_old_json_limit_migrates_without_resetting_internal_fallback_budget(client):
    from backend.app.ocr_settings import migrate_ocr_configuration
    c,module,root=client
    c.put('/api/settings/ocr',json=config(dailyLimit=71))
    document=json.loads((root/'.snapmind').read_text(encoding='utf-8'))
    document['ocr']['dailyLimit']=59
    (root/'.snapmind').write_text(json.dumps(document),encoding='utf-8')
    migrate_ocr_configuration(module.DB)
    assert 'dailyLimit' not in json.loads((root/'.snapmind').read_text(encoding='utf-8'))['ocr']
    assert c.get('/api/settings/ocr').json()['dailyLimit']==59
    c.put('/api/settings/models/custom',json={'name':'Test','vendor':'custom','provider':'openai-compatible','baseUrl':'https://example.invalid/v1','model':'fixture','vision':False})
    assert 'dailyLimit' not in json.loads((root/'.snapmind').read_text(encoding='utf-8'))['ocr']
