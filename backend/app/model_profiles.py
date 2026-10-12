"""Multiple encrypted model profiles with one atomic active selection."""
import json
import sqlite3
import time
import ctypes
import httpx
import webbrowser
from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal
from .model_settings import Blob, protect_key
from .config_file import configuration_path, configuration_document, read_configuration, write_configuration
from urllib.parse import urlsplit

PRESETS = [
    {'id':'deepseek','name':'DeepSeek','vendor':'deepseek','provider':'openai-compatible','baseUrl':'https://api.deepseek.com','model':''},
    {'id':'kimi','name':'Kimi','vendor':'kimi','provider':'openai-compatible','baseUrl':'https://api.moonshot.cn/v1','model':''},
    {'id':'qwen','name':'Qwen','vendor':'qwen','provider':'openai-compatible','baseUrl':'https://dashscope.aliyuncs.com/compatible-mode/v1','model':''},
    {'id':'doubao','name':'豆包','vendor':'doubao','provider':'openai-compatible','baseUrl':'https://ark.cn-beijing.volces.com/api/v3','model':''},
    {'id':'glm','name':'GLM','vendor':'glm','provider':'openai-compatible','baseUrl':'https://open.bigmodel.cn/api/paas/v4','model':''},
    {'id':'custom','name':'自定义接口','vendor':'custom','provider':'openai-compatible','baseUrl':'','model':''},
]
KEY_PORTALS={
    'deepseek':'https://platform.deepseek.com/api_keys',
    'kimi':'https://platform.kimi.com/console/api-keys',
    'qwen':'https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key',
    'doubao':'https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey',
    'glm':'https://bigmodel.cn/usercenter/proj-mgmt/apikeys',
    'paddleocr':'https://aistudio.baidu.com/paddleocr',
}
KEY_REQUIRED={'deepseek','kimi','qwen','doubao','glm'}

class ProfileConfig(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    vendor: Literal['deepseek','kimi','qwen','doubao','glm','custom'] = 'custom'
    provider: Literal['openai-compatible','ollama'] = 'openai-compatible'
    baseUrl: str = Field(max_length=2048)
    model: str = Field(default='', max_length=160)
    apiKey: str | None = Field(default=None, max_length=4096)
    clearApiKey: bool = False
    vision: bool = False

class ActiveSelection(BaseModel):
    activeId: str | None = Field(default=None, pattern=r'^[a-zA-Z0-9-]{1,80}$')

def normalize_url(value):
    url=value.strip().rstrip('/')
    try:
        parsed=urlsplit(url)
        valid=parsed.scheme in ('http','https') and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        parsed.port
    except ValueError:
        valid=False
    if not valid:
        raise HTTPException(400,'请输入有效的 HTTP 或 HTTPS 接口地址')
    return url

def read_registry(db):
    db.execute('CREATE TABLE IF NOT EXISTS app_settings (name TEXT PRIMARY KEY, body TEXT NOT NULL)')
    row=db.execute("SELECT body FROM app_settings WHERE name='model_profiles'").fetchone()
    if row:
        registry=json.loads(row[0])
        registry=registry_from_file(registry)
        retired=[p for p in registry['profiles'] if p.get('vendor')=='ollama']
        if retired:
            registry.setdefault('retiredProfiles',[]).extend(retired)
            registry['profiles']=[p for p in registry['profiles'] if p.get('vendor')!='ollama']
            if registry['activeId'] in {p['id'] for p in retired}:registry['activeId']=None
        existing={p['id'] for p in registry['profiles']}
        registry['profiles'].extend({**p,'vision':False,'saved':False} for p in PRESETS if p['id'] not in existing)
        order={p['id']:i for i,p in enumerate(PRESETS)}
        registry['profiles'].sort(key=lambda p:order.get(p['id'],len(order)))
        return registry
    registry={'activeId':None,'profiles':[{**p,'vision':False,'saved':False} for p in PRESETS]}
    legacy=db.execute("SELECT body FROM app_settings WHERE name='model'").fetchone()
    if legacy:
        config=json.loads(legacy[0])
        if config.get('baseUrl') and config.get('model'):
            registry['profiles'].append({**config,'id':'legacy','name':'已有配置','vendor':'custom','vision':False,'saved':True})
    return registry_from_file(registry)

def registry_from_file(cached):
    document=read_configuration()
    if document is None:return cached
    profiles=[]
    try:
        for item in document['models']:
            config=ProfileConfig(name=item['name'],vendor=item['provider'],provider=item.get('apiFormat','openai-compatible'),baseUrl=item['baseUrl'],model=item.get('model',''),apiKey=item.get('apiKey',''),vision=item.get('vision',False))
            previous=next((p for p in cached['profiles'] if p['id']==item['id']),{})
            key=(config.apiKey or '').strip()
            encrypted=previous.get('apiKeyProtected','')
            if key:
                try:unchanged=encrypted and unprotect_key(encrypted)==key
                except HTTPException:unchanged=False
                encrypted=encrypted if unchanged else protect_key(key)
            else:encrypted=''
            p={'id':item['id'],'name':config.name,'vendor':config.vendor,'provider':config.provider,'baseUrl':config.baseUrl,'model':config.model,'vision':config.vision,'apiKeyProtected':encrypted}
            p['saved']=profile_ready(p)
            if item.get('enabled') and not p['saved']:raise HTTPException(400,'配置文件中启用的模型尚未填写完整')
            profiles.append(p)
    except (ValueError,KeyError,TypeError):
        raise HTTPException(400,'.snapmind/models.json 中的模型配置字段无效')
    existing={p['id'] for p in profiles}
    profiles.extend({**p,'vision':False,'saved':False} for p in PRESETS if p['id'] not in existing)
    result={'activeId':document['activeModelId'],'profiles':profiles}
    retired=cached.get('retiredProfiles',[])+[p for p in cached['profiles'] if p.get('vendor')=='ollama']
    if retired:result['retiredProfiles']=retired
    return result

def profile_ready(profile):
    try:normalize_url(profile['baseUrl'])
    except HTTPException:return False
    return bool(profile['name'].strip() and profile['model'].strip() and (profile['vendor'] not in KEY_REQUIRED or profile.get('apiKeyProtected')))

def write_registry(db, registry):
    db.execute("INSERT INTO app_settings(name,body) VALUES('model_profiles',?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",(json.dumps(registry,ensure_ascii=False),))
    write_configuration(configuration_document(registry,unprotect_key))

def public_registry(registry):
    return {'activeId':registry['activeId'],'configFile':'.snapmind/models.json','profiles':[{k:v for k,v in p.items() if k!='apiKeyProtected'} | {'hasApiKey':bool(p.get('apiKeyProtected')),'enabled':p['id']==registry['activeId'],'apiKeyUrl':KEY_PORTALS.get(p['vendor'])} for p in registry['profiles']]}

def get_profiles(path):
    with sqlite3.connect(path) as db:
        registry=read_registry(db)
        if not configuration_path().exists():write_configuration(configuration_document(registry,unprotect_key))
        return public_registry(registry)

def get_configuration(path, reveal_keys=False):
    with sqlite3.connect(path) as db:registry=read_registry(db)
    document=configuration_document(registry,unprotect_key)
    if not configuration_path().exists():write_configuration(document)
    if not reveal_keys:
        for item in document.get('speech',{}).get('profiles',[]):
            if item.get('apiKey'):item['apiKey']='••••••••••'
        if document.get('ocr',{}).get('apiKey'):document['ocr']['apiKey']='••••••••••'
        for item in document['models']:
            if item['apiKey']:item['apiKey']='••••••••••'
    return document

def save_profile(path, profile_id, config, *, draft=False):
    if not config.name.strip() or not draft and not config.model.strip():
        raise HTTPException(400,'请填写配置名称和模型名称')
    url=config.baseUrl.strip().rstrip('/') if draft else normalize_url(config.baseUrl)
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        registry=read_registry(db)
        previous=next((p for p in registry['profiles'] if p['id']==profile_id),None)
        if not previous and len(registry['profiles'])>=30:
            raise HTTPException(400,'最多保存 30 个模型配置')
        key=(config.apiKey or '').strip()
        previous_key=unprotect_key((previous or {}).get('apiKeyProtected'))
        key_changed=bool(key) and key!=previous_key
        protected=protect_key(key) if key_changed and not config.clearApiKey else None
        profile={'id':profile_id,'name':config.name.strip(),'vendor':config.vendor,'provider':config.provider,'baseUrl':url,'model':config.model.strip(),'vision':config.vision}
        if not config.clearApiKey:
            profile['apiKeyProtected']=protected or (previous or {}).get('apiKeyProtected','')
        if not draft and config.vendor in KEY_REQUIRED and config.provider=='openai-compatible' and not profile.get('apiKeyProtected') and not config.clearApiKey:
            raise HTTPException(400,'该服务需要 API Key，请填写后保存')
        profile['saved']=profile_ready(profile)
        changed=any(profile.get(field)!=(previous or {}).get(field) for field in ('provider','baseUrl','model','vision')) or key_changed or config.clearApiKey
        if changed and registry['activeId']==profile_id:
            registry['activeId']=None
        if previous:
            registry['profiles'][registry['profiles'].index(previous)]=profile
        else:
            registry['profiles'].append(profile)
        write_registry(db,registry)
    return public_registry(registry)

def set_active(path, selection):
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        registry=read_registry(db)
        if selection.activeId:
            profile=next((p for p in registry['profiles'] if p['id']==selection.activeId),None)
            if not profile or not profile.get('saved'):
                raise HTTPException(400,'请先保存模型配置，再启用')
            if profile.get('vendor') in KEY_REQUIRED and profile['provider']=='openai-compatible' and not profile.get('apiKeyProtected'):
                raise HTTPException(400,'请先填写 API Key 并保存，再启用此模型')
        registry['activeId']=selection.activeId
        write_registry(db,registry)
    return public_registry(registry)

def unprotect_key(value):
    if not value:
        return ''
    try:
        data=bytes.fromhex(value)
        buffer=ctypes.create_string_buffer(data)
        source=Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
        target=Blob()
        crypt=ctypes.WinDLL('crypt32',use_last_error=True)
        crypt.CryptUnprotectData.argtypes=[ctypes.POINTER(Blob),ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_void_p,ctypes.c_ulong,ctypes.POINTER(Blob)]
        if not crypt.CryptUnprotectData(ctypes.byref(source),None,None,None,None,1,ctypes.byref(target)):
            raise ValueError()
        kernel=ctypes.WinDLL('kernel32');kernel.LocalFree.argtypes=[ctypes.c_void_p]
        try:
            return ctypes.string_at(target.data,target.size).decode('utf-8')
        finally:
            kernel.LocalFree(target.data)
    except (ValueError,OSError,AttributeError):
        raise HTTPException(400,'无法读取已保存的密钥，请重新填写 API Key')

def endpoint(profile, method):
    if profile['provider']=='ollama':
        return profile['baseUrl']+('/api/tags' if method=='models' else '/api/chat')
    return profile['baseUrl']+'/'+method

def profile_for_request(path, profile_id, config):
    with sqlite3.connect(path) as db:
        registry=read_registry(db)
    previous=next((p for p in registry['profiles'] if p['id']==profile_id),{})
    profile={'id':profile_id,'name':config.name.strip(),'provider':config.provider,'baseUrl':normalize_url(config.baseUrl),'model':config.model.strip(),'vision':config.vision}
    key='' if config.clearApiKey else (config.apiKey or '').strip() or unprotect_key(previous.get('apiKeyProtected'))
    return profile,key

def safe_http_error(status):
    if status in (401,403):return '认证失败，请检查 API Key、账号权限和接口区域'
    if status==404:return '接口不存在，请检查地址和接口类型'
    if status==429:return '请求受限或额度不足，请稍后重试'
    return f'模型服务返回 HTTP {status}，请检查接口和模型名称'

async def query_models(path, profile_id, config, *, measure_only=False):
    profile,key=profile_for_request(path,profile_id,config)
    if not measure_only and not key:
        raise HTTPException(400,'请先填写 API Key，再获取模型列表')
    headers={'Authorization':'Bearer '+key} if key else {}
    started=time.perf_counter()
    status_code=None
    models=[]
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False,trust_env=False) as client:
            cursor=None
            cursors=set()
            for page in range(100):
                response=await client.get(endpoint(profile,'models'),headers=headers,**({'params':{'after':cursor}} if cursor else {}))
                status_code=response.status_code
                if not response.is_success:
                    message=safe_http_error(status_code)
                    if not measure_only and status_code in (404,405):message='该接口未提供模型列表，仍可手动填写模型名称；请核对平台的模型列表接口支持情况'
                    raise HTTPException(400,message)
                payload=response.json()
                records=payload.get('models' if profile['provider']=='ollama' else 'data')
                if not isinstance(records,list):raise ValueError()
                page_models=[item.get('name') if profile['provider']=='ollama' else item.get('id') for item in records if isinstance(item,dict)]
                models.extend(m for m in page_models if isinstance(m,str) and m.strip())
                if measure_only or not payload.get('has_more'):break
                cursor=payload.get('last_id') or (page_models[-1] if page_models else None)
                if not cursor or cursor in cursors or page==99:raise HTTPException(400,'模型列表分页异常，请检查接口或手动填写模型名称')
                cursors.add(cursor)
                if time.perf_counter()-started>15:raise HTTPException(408,'获取模型列表超时，请稍后重试')
        models=list(dict.fromkeys(models))
    except httpx.TimeoutException:
        raise HTTPException(408,'连接超时，请检查地址与网络')
    except httpx.RequestError:
        raise HTTPException(400,'无法连接模型服务，请检查接口地址、网络或本地服务是否启动')
    except (ValueError,AttributeError):
        raise HTTPException(400,'服务返回格式不正确，请检查接口类型')
    return {'ok':True,'latencyMs':round((time.perf_counter()-started)*1000,1),'models':models,'modelAvailable':profile['model'] in models if profile['model'] else None,'statusCode':status_code}

async def test_profile(path, profile_id, config):
    profile_for_request(path,profile_id,config)
    started=time.perf_counter()
    try:
        return await query_models(path,profile_id,config,measure_only=True)
    except HTTPException as e:
        return {'ok':False,'latencyMs':round((time.perf_counter()-started)*1000,1),'models':[],'modelAvailable':None,'error':e.detail}

def open_key_portal(vendor):
    url=KEY_PORTALS.get(vendor)
    if not url:raise HTTPException(400,'该配置没有预设的 API Key 获取页面')
    if not webbrowser.open(url,new=2):raise HTTPException(500,'无法打开浏览器，请手动访问 API Key 链接')
    return {'opened':True}

def get_active_profile(path):
    with sqlite3.connect(path) as db:
        registry=read_registry(db)
    return next((p for p in registry['profiles'] if p['id']==registry['activeId'] and p.get('saved')),None)
