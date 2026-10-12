"""Opt-in end-to-end verification using a generated two-column image only."""
import base64
import io
import json
from pathlib import Path
import sys
import time
import httpx
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
if '--live' not in sys.argv: raise SystemExit('Pass --live to test the configured OCR and LLM with synthetic content.')
out=ROOT/'artifacts'/'inline-translation-live';out.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(900,540),'#fbf9ff');draw=ImageDraw.Draw(image)
for text,x,y,size in [('Project settings',50,60,26),('Save changes',50,140,24),('Copy selected text',50,220,24),
                      ('Translation preview',500,60,26),('Cancel operation',500,140,24),('Keep each line separate',500,220,24)]:
    draw.text((x,y),text,font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',size),fill='#30283f',anchor='lt')
image.save(out/'source.png');buffer=io.BytesIO();image.save(buffer,format='PNG')
asset={'id':'live-inline-synthetic','name':'Synthetic two columns','width':900,'height':540,'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()}
with httpx.Client(timeout=240,trust_env=False) as client:
    started=time.perf_counter()
    response=client.post('http://127.0.0.1:8776/api/capture/locate',json={'asset':asset,'granularity':'line'})
    if response.status_code!=200: raise SystemExit('Location API failed: HTTP '+str(response.status_code))
    location=response.json();location_seconds=round(time.perf_counter()-started,2)
    assert location['width']==900 and location['height']==540
    assert len(location['regions'])==6 and all(r['granularity']=='line' for r in location['regions'])
    lines=[{k:r[k] for k in ['id','text','bbox']} for r in location['regions']]
    print('OCR line positions received; starting configured LLM translation.',flush=True)
    started=time.perf_counter()
    response=client.post('http://127.0.0.1:8776/api/capture/translate-inline',json={'asset':asset,'lines':lines,'language':'zh-CN'})
    if response.status_code!=200: raise SystemExit('Translation API failed: HTTP '+str(response.status_code))
    translation=response.json();translation_seconds=round(time.perf_counter()-started,2)
    assert len(translation['lines'])==6
    assert [r['id'] for r in translation['lines']]==[r['id'] for r in lines]
    assert [r['bbox'] for r in translation['lines']]==[r['bbox'] for r in lines]
    assert any(r['text']!=r['sourceText'] for r in translation['lines'])
record={'syntheticOnly':True,'asset':asset,'location':location,'translation':translation,
        'latencySeconds':{'location':location_seconds,'translation':translation_seconds}}
(out/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'lines':6,'ocrMode':location['mode'],'ocrModel':location.get('model'),'fallback':location['fallback'],
                  'latencySeconds':record['latencySeconds'],'idsAndCoordinatesPreserved':True},ensure_ascii=True),flush=True)
