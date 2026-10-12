"""Opt-in live annotation test using generated cards only."""
import base64
import io
import json
import time
import sys
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFont

if '--live' not in sys.argv:raise SystemExit('Pass --live to test the configured model with a synthetic image.')
out=Path(__file__).resolve().parents[1]/'artifacts/ai-callouts-live';out.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(960,620),'#fcfaff');d=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',26)
for box,bg,title,detail in [((80,100,330,310),'#e5d8fa','Settings','Configure preferences'),((520,100,880,310),'#cbdcf7','Video preview','Play the selected video')]:
    d.rounded_rectangle(box,radius=16,fill=bg,outline='#bda7d6',width=2)
    d.text((box[0]+22,box[1]+40),title,font=font,fill='#4f3a69');d.text((box[0]+22,box[1]+100),detail,font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',18),fill='#675b78')
d.rounded_rectangle((570,400,790,500),radius=16,fill='#c8e9d4',outline='#81c8a3',width=2);d.text((640,430),'Save',font=font,fill='#316f52')
image.save(out/'source.png');b=io.BytesIO();image.save(b,format='PNG')
asset={'id':'live-ai-cards','name':'Synthetic cards','width':960,'height':620,'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()}
prompt='给左侧 Settings 卡片加一个简短中文气泡说明，圈出右侧 Video preview 卡片，在下面的 Save 按钮上加一个绿勾。'
records={'syntheticOnly':True,'asset':asset,'turns':[]}
with httpx.Client(timeout=160,trust_env=False) as client:
    started=time.perf_counter();r=client.post('http://127.0.0.1:8776/api/capture/annotate',json={'asset':asset,'prompt':prompt})
    if r.status_code!=200:raise SystemExit('Annotation API failed: HTTP '+str(r.status_code))
    result=r.json();elapsed=round(time.perf_counter()-started,2)
    assert all(a['operation']=='add' for a in result['annotations'])
    assert {'callout','circle','check'}.issubset({a['kind'] for a in result['annotations']})
    existing=[{'id':'ai-'+str(i+1),'kind':a['kind'],'text':a['text'],'bbox':a['bbox']} for i,a in enumerate(result['annotations'])]
    assert all(len(a['text'])<=40 for a in existing)
    records['turns'].append({'prompt':prompt,'seconds':elapsed,'result':result})
    print(json.dumps({'turn':1,'seconds':elapsed,'kinds':[a['kind'] for a in existing]},ensure_ascii=True),flush=True)
    followup='把刚才的气泡注释改成“设置入口”，保留它的指向位置；保留其他圈线和勾选，不要新增标注。'
    started=time.perf_counter();r=client.post('http://127.0.0.1:8776/api/capture/annotate',json={'asset':asset,'prompt':followup,'existing':existing,'history':[{'role':'user','text':prompt},{'role':'assistant','text':result['answer'] or '已添加标注。'}]})
    if r.status_code!=200:raise SystemExit('Follow-up API failed: HTTP '+str(r.status_code))
    updated=r.json();elapsed=round(time.perf_counter()-started,2)
    assert updated['annotations'] and all(a['operation']=='update' for a in updated['annotations'])
    assert any(a['kind']=='callout' and a['text']=='设置入口' for a in updated['annotations'])
    records['turns'].append({'prompt':followup,'seconds':elapsed,'result':updated})
    print(json.dumps({'turn':2,'seconds':elapsed,'updates':len(updated['annotations']),'noNewMarks':True},ensure_ascii=True),flush=True)
(out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
