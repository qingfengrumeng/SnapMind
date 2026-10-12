"""PaddleOCR synchronous endpoints and AI Studio asynchronous job API."""
import asyncio
import base64
import io
import math
import time
import json
import ipaddress
import re
from urllib.parse import urlsplit, quote
import httpx
from PIL import Image
from fastapi import HTTPException
from .model_profiles import normalize_url, unprotect_key

JOB_TIMEOUT = 60
POLL_INTERVAL = 2
MAX_RESULT_BYTES = 8_000_000

class PaddleFailure(HTTPException):
    def __init__(self, reason, detail, status=502):
        self.reason=reason
        super().__init__(status,detail)

def image_bytes(data):
    try:
        raw=base64.b64decode(data.split(',',1)[1],validate=True)
        with Image.open(io.BytesIO(raw)) as image:
            width,height=image.size
            if width*height>40_000_000: raise ValueError()
            image_format=image.format
            image.verify()
        return raw,width,height,image_format
    except (ValueError,IndexError,OSError): raise HTTPException(400,'无法读取截图图片')

def number(value):
    if isinstance(value,(int,float)) and not isinstance(value,bool) and math.isfinite(value): return float(value)
    return None

def region(text, box=None, polygon=None, confidence=None, label='text'):
    result = {'text':text,'label':label}
    if isinstance(polygon,list) and len(polygon)>=3 and all(isinstance(p,list) and len(p)==2 and all(number(n) is not None for n in p) for p in polygon):
        result['polygon'] = polygon
        xs,ys = zip(*polygon)
        box = [min(xs),min(ys),max(xs),max(ys)]
    if isinstance(box,list) and len(box)==4 and all(number(n) is not None for n in box) and box[2]>=box[0] and box[3]>=box[1]: result['bbox'] = box
    score = number(confidence)
    if score is not None: result['confidence'] = score
    return result

def parse_result(payload):
    if not isinstance(payload,dict) or payload.get('errorCode',0)!=0 or not isinstance(payload.get('result'),dict): raise HTTPException(502,'PaddleOCR 返回了无效识别结果')
    result = payload['result']
    pages = result.get('ocrResults',result.get('layoutParsingResults'))
    if not isinstance(pages,list): raise HTTPException(502,'请检查 PaddleOCR 接口地址是否对应 OCR 或版面解析服务')
    regions,texts = [],[]
    for page_index,page in enumerate(pages):
        if not isinstance(page,dict): raise HTTPException(502,'PaddleOCR 返回格式异常')
        pruned = page.get('prunedResult',{})
        if not isinstance(pruned,dict): raise HTTPException(502,'PaddleOCR 返回格式异常')
        ocr = pruned.get('overall_ocr_res') or pruned
        if not isinstance(ocr,dict): raise HTTPException(502,'PaddleOCR 返回格式异常')
        lines = ocr.get('rec_texts',[])
        scores,polygons,boxes = ocr.get('rec_scores',[]),ocr.get('rec_polys',[]),ocr.get('rec_boxes',[])
        if not all(isinstance(v,list) for v in (lines,scores,polygons,boxes)): raise HTTPException(502,'PaddleOCR 返回格式异常')
        for i,text in enumerate(lines):
            if not isinstance(text,str) or not text.strip(): continue
            item = region(text, boxes[i] if i<len(boxes) else None, polygons[i] if i<len(polygons) else None, scores[i] if i<len(scores) else None)
            regions.append(item | {'page':page_index,'granularity':'line'});texts.append(text)
        blocks = pruned.get('parsing_res_list',[])
        for block in blocks:
            if not isinstance(block,dict) or not isinstance(block.get('block_content'),str): continue
            text = block['block_content'].strip()
            if not text: continue
            # Prefer line coordinates when available. Layout regions are not line boxes.
            if not lines: regions.append(region(text,block.get('block_bbox'),label=block.get('block_label','text')) | {'page':page_index,'granularity':'block'})
        markdown = page.get('markdown',{})
        if not lines:
            text = markdown.get('text','') if isinstance(markdown,dict) else ''
            texts.append(text if isinstance(text,str) and text.strip() else '\n'.join(b['text'] for b in regions if b['page']==page_index))
        if len(regions)>10000: raise HTTPException(502,'OCR 返回内容过多，请缩小截图范围')
    text = '\n'.join(t for t in texts if t).strip()
    if len(text)>200000: raise HTTPException(502,'OCR 返回内容过长，请缩小截图范围')
    return {'text':text,'regions':regions,'mode':'paddleocr','coordinateSpace':'image-pixels'}

def failure(status):
    if status in (401,403): return 'PaddleOCR 认证失败，请检查 API Key / Access Token'
    if status==404: return 'PaddleOCR 接口不存在，请复制平台调用示例中的完整 API URL'
    if status==429: return 'PaddleOCR 请求受限或额度不足，请稍后重试'
    return f'PaddleOCR 服务返回 HTTP {status}，请检查接口地址与服务状态'

async def recognize_paddle(config, data):
    raw,width,height,image_format=image_bytes(data)
    key = unprotect_key(config.get('apiKeyProtected'))
    if not key: raise HTTPException(400,'请填写 PaddleOCR API Key')
    if config.get('apiMode','sync')=='async':
        return await recognize_job(config,raw,width,height,image_format,key)
    encoded=base64.b64encode(raw).decode('ascii')
    payload = {'file':encoded,'fileType':1,'useDocOrientationClassify':False,'useDocUnwarping':False,'visualize':False}
    if config['model'].startswith('PP-OCR'): payload['useTextlineOrientation'] = False
    else: payload['useLayoutDetection'] = True
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(90,connect=8),follow_redirects=False,trust_env=False) as client:
            response = await client.post(normalize_url(config['baseUrl']),headers={'Authorization':'token '+key},json=payload)
        if not response.is_success: raise HTTPException(400,failure(response.status_code))
        result = parse_result(response.json())
        return result | {'width':width,'height':height}
    except httpx.TimeoutException: raise HTTPException(408,'PaddleOCR 识别超时，请缩小截图或稍后重试')
    except httpx.RequestError: raise HTTPException(400,'无法连接 PaddleOCR，请检查接口地址和网络')
    except (ValueError,TypeError,KeyError): raise HTTPException(502,'PaddleOCR 返回格式异常，请核对完整 API URL')

def failure_reason(message,default='unavailable'):
    message=str(message).lower()
    if any(x in message for x in ('quota','daily limit','额度','配额','每日','用量超')): return 'cloud-quota'
    if any(x in message for x in ('rate limit','frequency','频率')): return 'rate-limit'
    return default

def job_data(response):
    if not response.is_success:
        reason='rate-limit' if response.status_code==429 else 'authentication' if response.status_code in (401,403) else 'unavailable'
        if response.status_code in (402,429): reason=failure_reason(response.text,reason)
        raise PaddleFailure(reason,failure(response.status_code))
    payload=response.json()
    if not isinstance(payload,dict): raise ValueError()
    if payload.get('code',0)!=0:
        # Inspect provider messages for classification, never return their text or URLs.
        reason=failure_reason(payload.get('msg',''))
        raise PaddleFailure(reason,'PaddleOCR 云端额度已用尽' if reason=='cloud-quota' else 'PaddleOCR 任务接口暂时不可用')
    data=payload.get('data')
    if not isinstance(data,dict): raise ValueError()
    return data

def result_url(value):
    if not isinstance(value,str): raise ValueError()
    url=urlsplit(value)
    if url.scheme!='https' or not url.hostname or url.username or url.password or url.fragment: raise ValueError()
    if url.hostname.lower()=='localhost' or url.hostname.lower().endswith(('.localhost','.local')): raise ValueError()
    try: address=ipaddress.ip_address(url.hostname)
    except ValueError:
        if re.fullmatch(r'[0-9.:]+',url.hostname): raise ValueError()
    else:
        if not address.is_global: raise ValueError()
    return value

async def download_jsonl(client,url):
    chunks=[];size=0
    # Separate request headers: the signed resource URL must never receive the API token.
    async with client.stream('GET',result_url(url)) as response:
        if not response.is_success: raise PaddleFailure('unavailable','无法下载 PaddleOCR 识别结果')
        async for chunk in response.aiter_bytes():
            size+=len(chunk)
            if size>MAX_RESULT_BYTES: raise ValueError()
            chunks.append(chunk)
    return b''.join(chunks).decode('utf-8-sig')

async def recognize_job(config,raw,width,height,image_format,key):
    url=normalize_url(config['baseUrl'])
    headers={'Authorization':'bearer '+key}
    options={'useDocOrientationClassify':False,'useDocUnwarping':False,'useChartRecognition':False}
    extension={'JPEG':'jpg','WEBP':'webp'}.get(image_format,'png')
    mime={'JPEG':'image/jpeg','WEBP':'image/webp'}.get(image_format,'image/png')
    try:
        async with asyncio.timeout(JOB_TIMEOUT):
            async with httpx.AsyncClient(timeout=httpx.Timeout(20,connect=8),follow_redirects=False,trust_env=False) as client:
                submitted=job_data(await client.post(url,headers=headers,data={'model':config['model'],'optionalPayload':json.dumps(options)},files={'file':('capture.'+extension,raw,mime)}))
                job_id=submitted['jobId']
                if not isinstance(job_id,str) or not re.fullmatch(r'[A-Za-z0-9_-]{1,160}',job_id): raise ValueError()
                while True:
                    status=job_data(await client.get(url+'/'+quote(job_id,safe=''),headers=headers))
                    state=status.get('state')
                    if state=='done':
                        content=await download_jsonl(client,status['resultUrl']['jsonUrl'])
                        break
                    if state=='failed':
                        reason=failure_reason(status.get('errorMsg',''))
                        raise PaddleFailure(reason,'PaddleOCR 云端解析失败')
                    if state not in ('pending','running'): raise ValueError()
                    await asyncio.sleep(POLL_INTERVAL)
                pages=[]
                for line in content.splitlines():
                    if not line.strip(): continue
                    payload=json.loads(line)
                    parsed=parse_result(payload)
                    if not isinstance(payload.get('result'),dict): raise ValueError()
                    result=payload['result']
                    pages.extend(result.get('ocrResults',result.get('layoutParsingResults',[])))
                if not pages: raise ValueError()
                result=parse_result({'result':{'layoutParsingResults':pages}})
                return result | {'width':width,'height':height,'apiMode':'async'}
    except PaddleFailure: raise
    except (TimeoutError,httpx.TimeoutException): raise PaddleFailure('timeout','PaddleOCR 等待超时',408)
    except httpx.RequestError: raise PaddleFailure('unavailable','无法连接 PaddleOCR')
    except (ValueError,TypeError,KeyError,IndexError,UnicodeError): raise PaddleFailure('invalid-result','PaddleOCR 返回的任务结果格式无效')

async def probe_ocr(config, key):
    started = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(12,connect=5),follow_redirects=False,trust_env=False) as client:
            response = await client.head(normalize_url(config.baseUrl),headers={'Authorization':('bearer ' if config.apiMode=='async' else 'token ')+key})
        ok = response.status_code in (200,204,405)
        return {'ok':ok,'latencyMs':round((time.perf_counter()-started)*1000,1),'error':None if ok else failure(response.status_code),'authVerified':False}
    except (httpx.RequestError,HTTPException):
        return {'ok':False,'latencyMs':round((time.perf_counter()-started)*1000,1),'error':'无法连接 PaddleOCR，请检查接口地址和网络','authVerified':False}
