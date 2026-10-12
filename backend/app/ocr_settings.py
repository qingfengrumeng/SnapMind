"""Independent PaddleOCR configuration, never part of the LLM registry."""
import json
import sqlite3
import hashlib
import re
from typing import Literal
from fastapi import HTTPException
from pydantic import BaseModel, Field
from .config_file import DEFAULT_OCR, read_configuration, write_configuration, configuration_document
from .model_profiles import read_registry, normalize_url, protect_key, unprotect_key

KEY_PORTAL = 'https://aistudio.baidu.com/paddleocr'

class OcrConfig(BaseModel):
    provider: Literal['paddleocr'] = 'paddleocr'
    baseUrl: str = Field(default='', max_length=2048)
    model: str = Field(default='PaddleOCR-VL-1.6', min_length=1, max_length=160)
    apiKey: str | None = Field(default=None, max_length=4096)
    clearApiKey: bool = False
    enabled: bool = False
    assistLlm: bool = True
    apiMode: Literal['async','sync'] = 'async'
    dailyLimit: int = Field(default=20000, ge=0, le=10_000_000)

def read_ocr(db):
    db.execute('CREATE TABLE IF NOT EXISTS app_settings (name TEXT PRIMARY KEY, body TEXT NOT NULL)')
    row = db.execute("SELECT body FROM app_settings WHERE name='ocr'").fetchone()
    previous = json.loads(row[0]) if row else {k:v for k,v in DEFAULT_OCR.items() if k!='apiKey'}
    document = read_configuration()
    if document and 'ocr' in document:
        try:
            config = OcrConfig(**document['ocr'])
        except (ValueError, TypeError):
            raise HTTPException(400, 'OCR 配置格式无效，请检查 OCR 配置字段')
        result = config.model_dump(exclude={'apiKey','clearApiKey'})
        result['dailyLimit'] = document['ocr'].get('dailyLimit',previous.get('dailyLimit',20000))
        key = (config.apiKey or '').strip()
        protected = previous.get('apiKeyProtected','')
        if key:
            try: unchanged=protected and unprotect_key(protected)==key
            except HTTPException: unchanged=False
            if not unchanged: protected=protect_key(key)
        else: protected = ''
        result['apiKeyProtected'] = protected
        return result
    return previous

def public_ocr(config):
    return {k:v for k,v in config.items() if k!='apiKeyProtected'} | {'hasApiKey':bool(config.get('apiKeyProtected')), 'apiKeyUrl':KEY_PORTAL}

def get_ocr(path):
    with sqlite3.connect(path) as db: config = read_ocr(db)
    from .ocr_usage import usage_summary
    return public_ocr(config) | {'usage':usage_summary(path,config),'fallback':'windows-ocr'}

def active_ocr(path):
    with sqlite3.connect(path) as db: config = read_ocr(db)
    if not config.get('enabled'): return None
    if not config.get('apiKeyProtected') or not config.get('baseUrl'): raise HTTPException(400, '请完善 PaddleOCR 的接口地址和 API Key')
    return config

def save_ocr(path, config):
    url = normalize_url(config.baseUrl) if config.baseUrl.strip() else ''
    with sqlite3.connect(path) as db:
        db.execute('BEGIN IMMEDIATE')
        previous = read_ocr(db)
        protected = previous.get('apiKeyProtected','')
        if config.clearApiKey: protected = ''
        elif (config.apiKey or '').strip(): protected = protect_key(config.apiKey.strip())
        result = config.model_dump(exclude={'apiKey','clearApiKey'}) | {'baseUrl':url,'apiKeyProtected':protected}
        if 'dailyLimit' not in config.model_fields_set:
            result['dailyLimit'] = previous.get('dailyLimit',20000)
        if config.enabled and (not url or not protected): raise HTTPException(400, '启用 PaddleOCR 前请填写接口地址与 API Key')
        registry = read_registry(db)
        document = configuration_document(registry, unprotect_key)
        document['ocr'] = {k:v for k,v in result.items() if k not in ('apiKeyProtected','dailyLimit')} | {'apiKey':unprotect_key(protected)}
        db.execute("INSERT INTO app_settings(name,body) VALUES('ocr',?) ON CONFLICT(name) DO UPDATE SET body=excluded.body", (json.dumps(result,ensure_ascii=False),))
        write_configuration(document)
    return get_ocr(path)


def migrate_ocr_configuration(path):
    """Remove the retired JSON field while keeping the internal fallback budget."""
    document = read_configuration()
    if not document or 'dailyLimit' not in document.get('ocr',{}): return
    with sqlite3.connect(path) as db: config = read_ocr(db)
    key = unprotect_key(config.pop('apiKeyProtected',''))
    save_ocr(path,OcrConfig(**config,apiKey=key))


def import_ocr_environment(path):
    """Import only the OCR fields once per changed .env, preserving all LLM settings.

    UI changes survive restarts when .env hasn't changed. Tests use an isolated
    configuration directory and therefore never import the user's credentials.
    """
    from .config_file import configuration_path
    env_path = configuration_path().parent / '.env'
    if not env_path.exists(): return
    values = {}
    for line in env_path.read_text(encoding='utf-8-sig').splitlines():
        match = re.match(r'^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*?)\s*$',line)
        if not match: continue
        value = match[2]
        if len(value)>=2 and value[0]==value[-1] and value[0] in ('"',"'"): value=value[1:-1]
        else: value=re.split(r'\s+#',value,maxsplit=1)[0].strip()
        values[match[1]]=value
    key = values.get('PADDLE_OCR_KEY') or values.get('PADDLEOCR_ACCESS_TOKEN')
    if not key: return
    try:
        limit = int(values.get('MAX_IMAGES_NUM','20000').replace(',','').replace('_',''))
        config = OcrConfig(baseUrl=values.get('PADDLE_OCR_JOB_URL',DEFAULT_OCR['baseUrl']),
                           model=values.get('PADDLE_OCR_MODEL','PaddleOCR-VL-1.6'),apiKey=key,
                           dailyLimit=limit,apiMode='async',enabled=True,assistLlm=True)
    except ValueError:
        raise HTTPException(400,'OCR 环境配置中的模型、接口或每日限额格式无效')
    digest = hashlib.sha256(config.model_dump_json().encode()).hexdigest()
    with sqlite3.connect(path) as db:
        row=db.execute("SELECT body FROM app_settings WHERE name='ocr_env_import'").fetchone()
        if row and row[0]==digest: return
    save_ocr(path,config)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO app_settings(name,body) VALUES('ocr_env_import',?) ON CONFLICT(name) DO UPDATE SET body=excluded.body",(digest,))
