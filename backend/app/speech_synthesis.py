"""Qwen-Audio-TTS duplex protocol. API keys never enter the browser."""
import asyncio
import json
from uuid import uuid4
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from fastapi import HTTPException
from websockets.asyncio.client import connect
from websockets.exceptions import InvalidStatus, WebSocketException

def connection(profile):
    url=profile['baseUrl']
    if profile.get('kind')=='asr':
        parts=urlsplit(url);query=[(k,v) for k,v in parse_qsl(parts.query) if k!='model']+[('model',profile['model'])]
        url=urlunsplit(parts._replace(query=urlencode(query)))
    return connect(url,additional_headers={'Authorization':'Bearer '+profile['apiKey']},proxy=None,open_timeout=10,close_timeout=2,max_size=4_000_000)

def event_error(header):
    code=str(header.get('error_code',''))
    if 'auth' in code.lower() or 'apikey' in code.lower():return HTTPException(400,'语音服务鉴权失败，请检查 API Key')
    if 'limit' in code.lower() or 'quota' in code.lower():return HTTPException(429,'语音服务额度或频率受限，请稍后重试')
    return HTTPException(502,'语音合成失败，请核对模型名称、音色和接口所属地域')

async def synthesize_stream(profile,text):
    task_id=str(uuid4());size=0;started=False;finished=False
    def command(action,input,**payload):return json.dumps({'header':{'action':action,'task_id':task_id,'streaming':'duplex'},'payload':{'input':input,**payload}},ensure_ascii=False)
    try:
        async with asyncio.timeout(120):
            async with connection(profile) as ws:
                await ws.send(command('run-task',{},task_group='audio',task='tts',function='SpeechSynthesizer',model=profile['model'],parameters={'text_type':'PlainText','voice':profile['voice'],'format':'mp3','sample_rate':profile['sampleRate'],'volume':profile['volume'],'rate':profile['rate'],'pitch':profile['pitch']}))
                try:
                    while True:
                        message=await asyncio.wait_for(ws.recv(),30)
                        if isinstance(message,bytes):
                            if not started:raise HTTPException(502,'语音服务返回了无效的事件顺序')
                            size+=len(message)
                            if size>32_000_000:raise HTTPException(413,'生成音频过大，请分段朗读')
                            if message:yield message
                            continue
                        envelope=json.loads(message)
                        if not isinstance(envelope,dict) or not isinstance(envelope.get('header'),dict):raise ValueError()
                        header=envelope['header']
                        if header.get('task_id')!=task_id:raise HTTPException(502,'语音服务任务标识不匹配')
                        event=header.get('event')
                        if event=='task-failed':raise event_error(header)
                        if event=='task-started':
                            if started:raise HTTPException(502,'语音服务返回了重复的启动事件')
                            started=True
                            for offset in range(0,len(text),20000):await ws.send(command('continue-task',{'text':text[offset:offset+20000]}))
                            await ws.send(command('finish-task',{}))
                        elif event=='task-finished':
                            if not size:raise HTTPException(502,'语音服务未返回音频')
                            finished=True
                            return
                finally:
                    if started and not finished:
                        try:await asyncio.wait_for(ws.send(command('finish-task',{'directive':'cancel'})),1)
                        except Exception:pass
    except HTTPException:raise
    except TimeoutError:raise HTTPException(504,'语音合成超时，请稍后重试')
    except InvalidStatus as e:
        code=e.response.status_code
        raise HTTPException(400 if code in (401,403) else 502,'语音接口连接失败，请检查接口地址、API Key 和服务权限')
    except (WebSocketException,OSError,ValueError,TypeError):raise HTTPException(502,'语音服务连接中断或返回异常，请重试')

async def synthesize(profile,text):
    return b''.join([chunk async for chunk in synthesize_stream(profile,text)])

async def probe(profile):
    from time import perf_counter
    begin=perf_counter()
    try:
        async with connection(profile):pass
        return {'ok':True,'latencyMs':round((perf_counter()-begin)*1000),'authVerified':True}
    except (WebSocketException,OSError,TimeoutError):return {'ok':False,'latencyMs':round((perf_counter()-begin)*1000),'authVerified':False,'error':'语音接口连接失败，请检查地址与 API Key'}
