"""Opt-in live verification: one generated image, no desktop/user document upload."""
import asyncio
import base64
import json
from pathlib import Path
import sys
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
from backend.app.ocr_locator import locate
from backend.app.ocr_settings import get_ocr,import_ocr_environment

async def main():
    if '--live' not in sys.argv: raise SystemExit('Pass --live to call the configured PaddleOCR API with a generated image.')
    root=ROOT/'artifacts'/'paddle-location';root.mkdir(parents=True,exist_ok=True)
    image=Image.new('RGB',(1000,500),'#fbf9ff');draw=ImageDraw.Draw(image)
    truth=[]
    for text,x,y,size in [('SnapMind position test',40,40,30),('文字定位测试',40,120,28),('Left column',40,220,24),('Right column',550,220,24),('Save result',40,320,24),('Cancel',550,320,24)]:
        font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',size)
        draw.text((x,y),text,font=font,fill='#30283f',anchor='lt')
        truth.append({'text':text,'bbox':list(draw.textbbox((x,y),text,font=font,anchor='lt'))})
    path=root/'synthetic.png';image.save(path)
    db=ROOT/'backend'/'data'/'snapmind.sqlite3';import_ocr_environment(db)
    started=time.perf_counter()
    result=await locate(db,'data:image/png;base64,'+base64.b64encode(path.read_bytes()).decode())
    assert result['width']==1000 and result['height']==500
    assert result['coordinateSpace']=='image-pixels' and result['regions']
    for region in result['regions']:
        draw.rectangle(region['bbox'],outline='#a040ef',width=2)
    image.save(root/'position-overlay.png')
    record={'syntheticOnly':True,'latencySeconds':round(time.perf_counter()-started,2),'truth':truth,'result':result}
    (root/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    settings=get_ocr(db)
    print(json.dumps({'mode':result['mode'],'fallback':result['fallback'],'fallbackReason':result.get('fallbackReason'),
                      'regions':len(result['regions']),'granularities':sorted({r.get('granularity') for r in result['regions']}),
                      'latencySeconds':record['latencySeconds'],'dailyLimit':settings['dailyLimit'],'submitted':settings['usage']['submitted']},ensure_ascii=True))
    print('Saved synthetic coordinates and overlay in artifacts/paddle-location/')

asyncio.run(main())
