import asyncio
import base64
from concurrent.futures import ThreadPoolExecutor
import importlib
import io
import json
import sqlite3
import sys

import httpx
from PIL import Image
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import ocr_locator, ocr_usage, ocr_settings, paddle_ocr, capture_processing

@pytest.fixture
def app(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    with TestClient(module.app) as client: yield client,module,tmp_path

def image():
    buffer=io.BytesIO();Image.new('RGB',(100,60),'white').save(buffer,format='PNG')
    return {'id':'synthetic','name':'fixture.png','data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),'width':100,'height':60,'scenario':'custom'}

def settings(**changes):
    return {'apiKey':'synthetic-secret','baseUrl':'https://ocr.example/api/v2/ocr/jobs','apiMode':'async',
            'enabled':True,'model':'PaddleOCR-VL-1.6','dailyLimit':20000,**changes}

def local_document():
    return {'text':'local text','regions':[{'text':'local text','bbox':[3,4,70,20],'page':0,'granularity':'line'}],
            'width':100,'height':60,'mode':'windows-ocr','coordinateSpace':'image-pixels'}


def test_local_ocr_reuse_is_bounded_expires_and_does_not_share_mutable_results(tmp_path,monkeypatch):
    calls=[]
    monkeypatch.setattr(ocr_locator,'active_ocr',lambda _:None)
    async def local(data):calls.append(data);return local_document()
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    asset=image()['data']
    async def run():
        first=await ocr_locator.locate(tmp_path/'cache.db',asset,require_lines=True)
        first['regions'][0]['text']='changed by caller'
        cached=await ocr_locator.locate(tmp_path/'cache.db',asset)
        assert cached['cacheHit'] and cached['regions'][0]['text']=='local text' and len(calls)==1
        await ocr_locator.locate(tmp_path/'other.db',asset)
        assert len(calls)==2
        buffer=io.BytesIO();modified=Image.new('RGB',(100,60),'white');modified.putpixel((0,0),(0,0,0));modified.save(buffer,format='PNG')
        changed='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()
        await ocr_locator.locate(tmp_path/'cache.db',changed)
        assert len(calls)==3,'Different pixels must never reuse an old OCR result'
        monkeypatch.setattr(ocr_locator,'LOCAL_CACHE_TTL',0)
        await ocr_locator.locate(tmp_path/'cache.db',asset)
        assert len(calls)==4
    asyncio.run(run())

def install_transport(monkeypatch,handler):
    real=httpx.AsyncClient
    monkeypatch.setattr(paddle_ocr.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    monkeypatch.setattr(paddle_ocr,'POLL_INTERVAL',0)

def test_async_submit_poll_jsonl_and_line_geometry(app,monkeypatch):
    client,module,_=app
    client.put('/api/settings/ocr',json=settings())
    requests=[];states=iter(['pending','running','done'])
    def transport(request):
        requests.append(request)
        if request.url.host=='result.example':
            assert 'authorization' not in request.headers
            payload={'result':{'layoutParsingResults':[{'prunedResult':{
                'overall_ocr_res':{'rec_texts':['fixture'],'rec_boxes':[[5,6,45,20]]},
                'parsing_res_list':[{'block_content':'duplicate block','block_bbox':[0,0,99,59]}]}}]}}
            return httpx.Response(200,text=json.dumps(payload)+'\n')
        assert request.headers['Authorization']=='bearer synthetic-secret'
        if request.method=='POST':
            assert 'multipart/form-data' in request.headers['content-type']
            assert b'PaddleOCR-VL-1.6' in request.content and b'useDocUnwarping' in request.content
            assert b'name="file"' in request.content and b'\x89PNG' in request.content
            return httpx.Response(200,json={'code':0,'data':{'jobId':'test-job'}})
        state=next(states)
        return httpx.Response(200,json={'data':{'state':state,'resultUrl':{'jsonUrl':'https://result.example/results.jsonl?signature=synthetic'}}})
    install_transport(monkeypatch,transport)
    async def forbidden(*_): raise AssertionError('Cloud success must not start local OCR or LLM')
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',forbidden)
    monkeypatch.setattr(module,'complete',forbidden)
    result=client.post('/api/capture/locate',json={'asset':image()})
    assert result.status_code==200
    data=result.json()
    assert data['mode']=='paddleocr' and data['fallback'] is False and data['apiMode']=='async'
    assert data['regions'][0]['bbox']==[5,6,45,20] and data['regions'][0]['id']=='text-1'
    assert data['regions'][0]['granularity']=='line' and len(data['regions'])==1
    assert len(requests)==5 and data['usage']['submitted']==1
    assert client.get('/api/usage').json()['ocrRequests']==1
    assert 'synthetic-secret' not in json.dumps(data)

def test_daily_budget_atomic_persistent_and_next_day(app,monkeypatch):
    client,module,_=app
    client.put('/api/settings/ocr',json=settings(dailyLimit=2))
    config=ocr_settings.active_ocr(module.DB)
    with ThreadPoolExecutor(max_workers=6) as pool:
        outcomes=list(pool.map(lambda _:ocr_usage.reserve(module.DB,config),range(6)))
    assert outcomes.count(None)==2 and outcomes.count('daily-limit')==4
    assert ocr_usage.usage_summary(module.DB,config)['submitted']==2
    async def forbidden(*_): raise AssertionError('Exhausted budget must bypass cloud')
    async def local(*_): return local_document()
    monkeypatch.setattr(ocr_locator,'recognize_paddle',forbidden)
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    result=client.post('/api/capture/locate',json={'asset':image()}).json()
    assert result['fallbackReason']=='daily-limit' and result['mode']=='windows-ocr'
    monkeypatch.setattr(ocr_usage,'today',lambda:'2099-01-02')
    assert ocr_usage.usage_summary(module.DB,config)['submitted']==0
    assert ocr_usage.reserve(module.DB,config) is None

@pytest.mark.parametrize('failure,reason',[('quota','cloud-quota'),('http-quota','cloud-quota'),('http','unavailable'),('auth','authentication'),('rate','rate-limit'),('network','unavailable'),('timeout','timeout'),('malformed','invalid-result'),('missing-coordinates','invalid-result'),('failed','unavailable')])
def test_remote_failures_fall_back_and_cool_down(app,monkeypatch,failure,reason):
    client,module,_=app;client.put('/api/settings/ocr',json=settings())
    calls=[]
    def transport(request):
        calls.append(request)
        if failure=='network': raise httpx.ConnectError('synthetic-secret hidden',request=request)
        if failure=='timeout': raise httpx.ReadTimeout('synthetic-secret hidden',request=request)
        if failure=='http': return httpx.Response(503,text='synthetic-secret')
        if failure=='auth': return httpx.Response(401,text='synthetic-secret')
        if failure=='rate': return httpx.Response(429,text='synthetic-secret')
        if failure=='http-quota': return httpx.Response(429,json={'msg':'daily quota exhausted synthetic-secret'})
        if failure=='quota': return httpx.Response(200,json={'code':10003,'msg':'daily quota exhausted synthetic-secret'})
        if failure=='malformed': return httpx.Response(200,json={'data':{'state':'unknown'}})
        if request.method=='POST': return httpx.Response(200,json={'data':{'jobId':'job'}})
        if failure=='failed': return httpx.Response(200,json={'data':{'state':'failed','errorMsg':'synthetic-secret internal error'}})
        if request.url.host=='result.example':
            return httpx.Response(200,text=json.dumps({'result':{'layoutParsingResults':[{'markdown':{'text':'text without coordinates'}}]}}))
        return httpx.Response(200,json={'data':{'state':'done','resultUrl':{'jsonUrl':'https://result.example/output'}}})
    install_transport(monkeypatch,transport)
    async def local(*_): return local_document()
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    for _ in range(2):
        response=client.post('/api/capture/locate',json={'asset':image()})
        assert response.status_code==200
        data=response.json()
        assert data['mode']=='windows-ocr' and data['fallbackReason']==reason
        assert 'synthetic-secret' not in json.dumps(data)
    assert len(calls)==(3 if failure=='missing-coordinates' else 2 if failure=='failed' else 1)
    assert client.get('/api/settings/ocr').json()['usage']['submitted']==1
    assert client.get('/api/usage').json()['ocrRequests']==1

def test_disabled_and_incomplete_settings_use_local(app,monkeypatch):
    client,module,_=app
    async def local(*_): return local_document()
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    assert client.post('/api/capture/locate',json={'asset':image()}).json()['fallbackReason']=='disabled'
    monkeypatch.setattr(ocr_locator,'active_ocr',lambda _:(_ for _ in ()).throw(HTTPException(400,'incomplete')))
    assert client.post('/api/capture/locate',json={'asset':image()}).json()['fallbackReason']=='configuration'
    assert client.get('/api/usage').json()['requests']==0

def test_timeout_bound_cancellation_and_no_unnecessary_fallback(app,monkeypatch):
    client,module,_=app;client.put('/api/settings/ocr',json=settings())
    def pending(request):
        if request.method=='POST': return httpx.Response(200,json={'data':{'jobId':'job'}})
        return httpx.Response(200,json={'data':{'state':'pending'}})
    install_transport(monkeypatch,pending)
    monkeypatch.setattr(paddle_ocr,'JOB_TIMEOUT',.02)
    monkeypatch.setattr(paddle_ocr,'POLL_INTERVAL',1)
    async def local(*_): return local_document()
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    assert client.post('/api/capture/locate',json={'asset':image()}).json()['fallbackReason']=='timeout'
    async def cancelled(*_): raise asyncio.CancelledError()
    async def forbidden(*_): raise AssertionError('Cancelled request must not run fallback')
    monkeypatch.setattr(ocr_locator,'recognize_paddle',cancelled)
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',forbidden)
    config=ocr_settings.active_ocr(module.DB)
    with sqlite3.connect(module.DB) as db: db.execute('DELETE FROM ocr_daily_usage')
    with pytest.raises(asyncio.CancelledError): asyncio.run(ocr_locator.locate(module.DB,image()['data']))

def test_invalid_image_consumes_no_quota_and_local_errors_are_reported(app,monkeypatch):
    client,module,_=app;client.put('/api/settings/ocr',json=settings())
    bad=image() | {'data':'data:image/png;base64,aGVsbG8='}
    assert client.post('/api/capture/locate',json={'asset':bad}).status_code==400
    assert client.get('/api/settings/ocr').json()['usage']['submitted']==0
    client.put('/api/settings/ocr',json=settings(enabled=False))
    async def unavailable(*_): raise HTTPException(503,'Windows OCR 不可用')
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',unavailable)
    assert client.post('/api/capture/locate',json={'asset':image()}).status_code==503

def test_short_cloud_deadline_cancels_wait_and_falls_back_once(app,monkeypatch):
    client,module,_=app;client.put('/api/settings/ocr',json=settings())
    calls=[]
    async def cloud(*args):
        calls.append('cloud')
        try:await asyncio.Event().wait()
        finally:calls.append('cancelled')
    async def local(*args):calls.append('local');return local_document()
    monkeypatch.setattr(ocr_locator,'recognize_paddle',cloud)
    monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    result=asyncio.run(ocr_locator.locate(module.DB,image()['data'],require_lines=True,cloud_timeout=.01))
    assert result['fallbackReason']=='timeout' and result['mode']=='windows-ocr'
    assert calls==['cloud','cancelled','local']
    assert client.get('/api/usage').json()['ocrRequests']==1

def test_env_import_preserves_llms_and_ui_changes(app):
    client,module,root=app
    llm={'name':'Synthetic LLM','vendor':'custom','provider':'openai-compatible','baseUrl':'https://llm.example/v1','model':'fixture','vision':True}
    client.put('/api/settings/models/custom',json=llm);client.put('/api/settings/models/active',json={'activeId':'custom'})
    (root/'.env').write_text('PADDLE_OCR_KEY="synthetic-env-secret"\nMAX_IMAGES_NUM=20,000\nUNRELATED_KEY=do-not-import\n',encoding='utf-8')
    ocr_settings.import_ocr_environment(module.DB)
    public=client.get('/api/settings/ocr').json()
    assert public['model']=='PaddleOCR-VL-1.6' and public['apiMode']=='async' and public['dailyLimit']==20000 and public['enabled']
    assert public['hasApiKey'] and 'synthetic-env-secret' not in json.dumps(public)
    assert client.get('/api/settings/models').json()['activeId']=='custom'
    assert client.get('/api/settings/config').json()['ocr']['apiKey']=='••••••••••'
    client.put('/api/settings/ocr',json=settings(enabled=False,dailyLimit=123,apiKey=None))
    ocr_settings.import_ocr_environment(module.DB)
    assert client.get('/api/settings/ocr').json()['dailyLimit']==123
    assert not client.get('/api/settings/ocr').json()['enabled']

def test_translate_receives_ocr_geometry_but_text_extraction_remains_llm(app,monkeypatch):
    client,module,_=app;client.put('/api/settings/ocr',json=settings())
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True,'model':'fixture'})
    calls=[]
    async def locate(path,data): calls.append(data);return local_document() | {'fallback':True}
    async def complete(profile,session,assets,action,prompt,path):
        assert len(assets)==1
        if action=='translate': assert 'image-pixels' in prompt and '[3, 4, 70, 20]' in prompt
        else: assert 'image-pixels' not in prompt
        return {'text':'result'}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    for action in ('translate','ocr','explain'):
        result=client.post('/api/capture/process',json={'asset':image(),'engine':'multimodal','action':action})
        assert result.status_code==200
        assert ('location' in result.json())==(action=='translate')
    assert len(calls)==1

def test_windows_scaled_tiled_coordinates_map_to_original(monkeypatch):
    buffer=io.BytesIO();Image.new('RGB',(3000,3000),'white').save(buffer,format='PNG')
    class Process:
        returncode=0
        stdout=json.dumps({'text':'first\nsecond','documents':[{'lines':[{'words':[{'text':'first','bbox':[10,20,50,40]}]}]},
                                                                  {'lines':[{'words':[{'text':'second','bbox':[10,20,50,40]}]}]}]})
    def run(*args,**kwargs):
        assert len(json.loads(kwargs['input'])['images'])==2
        return Process()
    monkeypatch.setattr(capture_processing.subprocess,'run',run)
    result=capture_processing.recognize_positions('data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode())
    assert result['regions'][0]['bbox']==[12.5,25,62.5,50]
    assert result['regions'][1]['bbox']==[12.5,2525,62.5,2550]

def test_result_urls_do_not_allow_local_resources():
    for url in ('http://result.example/a','https://127.0.0.1/a','https://[::1]/a','https://[fd00::1]/a','https://localhost/a','https://user:pass@result.example/a'):
        with pytest.raises(ValueError): paddle_ocr.result_url(url)
    assert paddle_ocr.result_url('https://result.example/a?signature=x').endswith('signature=x')

def test_unreadable_cached_key_is_recovered_from_existing_configuration(app,monkeypatch):
    client,module,_=app
    client.put('/api/settings/ocr',json=settings())
    def cached_key_unavailable(_): raise HTTPException(400,'Cached Windows protection context unavailable')
    monkeypatch.setattr(ocr_settings,'unprotect_key',cached_key_unavailable)
    with sqlite3.connect(module.DB) as db:
        recovered=ocr_settings.read_ocr(db)
    assert recovered['apiKeyProtected'] and recovered['enabled']
