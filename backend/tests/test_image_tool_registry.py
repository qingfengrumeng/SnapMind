import copy
import pytest
from PIL import Image, ImageDraw
from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module
from backend.app.image_tools import png_data, image_from_data


def context():
    image = Image.new('RGB', (160, 100), 'white')
    ImageDraw.Draw(image).rectangle((20, 30, 69, 59), fill='purple')
    return {'assets': [{'id': 'image-1', 'name': 'Generated image', 'data': png_data(image),
                        'width': 160, 'height': 100, 'scenario': 'custom'}], 'selectedId': 'image-1',
            'history': [{'role': 'user', 'text': 'Earlier question'}, {'role': 'assistant', 'text': 'Earlier answer'}]}


def test_catalog_contains_operations_without_conversation_shortcuts(module):
    response = TestClient(module.app).get('/api/tools')
    assert response.status_code == 200
    tools = {t['function']['name']: t['function'] for t in response.json()['tools']}
    assert set(tools) == {'region', 'qr', 'entities', 'table', 'annotate', 'detect', 'ocr', 'offline',
                          'translate', 'crop', 'highlight', 'mosaic', 'heal', 'lift', 'answer', 'draw', 'blur', 'undo', 'clear_annotations'}
    assert 'bbox' in tools['region']['parameters']['required']
    assert 'bbox' in tools['crop']['parameters']['required'],'Explicit crop UI keeps its coordinate field; natural-language agent uses its internal text-target schema'
    assert 'targetText' in tools['highlight']['parameters']['required']
    assert tools['annotate']['parameters']['additionalProperties'] is False
    assert tools['translate']['parameters']['properties']['language']['enum'] == ['zh-CN', 'zh-TW', 'en']


def test_region_is_exact_additional_image_without_llm_or_history_write(module, monkeypatch):
    async def never(*args, **kwargs):
        raise AssertionError('A pixel region must not call LLM or OCR')
    monkeypatch.setattr(module, 'complete', never)
    monkeypatch.setattr(module, 'locate', never)
    body = {'name': 'region', 'arguments': {'bbox': [20, 30, 70, 60]}, 'context': context()}
    before = copy.deepcopy(body)
    client = TestClient(module.app)
    response = client.post('/api/tools/call', json=body)
    assert response.status_code == 200
    result = response.json()
    assert result['action'] == 'region' and result['assetId'] == 'image-1'
    assert (result['payload']['width'], result['payload']['height']) == (50, 30)
    cropped = image_from_data(result['payload']['data'])
    assert cropped.getpixel((0, 0)) == (128, 0, 128)
    assert cropped.getpixel((49, 29)) == (128, 0, 128)
    assert body == before
    assert client.get('/api/sessions').json() == []
    assert client.get('/api/usage').json()['requests'] == 0


@pytest.mark.parametrize('arguments,status', [({}, 422), ({'bbox': [-1, 0, 30, 30]}, 422),
    ({'bbox': [10, 10, 161, 40]}, 400), ({'bbox': [30, 30, 20, 40]}, 422),
    ({'bbox': [0, 0, 10]}, 422), ({'bbox': [0, 0, 10, 10], 'path': 'unexpected'}, 422)])
def test_region_rejects_missing_or_invalid_geometry(module, arguments, status):
    assert TestClient(module.app).post('/api/tools/call', json={
        'name': 'region', 'arguments': arguments, 'context': context()}).status_code == status


@pytest.mark.parametrize('name', ['chat', 'note', 'explain', 'code', 'paper', 'exam', 'formula'])
def test_conversation_shortcuts_are_not_callable_tools(module, monkeypatch, name):
    async def never(*args, **kwargs):
        raise AssertionError('Removed tool must not execute a model')
    monkeypatch.setattr(module, 'complete', never)
    response = TestClient(module.app).post('/api/tools/call', json={
        'name': name, 'arguments': {}, 'context': context()})
    assert response.status_code == 422


@pytest.mark.parametrize('name', ['annotate', 'detect', 'table', 'qr', 'entities', 'offline', 'ocr'])
def test_explicit_tool_dispatch_bypasses_intent_classification(module, monkeypatch, name):
    calls = []
    async def spy(*args, **kwargs):
        calls.append((args, kwargs))
        payload={'width':160,'height':100,'coordinateSpace':'image-pixels'}
        if name=='annotate':payload['annotations']=[]
        if name=='detect':payload['objects']=[]
        if name=='table':payload={'tables':[]}
        return {'action': args[10], 'assetId': args[2], 'answer': 'verified dispatch', 'payload': payload}
    import backend.app.agent.tools as agent_tools
    monkeypatch.setattr(agent_tools, 'converse', spy)
    response = TestClient(module.app).post('/api/tools/call', json={
        'name': name, 'arguments': {'imageId': 'image-1', 'prompt': 'A follow-up request'}, 'context': context()})
    assert response.status_code == 200 and response.json()['action'] == name
    assert len(calls) == 1
    args, kwargs = calls[0]
    assert args[3] == 'A follow-up request' and args[10] == name
    assert [t.text for t in args[4]] == ['Earlier question', 'Earlier answer']


@pytest.mark.parametrize('body', [
    {'name': 'snapshot', 'arguments': {}},
    {'name': 'region', 'arguments': {'bbox': [0, 0, 10, 10]}, 'unexpected': True},
    {'name': 'explain', 'arguments': {'bbox': [0, 0, 10, 10]}},
    {'name': 'highlight', 'arguments': {}},
    {'name': 'translate', 'arguments': {'language': 'unknown'}},
])
def test_unknown_tools_and_unexpected_arguments_rejected(module, body):
    assert TestClient(module.app).post('/api/tools/call', json={**body, 'context': context()}).status_code == 422


def test_missing_or_mismatched_image_fails_without_model_call(module, monkeypatch):
    async def never(*args, **kwargs):
        raise AssertionError('Invalid image must fail before inference')
    monkeypatch.setattr(module, 'complete', never)
    client = TestClient(module.app)
    for args in [{'imageId': 'missing', 'bbox': [0, 0, 10, 10]}]:
        assert client.post('/api/tools/call', json={'name': 'region', 'arguments': args, 'context': context()}).status_code == 400
    invalid = context()
    invalid['assets'][0]['width'] = 161
    assert client.post('/api/tools/call', json={'name': 'qr', 'context': invalid}).status_code == 400


def test_note_metadata_survives_history_save(module):
    from backend.tests.test_image_history import session
    saved = session()
    saved['messages'][0]['imageResult']['note'] = {'markdown': '# Note\n\nEarlier answer', 'imageIds': ['picture-1']}
    client = TestClient(module.app)
    assert client.put('/api/sessions/' + saved['id'], json=saved).status_code == 200
    assert client.get('/api/sessions').json()[0]['messages'][0]['imageResult']['note'] == saved['messages'][0]['imageResult']['note']
