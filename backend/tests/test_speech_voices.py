import asyncio
import json

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from backend.app import speech_voices as voices
from backend.app.speech_settings import SpeechProfile
from backend.tests.test_capture_processing import module


DOCUMENT = '''<h3>qwen-audio-3.1-tts-flash <span></span></h3>
<h4>精品中文音色</h4><table><tr><th>名称</th><th>voice 参数</th></tr>
<tr><td>龙安温</td><td><code>longanwen_v3.1</code></td><td>女</td><td>优雅</td><td>助手</td><td></td></tr></table>
<h4>精品英文音色</h4><table><tr><td>Emily</td><td><code>Emily_v3.1</code></td><td>女</td><td>英式</td><td></td></tr></table>
<h3>qwen-audio-3.0-tts-plus</h3><table><tr><td>社交陪伴</td><td>名称：龙安灵心voice参数：longanlingxin特质：温暖</td><td></td></tr></table>
<h2>基础音色</h2><table><tr><td>ignore</td><td><code>wrong-model</code></td></tr></table>'''


def test_catalogue_model_boundaries_language_and_inline_legacy_voices():
    result = voices.parse_catalog(DOCUMENT, 'qwen-audio-3.1-tts-flash')
    assert [v['id'] for v in result] == ['longanwen_v3.1', 'Emily_v3.1']
    assert result[0]['name'] == '龙安温' and result[0]['language'] == 'zh'
    assert result[1]['language'] == 'en'
    legacy = voices.parse_catalog(DOCUMENT, 'qwen-audio-3.0-tts-plus')
    assert legacy[0]['id'] == 'longanlingxin' and legacy[0]['name'] == '龙安灵心'
    data = {'docDetailData': {'storeData': {'data': {'content': DOCUMENT}}}}
    embedded = '<script>window.__ICE_PAGE_PROPS__=' + json.dumps(data) + ';</script>'
    assert voices.parse_catalog(embedded, 'qwen-audio-3.1-tts-flash') == result
    with pytest.raises(ValueError):
        voices.parse_catalog('<h3>unknown</h3>', 'qwen-audio-3.1-tts-flash')


def transport(monkeypatch, response):
    client = httpx.AsyncClient
    seen = []
    def handle(request):
        seen.append(request)
        return response(request)
    monkeypatch.setattr(voices.httpx, 'AsyncClient', lambda **kwargs: client(**kwargs, transport=httpx.MockTransport(handle)))
    return seen


def test_endpoint_uses_draft_model_without_exporting_keys_or_saving_configuration(module, monkeypatch):
    seen = transport(monkeypatch, lambda req: httpx.Response(200, text=DOCUMENT))
    client = TestClient(module.app)
    before = client.get('/api/settings/speech').json()
    config = {'name': 'Draft', 'kind': 'tts', 'model': 'qwen-audio-3.1-tts-flash', 'apiKey': 'fixture-secret'}
    response = client.post('/api/settings/speech/unsaved/voices', json=config)
    assert response.status_code == 200 and len(response.json()['voices']) == 2
    assert response.json()['source'] == voices.CATALOG_URL
    assert 'fixture-secret' not in response.text
    assert len(seen) == 1 and str(seen[0].url) == voices.CATALOG_URL
    assert 'authorization' not in seen[0].headers and not seen[0].content
    assert client.get('/api/settings/speech').json() == before
    config['model'] = 'qwen-audio-3.0-tts-plus'
    assert client.post('/api/settings/speech/unsaved/voices', json=config).json()['voices'][0]['id'] == 'longanlingxin'


@pytest.mark.parametrize('body,status', [
    ('provider-secret upstream failure', 403), ('<html>changed layout</html>', 200), ('x' * 2_000_001, 200),
], ids=['upstream-denied', 'changed-layout', 'oversized'])
def test_catalogue_failure_is_safe_and_not_reported_as_empty_success(monkeypatch, body, status):
    transport(monkeypatch, lambda req: httpx.Response(status, text=body))
    with pytest.raises(HTTPException) as result:
        asyncio.run(voices.list_voices(SpeechProfile(name='Draft', kind='tts', model='qwen-audio-3.1-tts-flash')))
    assert result.value.status_code == 502 and 'provider-secret' not in result.value.detail


def test_unsupported_model_and_asr_are_rejected_before_network(monkeypatch):
    seen = transport(monkeypatch, lambda req: pytest.fail('Unexpected network request'))
    for kind, model in [('asr', 'qwen3-asr-flash-realtime'), ('tts', 'unknown-tts')]:
        with pytest.raises(HTTPException) as result:
            asyncio.run(voices.list_voices(SpeechProfile(name='Draft', kind=kind, model=model)))
        assert result.value.status_code == 400
    assert not seen
