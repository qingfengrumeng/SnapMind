"""Two real model calls, using a generated image with no desktop/user content."""
import json,time,sys
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFont
from backend.app.image_tools import png_data
sys.stdout.reconfigure(encoding='utf-8')
output=Path('artifacts/image-tools');output.mkdir(parents=True,exist_ok=True)
image=Image.new('RGB',(720,360),'#faf7ff');draw=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',28)
draw.text((35,35),'SnapMind image conversation',fill='#41344e',font=font)
draw.text((35,105),'Code    Quantity    Price',fill='#41344e',font=font)
draw.text((35,155),'001      2              15',fill='#41344e',font=font)
draw.text((35,205),'002      3              20',fill='#41344e',font=font)
draw.text((35,280),'Only generated example data.',fill='#7d698c',font=font)
image.save(output/'live-fixture.png')
asset={'id':'generated-chat-live','name':'Generated test image','data':png_data(image),'width':720,'height':360,'scenario':'custom'}
history=[];results=[]
with httpx.Client(timeout=240,trust_env=False) as client:
    for question in ['提取截图中的表格','第二行商品买两件一共多少钱？解释一下你怎么算的。']:
        start=time.perf_counter()
        response=client.post('http://127.0.0.1:8776/api/capture/conversation',json={'assets':[asset],'selectedId':asset['id'],'prompt':question,'history':history})
        response.raise_for_status();result=response.json();elapsed=round(time.perf_counter()-start,2)
        results.append({'question':question,'seconds':elapsed,**result})
        history.extend([{'role':'user','text':question},{'role':'assistant','text':result['answer']+'\n'+json.dumps(result['payload'],ensure_ascii=False)}])
    assert results[0]['action']=='table' and results[0]['payload']['tables']
    assert results[1]['action']=='chat' and '40' in results[1]['answer']
(output/'live-results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps([{'action':r['action'],'seconds':r['seconds'],'answer':r['answer']} for r in results],ensure_ascii=False))
