"""PaddleOCR first, Windows OCR fallback. LLMs never generate geometry here."""
import asyncio
import hashlib
import json
import time
from collections import OrderedDict
from copy import deepcopy
from threading import Lock
from fastapi import HTTPException
from .ocr_settings import active_ocr
from .ocr_usage import reserve, pause_cloud, usage_summary
from .paddle_ocr import recognize_paddle, image_bytes, PaddleFailure
from .capture_processing import recognize_positions_async

_local_cache=OrderedDict()
_local_lock=Lock()
LOCAL_CACHE_TTL=30

def local_cached(path,data,document=None):
    key=(str(path),hashlib.sha256(data.encode()).hexdigest())
    now=time.monotonic()
    with _local_lock:
        for expired in [key for key,(created,_) in _local_cache.items() if now-created>=LOCAL_CACHE_TTL]:_local_cache.pop(expired)
        if document is None:
            cached=_local_cache.get(key)
            if cached:_local_cache.move_to_end(key);return deepcopy(cached[1])
        elif document.get('text','').strip() and document.get('regions') and len(json.dumps(document,ensure_ascii=False).encode())<=512000:
            _local_cache[key]=(now,deepcopy(document));_local_cache.move_to_end(key)
            while len(_local_cache)>8:_local_cache.popitem(last=False)
    return None

def coordinates(document):
    width,height=document['width'],document['height']
    items=[]
    for region in document['regions']:
        box=region.get('bbox')
        if region.get('page',0)!=0 or not box: continue
        box=[max(0,min(width if i%2==0 else height,v)) for i,v in enumerate(box)]
        if box[2]<=box[0] or box[3]<=box[1]: continue
        items.append(region | {'id':f'text-{len(items)+1}','bbox':box})
    if document['text'].strip() and not items:
        raise PaddleFailure('invalid-result','识别结果缺少可用的文字坐标')
    return document | {'regions':items}

async def locate(path,data,require_lines=False,cloud_timeout=None):
    # Validate before reserving quota or falling back on malformed client input.
    image_bytes(data)
    reason=None;config=None
    try:
        config=active_ocr(path)
        if config:
            # VL produces paragraph/table blocks. Inline translation requires the
            # OCR subpipeline in Structure; this does not change saved settings.
            if require_lines and config.get('model','').startswith('PaddleOCR-VL'):
                config=config | {'model':'PP-StructureV3'}
            reason=reserve(path,config)
            if reason is None:
                try:
                    result=coordinates(await asyncio.wait_for(recognize_paddle(config,data),timeout=cloud_timeout))
                    if require_lines and any(r.get('granularity')!='line' for r in result['regions']):
                        raise PaddleFailure('block-only','云端未提供文字行坐标')
                    if require_lines: result=await asyncio.to_thread(refine_line_boxes,data,result)
                    return result | {'fallback':False,'model':config.get('model'),'usage':usage_summary(path,config)}
                except (HTTPException,ValueError,TypeError,KeyError,TimeoutError) as error:
                    reason=getattr(error,'reason','unavailable')
                    if not isinstance(error,PaddleFailure) and isinstance(error,HTTPException):
                        reason='timeout' if error.status_code==408 else 'unavailable'
                    if isinstance(error,TimeoutError):reason='timeout'
                    pause_cloud(path,config,reason)
        else:
            reason='disabled'
            cached=local_cached(path,data)
            if cached is not None:return cached|{'cacheHit':True}
    except HTTPException:
        reason='configuration'
    # Cancellation must propagate; a cancelled request never starts a fallback job.
    await asyncio.sleep(0)
    result=coordinates(await recognize_positions_async(data))
    result=result | {'fallback':True,'fallbackReason':reason,'primary':'paddleocr',
                     'usage':usage_summary(path,config) if config else None}
    if reason=='disabled':local_cached(path,data,result)
    return result

def refine_line_boxes(data,document):
    """Trim uniform OCR padding using image pixels, retaining the original OCR box.

    Conservative: only flat backgrounds and compact ink are refined. Pictures,
    gradients, thin grid rules and crowded lines keep their provider coordinates.
    """
    import io
    from PIL import Image
    raw,_,_,_=image_bytes(data)
    image=Image.open(io.BytesIO(raw)).convert('RGB')
    regions=[]
    for item in document['regions']:
        l,t,r,b=map(round,item['bbox']);w,h=r-l,b-t
        refined=item
        if w>=4 and 5<=h<=150 and w*h<=350000:
            crop=image.crop((l,t,r,b));pixels=crop.load()
            border=[pixels[x,y] for x in range(w) for y in (0,h-1)]+[pixels[x,y] for y in range(h) for x in (0,w-1)]
            bins={}
            for p in border:
                key=tuple(v//16 for v in p);bins[key]=bins.get(key,0)+1
            dominant=max(bins,key=bins.get)
            if bins[dominant]/len(border)>=.72:
                samples=[p for p in border if tuple(v//16 for v in p)==dominant]
                bg=tuple(sum(p[i] for p in samples)/len(samples) for i in range(3))
                points=[]
                for y in range(h):
                    for x in range(w):
                        if max(abs(pixels[x,y][i]-bg[i]) for i in range(3))>45: points.append((x,y))
                if points:
                    left=min(x for x,y in points);right=max(x for x,y in points)+1
                    top=min(y for x,y in points);bottom=max(y for x,y in points)+1
                    # A rule/box edge or a textured crop should not redefine a text line.
                    if bottom-top>=4 and right-left>=3 and len(points)/(w*h)<.55 and right-left>=w*.3:
                        refined=item | {'ocrBbox':item['bbox'],'bbox':[l+left,t+top,l+right,t+bottom]}
        regions.append(refined)
    return document | {'regions':regions}
