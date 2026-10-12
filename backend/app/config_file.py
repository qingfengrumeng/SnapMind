"""SnapMind's JSON configuration file, written atomically under .snapmind/models.json."""
import json
import os
import re
import tempfile
from pathlib import Path
from fastapi import HTTPException

DEFAULT_OCR = {'provider':'paddleocr','baseUrl':'https://paddleocr.aistudio-app.com/api/v2/ocr/jobs','apiKey':'','model':'PaddleOCR-VL-1.6','enabled':False,'assistLlm':True,'apiMode':'async','dailyLimit':20000}

def configuration_path():
    from .local_storage import home
    return Path(os.environ.get('SNAPMIND_CONFIG_FILE',home()/'models.json'))

def configuration_document(registry,decode_key):
    stored = read_configuration()
    ocr = {k:v for k,v in (stored or {}).get('ocr',DEFAULT_OCR).items() if k!='dailyLimit'}
    return ({'speech':stored['speech']} if stored and 'speech' in stored else {}) | {'schemaVersion':1,'ocr':ocr,'activeModelId':registry['activeId'],'models':[
        {'id':p['id'],'name':p['name'],'provider':p['vendor'],'baseUrl':p['baseUrl'],
         'apiKey':decode_key(p.get('apiKeyProtected')),'model':p['model'],
         'enabled':p['id']==registry['activeId'],'vision':bool(p.get('vision'))} | ({'apiFormat':p['provider']} if p['provider']!='openai-compatible' else {})
        for p in registry['profiles']]}

def write_configuration(document):
    document = dict(document)
    if isinstance(document.get('ocr'),dict):
        document['ocr'] = {k:v for k,v in document['ocr'].items() if k!='dailyLimit'}
    path=configuration_path()
    temporary=None
    try:
        path.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=path.parent,prefix='.snapmind.',suffix='.tmp',delete=False) as output:
            temporary=Path(output.name)
            json.dump(document,output,ensure_ascii=False,indent=2)
            output.write('\n');output.flush();os.fsync(output.fileno())
        os.replace(temporary,path)
        temporary=None
    except OSError:
        raise HTTPException(500,'无法写入 .snapmind/models.json，请检查配置目录权限')
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)

def read_configuration():
    path=configuration_path()
    if not path.exists():return None
    try:
        if path.stat().st_size>2_000_000:raise ValueError()
        document=json.loads(path.read_text(encoding='utf-8-sig'))
        if document.get('schemaVersion')!=1 or not isinstance(document.get('models'),list) or len(document['models'])>30:raise ValueError()
        ids=set();active=[]
        for model in document['models']:
            if not isinstance(model,dict) or not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',model.get('id','')) or model['id'] in ids:raise ValueError()
            if not isinstance(model.get('enabled',False),bool):raise ValueError()
            ids.add(model['id'])
            if model.get('enabled'):active.append(model['id'])
        if len(active)>1:raise HTTPException(400,'配置文件中只允许一个模型的 enabled 为 true')
        document['activeModelId']=active[0] if active else None
        return document
    except (OSError,ValueError,TypeError,AttributeError):
        raise HTTPException(400,'.snapmind/models.json 格式无效，请检查 JSON 和模型字段')
