import ctypes
import json
import os
import sqlite3
from ctypes import wintypes
from urllib.parse import urlsplit
from fastapi import HTTPException
from pydantic import BaseModel, Field
from typing import Literal

class ModelConfig(BaseModel):
    provider: Literal['openai-compatible', 'ollama'] = 'openai-compatible'
    baseUrl: str = Field(max_length=2048)
    model: str = Field(min_length=1, max_length=160)
    apiKey: str | None = Field(default=None, max_length=4096)
    clearApiKey: bool = False

class Blob(ctypes.Structure):
    _fields_ = [('size', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

def protect_key(value: str) -> str:
    if os.name != 'nt':
        raise HTTPException(503, '此环境暂不支持安全保存 API Key')
    buffer = ctypes.create_string_buffer(value.encode('utf-8'))
    source = Blob(len(value.encode('utf-8')), ctypes.cast(buffer, ctypes.POINTER(ctypes.c_ubyte)))
    target = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    crypt.CryptProtectData.argtypes = [ctypes.POINTER(Blob), wintypes.LPCWSTR, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, wintypes.DWORD, ctypes.POINTER(Blob)]
    if not crypt.CryptProtectData(ctypes.byref(source), 'SnapMind model API key', None, None, None, 1, ctypes.byref(target)):
        raise HTTPException(500, '无法安全保存 API Key，请重试')
    kernel = ctypes.WinDLL('kernel32')
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    try:
        return ctypes.string_at(target.data, target.size).hex()
    finally:
        kernel.LocalFree(target.data)

def read_settings(db_path):
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS app_settings (name TEXT PRIMARY KEY, body TEXT NOT NULL)')
        row = db.execute("SELECT body FROM app_settings WHERE name='model'").fetchone()
    return json.loads(row[0]) if row else {'provider': 'openai-compatible', 'baseUrl': '', 'model': ''}

def public_settings(settings):
    return {key: settings.get(key, '') for key in ('provider', 'baseUrl', 'model')} | {'hasApiKey': bool(settings.get('apiKeyProtected'))}

def save_settings(db_path, config: ModelConfig):
    url = config.baseUrl.strip().rstrip('/')
    try:
        parsed = urlsplit(url)
        valid = parsed.scheme in ('http', 'https') and parsed.hostname and not parsed.username and not parsed.password and not parsed.query and not parsed.fragment
        parsed.port
    except ValueError:
        valid = False
    if not valid:
        raise HTTPException(400, '请输入有效的 HTTP 或 HTTPS 接口地址，不要包含密钥、查询参数或片段')
    model = config.model.strip()
    if not model:
        raise HTTPException(400, '请输入模型名称')
    key = (config.apiKey or '').strip()
    protected = protect_key(key) if key else None
    # Preserve an existing key when the password field is left blank.
    with sqlite3.connect(db_path) as db:
        db.execute('CREATE TABLE IF NOT EXISTS app_settings (name TEXT PRIMARY KEY, body TEXT NOT NULL)')
        row = db.execute("SELECT body FROM app_settings WHERE name='model'").fetchone()
        previous = json.loads(row[0]) if row else {}
        settings = {'provider': config.provider, 'baseUrl': url, 'model': model}
        if not config.clearApiKey:
            settings['apiKeyProtected'] = protected or previous.get('apiKeyProtected', '')
        db.execute("INSERT INTO app_settings(name,body) VALUES('model',?) ON CONFLICT(name) DO UPDATE SET body=excluded.body", (json.dumps(settings),))
    return public_settings(settings)
