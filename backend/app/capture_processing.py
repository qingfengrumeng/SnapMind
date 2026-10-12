"""One-shot screenshot tools. OCR is local and never falls back to sample text."""
import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
from pathlib import Path
from PIL import Image
from fastapi import HTTPException

def clean_transcription(text: str) -> str:
    # Remove only known uncertainty markers, preserving real text and its whitespace.
    return re.sub(r'\[\s*(?:无法辨认|无法识别|無法辨認|無法識別)\s*\]|【\s*(?:无法辨认|无法识别|無法辨認|無法識別)\s*】|［\s*(?:无法辨认|无法识别|無法辨認|無法識別)\s*］', '', text)

def recognize(data: str) -> str:
    if os.name != 'nt':
        raise HTTPException(400, '本地文字识别目前支持 Windows 桌面端。')
    try:
        image = Image.open(io.BytesIO(base64.b64decode(data.split(',', 1)[1], validate=True))).convert('RGB')
        if image.width * image.height > 40_000_000:
            raise ValueError('image size')
        if image.width > 2400:
            image = image.resize((2400, max(1, round(image.height * 2400 / image.width))))
        parts = []
        for top in range(0, image.height, 2400):
            buf = io.BytesIO()
            image.crop((0, top, image.width, min(top + 2400, image.height))).save(buf, format='PNG')
            parts.append(base64.b64encode(buf.getvalue()).decode('ascii'))
        process = subprocess.run([sys.executable,str(Path(__file__).with_name('windows_ocr.py'))], input=json.dumps({'images': parts}), capture_output=True, text=True, encoding='utf-8', timeout=45, creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode:
            raise HTTPException(400, '本地文字识别不可用，请检查 Windows 是否安装了中文或英文 OCR 语言组件。')
        return json.loads(process.stdout.lstrip('\ufeff'))['text'].strip()
    except HTTPException:
        raise
    except subprocess.TimeoutExpired:
        raise HTTPException(408, '文字识别超时，请缩小截图区域后重试。')
    except (ValueError, KeyError, OSError):
        raise HTTPException(400, '无法读取截图或识别结果。')

async def recognize_async(data: str) -> str:
    return await asyncio.to_thread(recognize, data)


def recognize_positions(data: str):
    """Windows OCR with word and visual-line boxes mapped back to source pixels."""
    if os.name!='nt': raise HTTPException(503,'本地降级识别需要 Windows OCR')
    try:
        image=Image.open(io.BytesIO(base64.b64decode(data.split(',',1)[1],validate=True))).convert('RGB')
        width,height=image.size
        if width*height>40_000_000: raise ValueError()
        scale=min(1,2400/width)
        if scale<1: image=image.resize((2400,max(1,round(height*scale))))
        sx,sy=width/image.width,height/image.height
        parts=[];offsets=[]
        for top in range(0,image.height,2000):
            buffer=io.BytesIO()
            image.crop((0,top,image.width,min(top+2000,image.height))).save(buffer,format='PNG')
            parts.append(base64.b64encode(buffer.getvalue()).decode('ascii'));offsets.append(top)
        from .ocr_recovery import text_strips, strip_atlas, merge_atlas
        original_count=len(parts);mappings=[]
        # Reuse this worker/engine: document cells are padded and enlarged so
        # table rules and dense layouts do not hide text from Windows OCR.
        for atlas,mapping in strip_atlas(text_strips(image)):
            buffer=io.BytesIO();atlas.save(buffer,format='PNG')
            parts.append(base64.b64encode(buffer.getvalue()).decode('ascii'));mappings.append(mapping)
        process=subprocess.run([sys.executable,str(Path(__file__).with_name('windows_ocr.py'))],input=json.dumps({'images':parts,'locations':True}),capture_output=True,text=True,encoding='utf-8',timeout=45,creationflags=subprocess.CREATE_NO_WINDOW)
        if process.returncode: raise HTTPException(503,'Windows OCR 不可用，请安装中文或英文 OCR 语言组件')
        result=json.loads(process.stdout.lstrip('\ufeff'))
        regions=[]
        for offset,document in zip(offsets,result['documents']):
            for line in document['lines']:
                groups=[];group=[]
                for word in line['words']:
                    box=word['bbox']
                    if group and box[0]-group[-1]['bbox'][2]>max(18,(box[3]-box[1])*1.5):
                        groups.append(group);group=[]
                    group.append(word)
                if group: groups.append(group)
                for group in groups:
                    words=[{'text':w['text'],'bbox':[w['bbox'][0]*sx,(w['bbox'][1]+offset)*sy,w['bbox'][2]*sx,(w['bbox'][3]+offset)*sy]} for w in group]
                    box=[min(w['bbox'][0] for w in words),min(w['bbox'][1] for w in words),max(w['bbox'][2] for w in words),max(w['bbox'][3] for w in words)]
                    regions.append({'text':' '.join(w['text'] for w in words),'bbox':box,'words':words,'label':'text','page':0,'granularity':'line'})
        document={'text':result['text'].strip(),'regions':regions,'width':width,'height':height,'mode':'windows-ocr','coordinateSpace':'image-pixels','language':result.get('language')}
        # Atlas coordinates refer to the resized image; map them back once.
        for mapping in mappings:
            for tile in mapping:tile['bbox']=[value*(sx if i%2==0 else sy) for i,value in enumerate(tile['bbox'])]
        return merge_atlas(document,mappings,result['documents'][original_count:])
    except HTTPException: raise
    except subprocess.TimeoutExpired: raise HTTPException(408,'本地 Windows OCR 识别超时，请缩小截图范围')
    except (OSError,ValueError,TypeError,KeyError,IndexError): raise HTTPException(400,'无法读取截图或 Windows OCR 结果')


async def recognize_positions_async(data):
    return await asyncio.to_thread(recognize_positions,data)
