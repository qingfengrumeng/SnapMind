import asyncio
import json
import base64
import io
from types import SimpleNamespace

import httpx
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from PIL import Image

from backend.app import speech_synthesis as synthesis, model_inference as inference, speech_recognition as recognition
from backend.tests.test_capture_processing import module
from backend.tests.test_speech import Socket, profile, config
from backend.tests.test_asr import activate


def test_audio_chunk_arrives_before_task_finished_and_close_cancels_provider(monkeypatch):
    socket=Socket()
    monkeypatch.setattr(synthesis,'connection',lambda _:socket)
    async def run():
        stream=synthesis.synthesize_stream(profile(),'hello')
        assert await anext(stream)==b'ID3fixture-audio'
        assert not socket.closed and not socket.queue.empty()
        await stream.aclose()
    asyncio.run(run())
    assert socket.closed and socket.commands[-1]['payload']['input']=={'directive':'cancel'}


def test_streaming_endpoint_and_safe_pre_header_provider_errors(module,monkeypatch):
    client=TestClient(module.app)
    client.put('/api/settings/speech/one',json=config())
    client.put('/api/settings/speech/active',json={'kind':'tts','activeId':'one'})
    async def source(profile,text):
        yield b'first'
        yield b'second'
    monkeypatch.setattr(module,'synthesize_stream',source)
    response=client.post('/api/speech/synthesize?stream=true',json={'text':'hello'})
    assert response.content==b'firstsecond' and response.headers['x-snapmind-audio']=='stream'
    assert response.headers['x-accel-buffering']=='no' and 'content-length' not in response.headers
    async def failure(profile,text):
        raise HTTPException(502,'语音服务鉴权失败')
        yield b''
    monkeypatch.setattr(module,'synthesize_stream',failure)
    response=client.post('/api/speech/synthesize?stream=true',json={'text':'hello'})
    assert response.status_code==502 and '鉴权失败' in response.json()['detail']


class ModelStream(httpx.AsyncByteStream):
    def __init__(self,ollama=False,broken=False):self.ollama=ollama;self.broken=broken;self.seen=[];self.closed=False
    async def __aiter__(self):
        for index,text in enumerate(['第一句。','第二句。']):
            # The consumer must publish the previous delta before reading another.
            assert len(self.seen)==index
            item={'message':{'content':text},'done':False} if self.ollama else {'choices':[{'delta':{'content':text},'finish_reason':None}]}
            yield ((json.dumps(item) if self.ollama else 'data: '+json.dumps(item))+'\n\n').encode()
        if self.broken:return
        final={'done':True,'message':{'content':''},'prompt_eval_count':10,'eval_count':4} if self.ollama else {'choices':[{'delta':{},'finish_reason':'stop'}],'usage':{'prompt_tokens':10,'completion_tokens':4}}
        yield ((json.dumps(final) if self.ollama else 'data: '+json.dumps(final))+'\n\n').encode()
    async def aclose(self):self.closed=True


@pytest.mark.parametrize('provider',['openai-compatible','ollama'])
def test_model_stream_publishes_real_deltas_and_records_usage(module,monkeypatch,provider):
    stream=ModelStream(provider=='ollama');client=httpx.AsyncClient
    def handle(request):
        body=json.loads(request.content)
        assert body['stream'] is True
        return httpx.Response(200,stream=stream)
    monkeypatch.setattr(inference.httpx,'AsyncClient',lambda **kw:client(**kw,transport=httpx.MockTransport(handle)))
    async def chunk(text):stream.seen.append(text)
    result=asyncio.run(inference.complete({'provider':provider,'model':'fixture','baseUrl':'http://example.test/v1','vision':False},SimpleNamespace(messages=[]),[],'chat','hello',module.DB,on_chunk=chunk))
    assert stream.seen==['第一句。','第二句。'] and result['text']=='第一句。第二句。' and stream.closed
    with module.sqlite3.connect(module.DB) as db:
        assert db.execute('SELECT input_tokens,output_tokens FROM model_usage WHERE model=?',('fixture',)).fetchone()==(10,4)


def test_continuous_asr_delivers_utterances_without_finish_or_reconnect(module,monkeypatch):
    class ContinuousSocket(Socket):
        def __init__(self):super().__init__();self.sentences=0
        async def __aenter__(self):await self.queue.put(json.dumps({'type':'session.created'}));return self
        async def send(self,raw):
            command=json.loads(raw);self.commands.append(command)
            if command['type']=='session.update':await self.queue.put(json.dumps({'type':'session.updated'}))
            elif command['type']=='input_audio_buffer.append':
                self.sentences+=1
                for event in [{'type':'input_audio_buffer.speech_started','item_id':str(self.sentences)},{'type':'conversation.item.input_audio_transcription.text','item_id':str(self.sentences),'text':'实时','stash':'文字'},{'type':'conversation.item.input_audio_transcription.completed','item_id':str(self.sentences),'transcript':'实时文字。'}]:await self.queue.put(json.dumps(event))
    socket=ContinuousSocket();monkeypatch.setattr(recognition,'connection',lambda _:socket)
    client=TestClient(module.app);activate(client)
    with client.websocket_connect('/api/speech/recognize?continuous=true') as ws:
        assert ws.receive_json()['type']=='ready'
        for turn in range(2):
            ws.send_bytes(b'\x00\x10\x00\xf0'*1280)
            assert ws.receive_json()['type']=='speech-started'
            assert ws.receive_json()['text']=='实时文字'
            assert ws.receive_json()['confirmed']=='实时文字。'
            assert ws.receive_json()=={'type':'utterance','text':'实时文字。','itemId':str(turn+1)}
        ws.send_json({'type':'cancel'})
    assert socket.closed
    assert [c['type'] for c in socket.commands]==['session.update','input_audio_buffer.append','input_audio_buffer.append']


def test_image_conversation_streams_text_deltas_and_final_tool_result(module,monkeypatch):
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    calls=[]
    async def complete(*args,on_chunk=None):
        assert on_chunk is not None
        calls.append(args[3])
        await on_chunk('第一行\n')
        await on_chunk('第二行')
        return {'text':'第一行\n第二行','kind':'text'}
    monkeypatch.setattr(module,'complete',complete)
    buffer=io.BytesIO();Image.new('RGB',(20,20),'white').save(buffer,format='PNG')
    asset={'id':'fixture','name':'test','data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),'width':20,'height':20,'scenario':'custom'}
    client=TestClient(module.app)
    response=client.post('/api/capture/conversation?stream=true',json={'assets':[asset],'selectedId':'fixture','prompt':'提取文字','history':[],'existing':[],'action':'ocr'})
    assert response.headers['content-type'].startswith('text/event-stream')
    events=[json.loads(line[6:]) for line in response.text.splitlines() if line.startswith('data: ')]
    assert events[:2]==[{'type':'chunk','text':'第一行\n','action':'ocr'},{'type':'chunk','text':'第二行','action':'ocr'}]
    assert events[-1]['type']=='result' and events[-1]['result']['answer']=='第一行\n第二行' and calls==['ocr']


def test_truncated_llm_stream_is_reported_as_error(module,monkeypatch):
    stream=ModelStream(broken=True);client=httpx.AsyncClient
    monkeypatch.setattr(inference.httpx,'AsyncClient',lambda **kw:client(**kw,transport=httpx.MockTransport(lambda _:httpx.Response(200,stream=stream))))
    async def chunk(text):stream.seen.append(text)
    with pytest.raises(HTTPException) as error:
        asyncio.run(inference.complete({'provider':'openai-compatible','model':'fixture','baseUrl':'http://example.test/v1','vision':False},SimpleNamespace(messages=[]),[],'chat','hello',module.DB,on_chunk=chunk))
    assert error.value.status_code==502 and '中断' in error.value.detail and stream.closed


@pytest.mark.parametrize('provider',['openai-compatible','ollama'])
def test_agent_planning_uses_provider_json_output_without_changing_regular_chat(module,monkeypatch,provider):
    client=httpx.AsyncClient;requests=[]
    def handle(request):
        body=json.loads(request.content);requests.append(body)
        output='{"kind":"final"}'
        result={'message':{'content':output},'prompt_eval_count':1,'eval_count':1} if provider=='ollama' else {'choices':[{'message':{'content':output}}],'usage':{'prompt_tokens':1,'completion_tokens':1}}
        return httpx.Response(200,json=result)
    monkeypatch.setattr(inference.httpx,'AsyncClient',lambda **kw:client(**kw,transport=httpx.MockTransport(handle)))
    profile={'provider':provider,'model':'fixture','baseUrl':'http://example.test/v1','vision':False}
    for value in [True,False]:
        asyncio.run(inference.complete(profile|{'_agentDecision':value},SimpleNamespace(messages=[]),[],'chat','Return JSON',module.DB))
    assert requests[0].get('format')=='json' if provider=='ollama' else requests[0]['response_format']=={'type':'json_object'}
    assert 'format' not in requests[1] and 'response_format' not in requests[1]
