"""One real model call using only the generated, UIA-verified fixture image."""
import base64
import json
import time
from pathlib import Path
import httpx
from PIL import Image

root=Path(__file__).resolve().parents[1]/'artifacts'/'uia-grounding'
info=json.loads((root/'fixture.json').read_text(encoding='utf-8'))
assert json.loads((root/'results.json').read_text())['passed']
image=root/'fixture.png'
width,height=Image.open(image).size
types=['Button','Button','Edit','ComboBox','CheckBox']
controls=[{'id':f'control-{i+1}','text':item['text'] or item['display'],'controlType':types[i],
           'bbox':[v-(info['y'] if n%2 else info['x']) for n,v in enumerate(item['bbox'])]}
          for i,item in enumerate(info['expected'])]
asset={'id':'uia-verified-fixture','name':'Generated control fixture','data':'data:image/png;base64,'+base64.b64encode(image.read_bytes()).decode(),'width':width,'height':height,'scenario':'custom'}
start=time.perf_counter()
response=httpx.post('http://127.0.0.1:8776/api/capture/annotate',json={'asset':asset,'controls':controls,
    'prompt':'圈出 Save 按钮，并给 Username 输入框添加一个简短气泡注释，说明它用于填写用户名。只标注这两个控件。'},timeout=165)
elapsed=time.perf_counter()-start
response.raise_for_status();result=response.json()
expected=[c['bbox'] for c in controls[:1]+controls[2:3]]
assert len(result['annotations'])==2,result
assert all(a['locationSource']=='uia' and a['bbox'] in expected for a in result['annotations']),result
assert {tuple(a['bbox']) for a in result['annotations']}=={tuple(b) for b in expected}
record={'passed':True,'latencySeconds':round(elapsed,2),'result':result,'input':'generated verified controls only'}
(root/'model-results.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(record,ensure_ascii=False))
