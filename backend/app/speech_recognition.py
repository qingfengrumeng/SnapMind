"""Local microphone PCM relay to Qwen-ASR-Realtime; no credentials in clients."""
import asyncio
import base64
import json
import math
import struct
from collections import deque
from uuid import uuid4
from fastapi import HTTPException, WebSocketDisconnect
from websockets.exceptions import WebSocketException, InvalidStatus
from .speech_synthesis import connection
from .speech_guard import is_filler_transcript

class Transcript:
    def __init__(self):self.items={}
    def update(self,event):
        id=event.get('item_id')
        if not isinstance(id,str):raise HTTPException(502,'语音识别结果缺少消息标识')
        old=self.items.get(id,{'text':'','final':False})
        final=event['type'].endswith('.completed')
        if old['final'] and not final:return self.text(),self.text(True)
        text=event.get('transcript','') if final else event.get('text','')+event.get('stash','')
        if not isinstance(text,str):raise HTTPException(502,'语音识别返回了无效文字')
        self.items[id]={'text':text,'final':final}
        if len(self.text())>3000:raise HTTPException(413,'识别文字超过 3000 字，请分段说话')
        return self.text(),self.text(True)
    def text(self,final=False):return ''.join(item['text'] for item in self.items.values() if not final or item['final'])

class SpeechEvidence:
    """Require microphone signal as well as cloud VAD; silence is not speech."""
    def __init__(self,rate):self.rate=rate;self.position=0;self.frames=deque()
    def append(self,pcm):
        samples=struct.unpack('<'+'h'*(len(pcm)//2),pcm)
        step=self.rate//50
        for offset in range(0,len(samples),step):
            frame=samples[offset:offset+step]
            # A microphone DC offset is not audible speech energy.
            mean=sum(frame)/len(frame)
            rms=math.sqrt(sum((sample-mean)**2 for sample in frame)/len(frame))/32768
            self.position+=len(frame)
            self.frames.append((self.position,len(frame),rms>=.004))
        while self.frames and self.frames[0][0]<self.position-self.rate*2:self.frames.popleft()
    def voiced(self):return sum(size for _,size,voice in self.frames if voice)>=self.rate*.12

def command(type,**data):return json.dumps({'event_id':'event_'+uuid4().hex,'type':type,**data},ensure_ascii=False)

async def event(ws,timeout=30):
    raw=await asyncio.wait_for(ws.recv(),timeout)
    if not isinstance(raw,str):raise HTTPException(502,'语音识别服务返回了无效数据')
    data=json.loads(raw)
    if not isinstance(data,dict):raise ValueError()
    if data.get('type') in ('error','conversation.item.input_audio_transcription.failed'):
        code=str(data.get('error',{}).get('code','')).lower()
        if 'limit' in code or 'quota' in code:raise HTTPException(429,'语音识别服务额度或频率受限，请稍后重试')
        raise HTTPException(502,'语音识别失败，请核对模型、接口地域和 API Key')
    return data

async def relay(client,profile,continuous=False):
    transcript=Transcript();tasks=[];audio_bytes=0;completed=set();speech_items=set();accepted=set();evidence=SpeechEvidence(profile['sampleRate'])
    try:
        async with asyncio.timeout(1835 if continuous else 155):
            async with connection(profile) as ws:
                first=await event(ws)
                if first.get('type')!='session.created':raise HTTPException(502,'语音识别会话启动异常')
                language=profile.get('language','zh')
                await ws.send(command('session.update',session={'input_audio_format':'pcm','sample_rate':profile['sampleRate'],'input_audio_transcription':{} if language=='auto' else {'language':language},'turn_detection':{'type':'server_vad','threshold':0.2,'silence_duration_ms':400}}))
                if (await event(ws)).get('type')!='session.updated':raise HTTPException(502,'语音识别会话配置失败')
                await client.send_json({'type':'ready','sampleRate':profile['sampleRate']})
                async def upload():
                    nonlocal audio_bytes
                    while True:
                        message=await asyncio.wait_for(client.receive(),125)
                        if message['type']=='websocket.disconnect':return
                        data=message.get('bytes')
                        if data is not None:
                            if not data or len(data)%2 or len(data)>64000:raise HTTPException(400,'录音数据格式无效')
                            audio_bytes+=len(data)
                            evidence.append(data)
                            if audio_bytes>profile['sampleRate']*2*(1800 if continuous else 120):raise HTTPException(413,'本次语音连接已达到时长上限，请重新连接')
                            await ws.send(command('input_audio_buffer.append',audio=base64.b64encode(data).decode()))
                        else:
                            control=json.loads(message.get('text',''))
                            if control.get('type')=='finish':
                                await ws.send(command('session.finish'))
                                # Keep watching disconnects until upstream finishes.
                                while True:
                                    if (await client.receive())['type']=='websocket.disconnect':return
                            if control.get('type')=='cancel':return
                            raise HTTPException(400,'未知的录音控制指令')
                async def download():
                    nonlocal transcript
                    def finish_item(item):
                        nonlocal transcript
                        completed.add(item);speech_items.discard(item);accepted.discard(item)
                        evidence.frames.clear();transcript=Transcript()
                        if len(completed)>2000:raise HTTPException(413,'通话轮数过多，请重新连接')
                    while True:
                        data=await event(ws,300 if continuous else 30);type=data.get('type','')
                        if type=='input_audio_buffer.speech_started':
                            item=data.get('item_id')
                            if isinstance(item,str):speech_items.add(item)
                            if evidence.voiced():await client.send_json({'type':'speech-started'})
                        elif type in ('conversation.item.input_audio_transcription.text','conversation.item.input_audio_transcription.completed'):
                            item=data.get('item_id')
                            if not isinstance(item,str):raise HTTPException(502,'语音识别结果缺少消息标识')
                            if continuous and item in completed:continue
                            candidate=data.get('transcript','') if type.endswith('.completed') else data.get('text','')+data.get('stash','')
                            if continuous and isinstance(candidate,str) and is_filler_transcript(candidate):
                                if type.endswith('.completed'):finish_item(item)
                                continue
                            if item not in accepted:
                                if item not in speech_items or not evidence.voiced():
                                    if continuous and type.endswith('.completed'):finish_item(item)
                                    continue
                                accepted.add(item)
                            text,confirmed=transcript.update(data)
                            await client.send_json({'type':'transcript','text':text,'confirmed':confirmed})
                            if continuous and type.endswith('.completed'):
                                finish_item(item)
                                await client.send_json({'type':'utterance','text':confirmed,'itemId':data['item_id']})
                        elif type=='session.finished':
                            await client.send_json({'type':'done','text':transcript.text(True)});return
                tasks=[asyncio.create_task(upload()),asyncio.create_task(download())]
                done,_=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                for task in done:await task
    except HTTPException as e:
        await client.send_json({'type':'error','message':e.detail,'confirmed':transcript.text(True)})
    except TimeoutError:
        await client.send_json({'type':'error','message':'语音识别超时，请重新录音','confirmed':transcript.text(True)})
    except (WebSocketException,OSError,ValueError,TypeError,KeyError):
        await client.send_json({'type':'error','message':'语音识别连接中断，请检查网络后重试','confirmed':transcript.text(True)})
    finally:
        for task in tasks:
            if not task.done():task.cancel()
        if tasks:await asyncio.gather(*tasks,return_exceptions=True)
