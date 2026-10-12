"""Independent Qwen ASR/TTS profiles stored alongside LLM/OCR configuration."""
import hashlib
import json
import os
import re
import sqlite3
from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit
from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from .config_file import read_configuration, write_configuration, configuration_document, configuration_path
from .model_profiles import read_registry, unprotect_key

class SpeechProfile(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1,max_length=80)
    kind: Literal['asr','tts'] = 'tts'
    provider: Literal['dashscope'] = 'dashscope'
    baseUrl: str = Field(default='',max_length=2048)
    model: str = Field(default='',max_length=160)
    apiKey: str | None = Field(default=None,max_length=4096)
    clearApiKey: bool = False
    voice: str = Field(default='longanwen_v3.1',max_length=160)
    sampleRate: Literal[8000,16000,22050,24000,44100,48000] = 22050
    rate: float = Field(default=1,ge=.5,le=2)
    volume: int = Field(default=50,ge=0,le=100)
    pitch: float = Field(default=1,ge=.5,le=2)
    language: Literal['zh','en','yue','ja','ko','de','fr','ru','auto'] = 'zh'

class SpeechSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    kind: Literal['asr','tts']
    activeId: str | None = Field(default=None,pattern=r'^[a-zA-Z0-9-]{1,80}$')

def defaults():
    return {'activeTtsId':None,'activeAsrId':None,'profiles':[
        SpeechProfile(name='Qwen TTS',model='qwen-audio-3.1-tts-flash').model_dump(exclude={'clearApiKey'}) | {'id':'qwen-tts','apiKey':''},
        SpeechProfile(name='Qwen ASR',kind='asr',model='qwen3-asr-flash-realtime',sampleRate=16000).model_dump(exclude={'clearApiKey'}) | {'id':'qwen-asr','apiKey':''}]}

def normalize_url(value):
    value=value.strip()
    if not value:return ''
    try:
        url=urlsplit(value);url.port
        if url.scheme!='wss' or not url.hostname or url.username or url.password or url.fragment:raise ValueError()
    except ValueError:raise HTTPException(400,'语音接口地址必须是有效的 wss:// WebSocket 地址')
    return value

def read_speech():
    document=read_configuration()
    data=(document or {}).get('speech')
    if data is None:return defaults()
    try:
        if not isinstance(data,dict) or not isinstance(data.get('profiles'),list) or len(data['profiles'])>30:raise ValueError()
        result={'activeTtsId':data.get('activeTtsId'),'activeAsrId':data.get('activeAsrId'),'profiles':[]};ids=set()
        for item in data['profiles']:
            id=item['id']
            if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',id) or id in ids:raise ValueError()
            ids.add(id);config=SpeechProfile(**{k:v for k,v in item.items() if k!='id'})
            result['profiles'].append(config.model_dump(exclude={'clearApiKey'})|{'id':id,'apiKey':config.apiKey or ''})
        for kind in ('asr','tts'):
            active=result['active'+kind.title()+'Id']
            if active is not None and not any(p['id']==active and p['kind']==kind for p in result['profiles']):raise ValueError()
        return result
    except (ValueError,TypeError,KeyError):raise HTTPException(400,'ASR&TTS 配置格式无效，请检查语音模型字段')

def public_speech(data):
    return {**data,'profiles':[{k:v for k,v in p.items() if k!='apiKey'}|{'hasApiKey':bool(p.get('apiKey'))} for p in data['profiles']]}

def get_speech():return public_speech(read_speech())

def write_speech(db,data):
    document=configuration_document(read_registry(db),unprotect_key)
    document['speech']=data
    write_configuration(document)

def resolved(config,previous=None):
    result=config.model_dump(exclude={'clearApiKey'})
    result['name']=config.name.strip();result['model']=config.model.strip();result['voice']=config.voice.strip()
    result['baseUrl']=normalize_url(config.baseUrl)
    result['apiKey']='' if config.clearApiKey else (config.apiKey or '').strip() or (previous or {}).get('apiKey','')
    if not result['name'] or not result['model']:raise HTTPException(400,'请填写配置名称和模型名称')
    if config.kind=='tts' and not result['voice']:raise HTTPException(400,'请填写 TTS 音色名称')
    if config.kind=='asr' and config.sampleRate not in (8000,16000):raise HTTPException(400,'ASR 采样率请选择 8000 或 16000 Hz')
    return result

def ready(profile):
    if not profile.get('apiKey') or not profile.get('baseUrl'):raise HTTPException(400,'请先填写语音接口地址与 API Key')
    normalize_url(profile['baseUrl'])

def save_speech(path,id,config):
    if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',id):raise HTTPException(400,'语音配置 ID 无效')
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');data=read_speech();old=next((p for p in data['profiles'] if p['id']==id),None)
        if not old and len(data['profiles'])>=30:raise HTTPException(400,'最多保存 30 个语音配置')
        profile=resolved(config,old)|{'id':id}
        for kind in ('asr','tts'):
            field='active'+kind.title()+'Id'
            if data[field]==id and (profile['kind']!=kind or profile!=old):data[field]=None
        data['profiles']=[profile if p['id']==id else p for p in data['profiles']]
        if not old:data['profiles'].append(profile)
        write_speech(db,data)
    return public_speech(data)

def select_speech(path,selection):
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');data=read_speech()
        if selection.activeId:
            profile=next((p for p in data['profiles'] if p['id']==selection.activeId and p['kind']==selection.kind),None)
            if not profile:raise HTTPException(400,'请选择已保存的对应语音模型')
            ready(profile)
        data['active'+selection.kind.title()+'Id']=selection.activeId;write_speech(db,data)
    return public_speech(data)

def active_tts():
    data=read_speech();profile=next((p for p in data['profiles'] if p['id']==data['activeTtsId'] and p['kind']=='tts'),None)
    if not profile:raise HTTPException(400,'请先在 ASR&TTS 配置中启用语音合成模型')
    ready(profile);return profile

def draft_speech(id,config):
    previous=next((p for p in read_speech()['profiles'] if p['id']==id),None)
    profile=resolved(config,previous);ready(profile);return profile

def active_asr():
    data=read_speech();profile=next((p for p in data['profiles'] if p['id']==data['activeAsrId'] and p['kind']=='asr'),None)
    if not profile:raise HTTPException(400,'请先在 ASR&TTS 配置中启用语音识别模型')
    ready(profile)
    if profile['sampleRate'] not in (8000,16000):raise HTTPException(400,'ASR 采样率请选择 8000 或 16000 Hz')
    return profile

def import_speech_environment(path,env_path=None):
    # Isolated tests and alternate data roots must never import real credentials.
    if env_path is None:
        if any(os.environ.get(k) for k in ('SNAPMIND_CONFIG_FILE','SNAPMIND_DATA_DIR','SNAPMIND_HOME')):return
        env_path=Path(__file__).resolve().parents[1]/'.env'
    env_path=Path(env_path)
    if not env_path.exists():return
    values={}
    for line in env_path.read_text(encoding='utf-8-sig').splitlines():
        match=re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$',line)
        if not match:continue
        value=match[2]
        values[match[1]]=value[1:-1] if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'") else re.split(r'\s+#',value,maxsplit=1)[0].strip()
    entries=[]
    for kind in ('asr','tts'):
        prefix='MINDPILOT_'+kind.upper()+'_'
        key=values.get(prefix+'API_KEY')
        if not key:continue
        entries.append((kind,SpeechProfile(name='Qwen '+kind.upper(),kind=kind,provider=values.get(prefix+'PROVIDER','dashscope'),baseUrl=values.get(prefix+'BASE_URL',''),model=values.get(prefix+'MODEL','qwen-audio-3.1-tts-flash' if kind=='tts' else 'qwen3-asr-flash-realtime'),voice=values.get(prefix+'VOICE','longanwen_v3.1'),apiKey=key,sampleRate=16000 if kind=='asr' else 22050)))
    if not entries:return
    # Keep the existing import fingerprint stable when new UI fields get defaults.
    digest=hashlib.sha256(json.dumps([(k,c.model_dump(exclude={'language'})) for k,c in entries],sort_keys=True).encode()).hexdigest()
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE');row=db.execute("SELECT body FROM app_settings WHERE name='speech_env_import'").fetchone()
        if row and row[0]==digest:return
        data=read_speech()
        for kind,config in entries:
            id='qwen-'+kind;profile=resolved(config)|{'id':id};ready(profile)
            data['profiles']=[p for p in data['profiles'] if p['id']!=id]+[profile]
            data['active'+kind.title()+'Id']=id
        write_speech(db,data)
        db.execute("INSERT INTO app_settings(name,body) VALUES('speech_env_import',?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",(digest,))
