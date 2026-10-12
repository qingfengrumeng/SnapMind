"""Reproduce text-only object mistakes and verify OCR-grounded geometry.

Uploads only a generated fixture, never a desktop image. Run with --live.
"""
import base64
import io
import json
import sys
import time
from pathlib import Path
import httpx
from PIL import Image, ImageDraw, ImageFont

if '--live' not in sys.argv:
    raise SystemExit('Pass --live to use configured OCR and multimodal services.')

out=Path(__file__).resolve().parents[1]/'artifacts/ai-annotation-grounding'
out.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(932,498),'#252525')
draw=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',22)
lines=[
    '已实现并更新开发版，工具栏新增 AI 标注：',
    '直接在截图上生成简短注释气泡，用连线指向对应内容。',
    '支持圈选、绿勾、红叉，以及继续提问修改或删除标注。',
    '气泡和指向圆点可分别拖动，支持删除、撤销。',
    '真实模型测试、交互回归和构建通过。',
    '已编辑 12 个文件',
]
truth=[]
for i,text in enumerate(lines):
    xy=(55,40+i*56)
    draw.text(xy,text,font=font,fill='#cecece')
    # Font metrics include the full advance of the final punctuation glyph.
    # Compare OCR against visible ink, matching what its boxes actually measure.
    ink=Image.new('L',image.size,0)
    ImageDraw.Draw(ink).text(xy,text,font=font,fill=255)
    truth.append({'text':text,'bbox':list(ink.getbbox())})
image.save(out/'source.png')
buffer=io.BytesIO();image.save(buffer,format='PNG')
asset={'id':'text-grounding-fixture','name':'Generated text only','width':932,'height':498,
       'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()}
records={'syntheticOnly':True,'asset':asset,'groundTruth':truth,'turns':[]}
previous=[]
if '--resume' in sys.argv and (out/'results.json').exists():
    stored=json.loads((out/'results.json').read_text(encoding='utf-8'))
    # Only reuse expensive detection/localization; always verify the follow-up.
    if stored['asset']==asset:previous=stored['turns'][:2]

def save():
    (out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')

with httpx.Client(timeout=160,trust_env=False) as client:
    def request(prompt,**kwargs):
        index=len(records['turns'])
        if index<len(previous) and previous[index]['prompt']==prompt and previous[index]['status']==200:
            records['turns'].append(previous[index]);save()
            print(json.dumps({'turn':index+1,'reusedRecordedResponse':True}),flush=True)
            return previous[index]['result']
        started=time.perf_counter()
        reply=client.post('http://127.0.0.1:8776/api/capture/annotate',json={'asset':asset,'prompt':prompt,**kwargs})
        result=reply.json();seconds=round(time.perf_counter()-started,2)
        record={'prompt':prompt,'seconds':seconds,'status':reply.status_code,'result':result}
        records['turns'].append(record);save()
        print(json.dumps({'turn':len(records['turns']),'seconds':seconds,'status':reply.status_code,
                          'annotations':len(result.get('annotations',[]))},ensure_ascii=True),flush=True)
        assert reply.status_code==200,result
        return result

    empty=request('圈出截图中的主要物品')
    assert empty['annotations']==[] and '未找到' in empty['answer']
    assert empty['approximate'] is False

    prompt='只圈出第二行文字：“'+lines[1]+'”。不要圈其他行，不要添加气泡。'
    text_result=request(prompt)
    assert len(text_result['annotations'])==1
    annotation=text_result['annotations'][0]
    assert annotation['kind']=='circle' and annotation['locationSource']=='ocr'
    target=truth[1]['bbox'];bbox=annotation['bbox']
    error=max(abs(a-b) for a,b in zip(target,bbox))
    records['textBoxMaximumEdgeErrorPixels']=error;save()
    assert error<=10,(target,bbox,error)

    existing=[{'id':'ai-1','kind':annotation['kind'],'text':annotation['text'],'bbox':bbox}]
    updated=request('把刚才的圈选改成气泡注释，内容是“注释指向对应内容”，保留原来的位置。',existing=existing,
                    history=[{'role':'user','text':prompt},{'role':'assistant','text':text_result['answer'] or '已圈出第二行。'}])
    assert len(updated['annotations'])==1
    assert updated['annotations'][0]['operation']=='update'
    assert updated['annotations'][0]['bbox']==bbox and updated['annotations'][0]['kind']=='callout'
    records['passed']=True;save()
    print(json.dumps({'passed':True,'textBoxMaximumEdgeErrorPixels':error,'textOnlyObjects':0,
                      'followupPreservesPosition':True},ensure_ascii=True),flush=True)
