import asyncio
import base64
import json
import pytest
from fastapi import HTTPException, WebSocketDisconnect
from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module
from backend.tests.test_speech import config
from backend.app import speech_recognition as recognition

class Socket:
    def __init__(self,fail=False):self.commands=[];self.queue=asyncio.Queue();self.closed=False;self.fail=fail
    async def __aenter__(self):await self.queue.put(json.dumps({'type':'session.created'}));return self
    async def __aexit__(self,*_):self.closed=True
    async def send(self,raw):
        data=json.loads(raw);self.commands.append(data)
        if data['type']=='session.update':await self.queue.put(json.dumps({'type':'session.updated'}))
        elif data['type']=='input_audio_buffer.append':
            if self.fail:await self.queue.put(json.dumps({'type':'error','error':{'code':'InvalidParameter','message':'fixture-key'}}))
            else:
                for event in [{'type':'input_audio_buffer.speech_started','item_id':'first'},{'type':'conversation.item.input_audio_transcription.text','item_id':'first','text':'你好','stash':'世界'},{'type':'conversation.item.input_audio_transcription.completed','item_id':'first','transcript':'你好世界。'}]:await self.queue.put(json.dumps(event))
        elif data['type']=='session.finish':await self.queue.put(json.dumps({'type':'session.finished'}))
    async def recv(self):return await self.queue.get()

def activate(client):
    result=client.put('/api/settings/speech/asr',json=config(kind='asr',model='qwen3-asr-flash-realtime',sampleRate=16000))
    assert result.status_code==200
    assert client.put('/api/settings/speech/active',json={'kind':'asr','activeId':'asr'}).status_code==200

def test_transcript_replacement_and_multiple_sentences():
    transcript=recognition.Transcript()
    def add(id,text,final=False,stash=''):return transcript.update({'type':'conversation.item.input_audio_transcription.'+('completed' if final else 'text'),'item_id':id,'text':text,'stash':stash,'transcript':text})
    assert add('first','你',stash='好')==('你好','')
    assert add('first','你好。',True)==('你好。','你好。')
    assert add('first','旧草稿')==('你好。','你好。')
    assert add('second','世界',stash='！')==('你好。世界！','你好。')
    assert add('second','世界！',True)==('你好。世界！','你好。世界！')
    with pytest.raises(HTTPException):add('third','字'*3001)

def test_relay_pcm_configuration_and_final_result(module,monkeypatch):
    socket=Socket();monkeypatch.setattr(recognition,'connection',lambda _:socket)
    client=TestClient(module.app);activate(client)
    with client.websocket_connect('/api/speech/recognize') as ws:
        assert ws.receive_json()=={'type':'ready','sampleRate':16000}
        ws.send_bytes(b'\x00\x10\x00\xf0'*1280)
        assert ws.receive_json()=={'type':'speech-started'}
        assert ws.receive_json()['text']=='你好世界'
        assert ws.receive_json()['confirmed']=='你好世界。'
        ws.send_json({'type':'finish'})
        assert ws.receive_json()=={'type':'done','text':'你好世界。'}
    assert socket.closed
    assert [c['type'] for c in socket.commands]==['session.update','input_audio_buffer.append','session.finish']
    settings=socket.commands[0]['session']
    assert settings['sample_rate']==16000 and settings['input_audio_format']=='pcm'
    assert settings['input_audio_transcription']=={'language':'zh'}
    assert settings['turn_detection']['type']=='server_vad'
    assert base64.b64decode(socket.commands[1]['audio'])==b'\x00\x10\x00\xf0'*1280

def test_configuration_and_origin_rejection(module):
    client=TestClient(module.app)
    with client.websocket_connect('/api/speech/recognize') as ws:
        assert '启用语音识别' in ws.receive_json()['message']
    with pytest.raises(WebSocketDisconnect) as error:
        with client.websocket_connect('/api/speech/recognize',headers={'origin':'https://unrelated.example'}):pass
    assert error.value.code==1008
    assert client.put('/api/settings/speech/asr',json=config(kind='asr',sampleRate=22050)).status_code==400

def test_upstream_errors_hide_credentials_and_close(module,monkeypatch):
    socket=Socket(fail=True);monkeypatch.setattr(recognition,'connection',lambda _:socket)
    client=TestClient(module.app);activate(client)
    with client.websocket_connect('/api/speech/recognize') as ws:
        ws.receive_json();ws.send_bytes(b'\0\0'*320);result=ws.receive_json()
        assert result['type']=='error' and 'fixture-key' not in json.dumps(result)
    assert socket.closed

def test_cancel_and_invalid_pcm_close_connection(module,monkeypatch):
    client=TestClient(module.app);activate(client)
    for control in ('cancel','invalid'):
        socket=Socket();monkeypatch.setattr(recognition,'connection',lambda _:socket)
        with client.websocket_connect('/api/speech/recognize') as ws:
            ws.receive_json()
            if control=='cancel':ws.send_json({'type':'cancel'})
            else:ws.send_bytes(b'odd');assert ws.receive_json()['type']=='error'
        assert socket.closed

@pytest.mark.parametrize('pcm',[b'\0\0'*3200,b'\x10\0'*3200,b'\0\x10'*320,b'\0\x10'*3200],ids=['silence','quiet-noise','short-click','dc-offset'])
def test_silence_noise_and_short_click_do_not_publish_cloud_hallucinations(module,monkeypatch,pcm):
    socket=Socket();monkeypatch.setattr(recognition,'connection',lambda _:socket)
    client=TestClient(module.app);activate(client)
    with client.websocket_connect('/api/speech/recognize?continuous=true') as ws:
        assert ws.receive_json()['type']=='ready'
        ws.send_bytes(pcm);ws.send_json({'type':'finish'})
        # Mock provider invents a transcript; the microphone evidence must veto it.
        assert ws.receive_json()=={'type':'done','text':''}
    assert socket.closed

def test_speech_evidence_requires_sustained_signal_not_a_particular_word():
    evidence=recognition.SpeechEvidence(16000)
    evidence.append(b'\0\0'*16000);assert not evidence.voiced()
    evidence.append(b'\x00\x10\x00\xf0'*160);assert not evidence.voiced()
    evidence.append(b'\x00\x10\x00\xf0'*960);assert evidence.voiced()
    evidence.frames.clear();assert not evidence.voiced()


@pytest.mark.parametrize('continuous',[True,False])
def test_filler_is_suppressed_in_calls_but_preserved_in_dictation(module,monkeypatch,continuous):
    class FillerSocket(Socket):
        async def send(self,raw):
            data=json.loads(raw)
            if data['type']!='input_audio_buffer.append':return await super().send(raw)
            self.commands.append(data)
            for item in [{'type':'input_audio_buffer.speech_started','item_id':'noise'},
                         {'type':'conversation.item.input_audio_transcription.text','item_id':'noise','text':'嗯','stash':'。'},
                         {'type':'conversation.item.input_audio_transcription.completed','item_id':'noise','transcript':'嗯。'}]:
                await self.queue.put(json.dumps(item))
    socket=FillerSocket();monkeypatch.setattr(recognition,'connection',lambda _:socket)
    client=TestClient(module.app);activate(client)
    with client.websocket_connect('/api/speech/recognize'+('?continuous=true' if continuous else '')) as ws:
        assert ws.receive_json()['type']=='ready'
        ws.send_bytes(b'\x00\x10\x00\xf0'*1280);ws.send_json({'type':'finish'})
        events=[]
        while True:
            item=ws.receive_json();events.append(item)
            if item['type']=='done':break
        if continuous:
            assert events==[{'type':'speech-started'},{'type':'done','text':''}]
        else:
            assert events[-1]=={'type':'done','text':'嗯。'}
    assert socket.closed


def test_filler_guard_preserves_short_commands_and_hesitations_with_content():
    from backend.app.speech_guard import is_filler_transcript
    for text in ('嗯。','嗯，嗯','呃……','hmm.','um','...'):assert is_filler_transcript(text)
    for text in ('撤销','好','不','嗯，请撤销','解释截图'):assert not is_filler_transcript(text)
