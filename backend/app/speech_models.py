"""Authenticated ASR/TTS model discovery; no hard-coded model catalogue.

DashScope catalogue and capability filters:
https://help.aliyun.com/zh/model-studio/list-models
"""
import asyncio
import re
from urllib.parse import urlsplit

import httpx
from fastapi import HTTPException
from .model_profiles import safe_http_error
from .speech_settings import normalize_url,read_speech


CAPABILITIES={'asr':('ASR','Realtime-ASR'),'tts':('TTS','Realtime-Text-to-Speech')}


def matches_kind(record,kind):
    name=record if isinstance(record,str) else record.get('model',record.get('id',record.get('name','')))
    if not isinstance(name,str) or not name.strip():return False
    capabilities=record.get('capabilities') if isinstance(record,dict) else None
    if isinstance(capabilities,list) and capabilities:
        values={value.lower() for value in capabilities if isinstance(value,str)}
        if values & {'realtime-omni','multimodal-omni','realtime-chatting'}:return False
        return bool(values & {value.lower() for value in CAPABILITIES[kind]})
    # Compatibility catalogues may only return IDs. Unknown/audio chat IDs
    # are excluded rather than guessed from a generic "audio" substring.
    value=name.strip().lower()
    if re.search(r'(?:^|[-_])(?:omni|audiochat|embedding)(?:[-_]|$)',value):return False
    return bool(re.search(r'(?:^|[-_])'+kind+r'(?:[-_]|$)',value)
                or re.match(r'^(?:paraformer|whisper)(?:[-_]|$)' if kind=='asr'
                            else r'^(?:cosyvoice|sambert)(?:[-_]|$)',value))


def model_endpoint(base_url):
    url=urlsplit(normalize_url(base_url))
    path='/api/v1/models' if '/api-ws/' in url.path or url.hostname.endswith('.aliyuncs.com') else '/v1/models'
    return 'https://'+url.netloc+path


async def fetch_models(profile_id,config):
    previous=next((p for p in read_speech()['profiles'] if p['id']==profile_id),None)
    key='' if config.clearApiKey else (config.apiKey or '').strip() or (previous or {}).get('apiKey','')
    if not key:raise HTTPException(400,'请先填写 API Key，再获取模型列表')
    if not config.baseUrl.strip():raise HTTPException(400,'请先填写语音接口地址，再获取模型列表')
    endpoint=model_endpoint(config.baseUrl)
    headers={'Authorization':'Bearer '+key}
    models=[];seen_pages=set();cursor=None
    try:
        async with asyncio.timeout(20),httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False,trust_env=False) as client:
            for page in range(1,101):
                params=[('capabilities',value) for value in CAPABILITIES[config.kind]]+[('page_no',str(page)),('page_size','100')]
                if cursor:params.append(('after',cursor))
                response=await client.get(endpoint,headers=headers,params=params)
                if response.status_code in (404,405):raise HTTPException(400,'该语音接口未提供模型列表，请手动输入模型名称')
                if not response.is_success:raise HTTPException(400,safe_http_error(response.status_code))
                payload=response.json()
                if not isinstance(payload,dict):raise ValueError()
                if payload.get('success') is False:raise HTTPException(400,'语音服务查询模型失败，请核对接口地址与 API Key')
                output=payload.get('output',payload)
                if not isinstance(output,dict):raise ValueError()
                records=output.get('models',output.get('data'))
                if not isinstance(records,list):raise ValueError()
                names=[]
                for record in records:
                    if not isinstance(record,(str,dict)):continue
                    name=record if isinstance(record,str) else record.get('model',record.get('id',record.get('name')))
                    if isinstance(name,str) and name.strip():names.append(name.strip())
                    if matches_kind(record,config.kind):models.append(name.strip())
                total=output.get('total')
                more=payload.get('has_more') or output.get('has_more') or isinstance(total,int) and page*int(output.get('page_size',100))<total
                if not more:break
                signature=tuple(names)
                if not names or signature in seen_pages or page==100:raise HTTPException(400,'模型列表分页异常，请手动输入模型名称')
                seen_pages.add(signature)
                if payload.get('has_more') or output.get('has_more'):
                    next_cursor=output.get('last_id',payload.get('last_id')) or names[-1]
                    if next_cursor==cursor:raise HTTPException(400,'模型列表分页异常，请手动输入模型名称')
                    cursor=next_cursor
        return {'kind':config.kind,'models':sorted(set(models)),'source':endpoint}
    except (TimeoutError,httpx.TimeoutException):raise HTTPException(408,'获取语音模型列表超时，请检查网络后重试')
    except httpx.RequestError:raise HTTPException(400,'无法连接语音模型列表接口，请检查地址与网络')
    except (ValueError,AttributeError,TypeError,KeyError):raise HTTPException(400,'服务未返回有效的语音模型列表，请手动输入模型名称')
