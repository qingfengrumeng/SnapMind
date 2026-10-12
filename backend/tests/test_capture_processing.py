import importlib
import sys
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def module(tmp_path, monkeypatch):
    monkeypatch.setenv('SNAPMIND_DATA_DIR', str(tmp_path))
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE', str(tmp_path / '.snapmind'))
    sys.modules.pop('backend.app.main', None)
    return importlib.import_module('backend.app.main')

ASSET = {'id':'fixture', 'name':'fixture.png', 'data':'data:image/png;base64,aGVsbG8=', 'width':100, 'height':100, 'scenario':'custom'}

def test_ocr_local_without_model_or_history(module, monkeypatch):
    monkeypatch.setattr(module, 'get_active_profile', lambda _: None)
    async def recognize(_): return 'Recognized text'
    async def never(*_): raise AssertionError('OCR must not call a remote model')
    monkeypatch.setattr(module, 'recognize_async', recognize)
    monkeypatch.setattr(module, 'complete', never)
    with TestClient(module.app) as client:
        assert client.post('/api/capture/process', json={'asset':ASSET,'action':'ocr'}).json() == {'text':'Recognized text','mode':'local-ocr'}
        assert client.get('/api/sessions').json() == []
        assert client.post('/api/capture/process', json={'asset':ASSET,'action':'translate'}).status_code == 400

@pytest.mark.parametrize('vision', [False, True])
def test_text_and_vision_model_routing(module, monkeypatch, vision):
    monkeypatch.setattr(module, 'get_active_profile', lambda _: {'vision':vision})
    async def recognize(_):
        assert not vision, 'Vision model should receive the image directly'
        return 'fixture text'
    async def complete(profile, session, assets, action, prompt, db):
        assert not session.messages
        assert len(assets) == int(vision)
        assert action == ('translate' if vision else 'chat')
        assert 'English' in prompt
        assert ('fixture text' in prompt) == (not vision)
        return {'text':'Translated fixture'}
    monkeypatch.setattr(module,'recognize_async',recognize)
    monkeypatch.setattr(module,'complete',complete)
    with TestClient(module.app) as client:
        result=client.post('/api/capture/process',json={'asset':ASSET,'action':'translate','language':'en'})
        assert result.status_code == 200
        assert result.json()['text'] == 'Translated fixture'
        assert client.get('/api/sessions').json() == []

def test_empty_ocr_and_action_validation(module, monkeypatch):
    async def recognize(_): return ''
    monkeypatch.setattr(module,'recognize_async',recognize)
    with TestClient(module.app) as client:
        assert client.post('/api/capture/process',json={'asset':ASSET,'action':'ocr'}).status_code == 400
        assert client.post('/api/capture/process',json={'asset':ASSET,'action':'chat'}).status_code == 422

@pytest.mark.parametrize('action', ['ocr','translate','explain'])
def test_direct_multimodal_uses_action_specific_instructions(module, monkeypatch, action):
    profile = {'vision':True,'name':'DeepSeek fixture','model':'synthetic'}
    monkeypatch.setattr(module,'get_active_profile',lambda _:profile)
    async def forbidden(*_): raise AssertionError('Direct multimodal processing must not call OCR')
    monkeypatch.setattr(module,'recognize_async',forbidden)
    monkeypatch.setattr(module,'recognize_paddle',forbidden)
    text = '标题\n\n  缩进正文\n项目\t数量\nA\t2\n'
    async def complete(selected_profile, session, assets, selected_action, prompt, db):
        assert selected_profile == profile
        assert len(assets)==1 and assets[0].data==ASSET['data']
        assert selected_action==action and not session.messages
        if action=='explain':
            assert all(word in prompt for word in ['这是什么','用途','作用','English'])
            assert '不要合并原有换行' not in prompt
            assert '保留标题、段落' not in prompt
        else:
            assert all(word in prompt for word in ['换行','空行','缩进','表格'])
            assert '逐字' in prompt if action=='ocr' else 'English' in prompt
        return {'text':text}
    monkeypatch.setattr(module,'complete',complete)
    with TestClient(module.app) as client:
        result=client.post('/api/capture/process',json={'asset':ASSET,'action':action,'engine':'multimodal','language':'en'})
        assert result.status_code==200
        assert result.json()=={'text':text,'mode':'model','model':'DeepSeek fixture'}
        assert client.get('/api/sessions').json()==[]

@pytest.mark.parametrize('profile', [None, {'vision':False}])
def test_direct_multimodal_requires_image_model(module, monkeypatch, profile):
    monkeypatch.setattr(module,'get_active_profile',lambda _:profile)
    with TestClient(module.app) as client:
        for action in ['ocr','translate','explain']:
            result=client.post('/api/capture/process',json={'asset':ASSET,'action':action,'engine':'multimodal'})
            assert result.status_code==400
            assert '模型' in result.json()['detail']

def test_transcription_is_not_truncated_in_a_table(module, monkeypatch):
    import json
    import httpx
    from backend.app import model_inference
    profile={'vision':True,'name':'Synthetic','model':'fixture','provider':'openai-compatible','baseUrl':'https://example.invalid/v1'}
    monkeypatch.setattr(module,'get_active_profile',lambda _:profile)
    original='标题\n\n'+('  A\t2\n'*4000)+'最后一行\n'
    real=httpx.AsyncClient
    def transport(request):
        body=json.loads(request.content)
        assert body['messages'][-1]['content'][1]['image_url']['url']==ASSET['data']
        return httpx.Response(200,json={'choices':[{'message':{'content':original}}]})
    monkeypatch.setattr(model_inference.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(transport),**kwargs))
    with TestClient(module.app) as client:
        result=client.post('/api/capture/process',json={'asset':ASSET,'action':'ocr','engine':'multimodal'})
        assert result.status_code==200 and result.json()['text']==original

def test_transcription_skips_uncertain_characters_and_allows_blank(module, monkeypatch):
    import json
    import httpx
    from backend.app import model_inference
    monkeypatch.setattr(module,'get_active_profile',lambda _:{'vision':True,'name':'Synthetic','model':'fixture','provider':'openai-compatible','baseUrl':'https://example.invalid/v1'})
    outputs=iter(['[无法辨认]0443\n\n  项目【无法识别】\t2\n无法辨认是正常文字\n',''])
    real=httpx.AsyncClient
    def transport(request):
        body=json.loads(request.content)
        assert '纯文字转录' in body['messages'][0]['content']
        assert '不描述图片' in body['messages'][-1]['content'][0]['text']
        return httpx.Response(200,json={'choices':[{'message':{'content':next(outputs)}}]})
    monkeypatch.setattr(model_inference.httpx,'AsyncClient',lambda **kwargs:real(transport=httpx.MockTransport(transport),**kwargs))
    with TestClient(module.app) as client:
        request={'asset':ASSET,'action':'ocr','engine':'multimodal'}
        result=client.post('/api/capture/process',json=request)
        assert result.status_code==200
        assert result.json()['text']=='0443\n\n  项目\t2\n无法辨认是正常文字\n'
        blank=client.post('/api/capture/process',json=request)
        assert blank.status_code==200 and blank.json()['text']==''
