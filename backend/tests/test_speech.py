import asyncio
import json
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module
from backend.app import speech_synthesis as synthesis
from backend.app.speech_settings import import_speech_environment, read_speech

def config(**changes):
    return {'name':'Qwen test','kind':'tts','baseUrl':'wss://example.com/api-ws/v1/inference','model':'qwen-audio-3.1-tts-flash','voice':'longanwen_v3.1','apiKey':'fixture-key',**changes}

def test_profiles_selection_and_configuration_preservation(module):
    client=TestClient(module.app)
    assert client.put('/api/settings/speech/one',json=config()).status_code==200
    assert client.put('/api/settings/speech/two',json=config(name='Second')).status_code==200
    assert client.put('/api/settings/speech/asr',json=config(kind='asr',sampleRate=16000)).status_code==200
    for kind,id in [('asr','asr'),('tts','one'),('tts','two')]:
        assert client.put('/api/settings/speech/active',json={'kind':kind,'activeId':id}).status_code==200
    value=client.get('/api/settings/speech').json()
    assert value['activeAsrId']=='asr' and value['activeTtsId']=='two'
    assert 'fixture-key' not in json.dumps(value) and 'apiKey' not in value['profiles'][0]
    assert client.put('/api/settings/speech/active',json={'kind':'tts','activeId':'asr'}).status_code==400
    document=client.get('/api/settings/config').json()
    assert all(p['apiKey']!='fixture-key' for p in document['speech']['profiles'])
    assert client.get('/api/settings/config?reveal_keys=true').json()['speech']['profiles'][-1]['apiKey']=='fixture-key'
    llm={'name':'Local','vendor':'custom','provider':'openai-compatible','model':'llm','baseUrl':'http://localhost:9999/v1','vision':False}
    assert client.put('/api/settings/models/custom',json=llm).status_code==200
    assert client.put('/api/settings/ocr',json={'baseUrl':'https://example.com/ocr','model':'ocr','enabled':False,'assistLlm':True}).status_code==200
    assert read_speech()['activeTtsId']=='two'
    # Editing an enabled profile requires explicit reactivation; blank keys persist.
    assert client.put('/api/settings/speech/two',json=config(apiKey='',voice='another')).json()['activeTtsId'] is None
    assert next(p for p in read_speech()['profiles'] if p['id']=='two')['apiKey']=='fixture-key'
    assert client.put('/api/settings/speech/two',json=config(clearApiKey=True)).status_code==200
    assert client.put('/api/settings/speech/active',json={'kind':'tts','activeId':'two'}).status_code==400
    assert client.put('/api/settings/speech/invalid',json=config(baseUrl='https://example.com')).status_code==400
    assert client.put('/api/settings/speech/invalid',json=config(rate=3)).status_code==422

def test_environment_import_once_preserves_ui_edits(module,tmp_path):
    env=tmp_path/'speech.env';env.write_text('MINDPILOT_TTS_API_KEY="fixture-key"\nMINDPILOT_TTS_BASE_URL=wss://example.com/inference\nMINDPILOT_TTS_MODEL=qwen-audio-3.1-tts-flash\nMINDPILOT_TTS_VOICE=longanwen_v3.1\n',encoding='utf-8')
    import_speech_environment(module.DB,env)
    assert read_speech()['activeTtsId']=='qwen-tts'
    client=TestClient(module.app)
    assert client.put('/api/settings/speech/qwen-tts',json=config(voice='ui-voice')).status_code==200
    import_speech_environment(module.DB,env)
    assert next(p for p in read_speech()['profiles'] if p['id']=='qwen-tts')['voice']=='ui-voice'
    assert read_speech()['activeTtsId'] is None

class Socket:
    def __init__(self,fail=False,block=False):self.commands=[];self.queue=asyncio.Queue();self.closed=False;self.fail=fail;self.block=block
    async def __aenter__(self):return self
    async def __aexit__(self,*_):self.closed=True
    async def send(self,raw):
        data=json.loads(raw);self.commands.append(data);header=data['header'];action=header['action']
        if action=='run-task':
            event='task-failed' if self.fail else 'task-started'
            await self.queue.put(json.dumps({'header':{'event':event,'task_id':header['task_id'],'error_code':'InvalidParameter','error_message':'fixture-key must never leak'}}))
        elif action=='continue-task' and not self.block:await self.queue.put(b'ID3fixture-audio')
        elif action=='finish-task' and not self.block:await self.queue.put(json.dumps({'header':{'event':'task-finished','task_id':header['task_id']}}))
    async def recv(self):return await self.queue.get()

def profile():return {**config(),'sampleRate':22050,'rate':1,'volume':50,'pitch':1}

def test_websocket_protocol_chunks_audio_and_task_identity(monkeypatch):
    ws=Socket();monkeypatch.setattr(synthesis,'connection',lambda _:ws)
    audio=asyncio.run(synthesis.synthesize(profile(),'中'*20001))
    assert audio==b'ID3fixture-audio'*2 and ws.closed
    assert [c['header']['action'] for c in ws.commands]==['run-task','continue-task','continue-task','finish-task']
    assert len({c['header']['task_id'] for c in ws.commands})==1
    assert [len(c['payload']['input']['text']) for c in ws.commands[1:3]]==[20000,1]
    assert ws.commands[0]['payload']['parameters']['format']=='mp3'
    assert ws.commands[0]['payload']['model']=='qwen-audio-3.1-tts-flash'

def test_service_failure_does_not_leak_key(monkeypatch):
    ws=Socket(fail=True);monkeypatch.setattr(synthesis,'connection',lambda _:ws)
    with pytest.raises(HTTPException) as error:asyncio.run(synthesis.synthesize(profile(),'hello'))
    assert error.value.status_code==502 and 'fixture-key' not in error.value.detail and ws.closed

def test_cancellation_closes_upstream_task(monkeypatch):
    ws=Socket(block=True);monkeypatch.setattr(synthesis,'connection',lambda _:ws)
    async def run():
        task=asyncio.create_task(synthesis.synthesize(profile(),'hello'))
        while len(ws.commands)<3:await asyncio.sleep(.001)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
    asyncio.run(run())
    assert ws.closed and ws.commands[-1]['payload']['input']=={'directive':'cancel'}

def test_audio_endpoint_requires_enabled_tts_and_returns_binary(module,monkeypatch):
    client=TestClient(module.app)
    assert client.post('/api/speech/synthesize',json={'text':'hello'}).status_code==400
    client.put('/api/settings/speech/one',json=config())
    client.put('/api/settings/speech/active',json={'kind':'tts','activeId':'one'})
    async def synth(profile,text):assert text=='hello';return b'ID3fixture-audio'
    monkeypatch.setattr(module,'synthesize',synth)
    response=client.post('/api/speech/synthesize',json={'text':'hello'})
    assert response.status_code==200 and response.content==b'ID3fixture-audio'
    assert response.headers['content-type']=='audio/mpeg' and response.headers['cache-control']=='no-store'
    assert client.post('/api/speech/synthesize',json={'text':'   '}).status_code==400
