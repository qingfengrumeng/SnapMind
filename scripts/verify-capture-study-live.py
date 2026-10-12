"""Opt-in real models, generated code/exam fixtures only."""
import base64
import io
import json
import sys
import time
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFont
if '--live' not in sys.argv:raise SystemExit('Pass --live to use configured OCR/LLM with synthetic fixtures.')
out=Path(__file__).resolve().parents[1]/'artifacts/capture-study-live';out.mkdir(parents=True,exist_ok=True)

def pack(image,id,name):
 image.save(out/(id+'.png'));buffer=io.BytesIO();image.save(buffer,format='PNG')
 return {'id':id,'name':name,'width':image.width,'height':image.height,'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()}

image=Image.new('RGB',(960,500),'#24252b');draw=ImageDraw.Draw(image)
font=ImageFont.truetype('C:/Windows/Fonts/consola.ttf',24)
lines=['def average(values):','    total = 0','    for value in values:','        total += value','    return total / len(values)','print(average([2, 4, 6]))']
for i,text in enumerate(lines):
 draw.text((40,65+i*50),str(41+i),font=font,fill='#9a92ac');draw.text((100,65+i*50),text,font=font,fill='#e3dcef')
code=pack(image,'code-source','代码行41到46')
papers=[];font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',25)
for i,(question,work) in enumerate([('求函数 f(x)=2x+3 在 x=4 时的值。','学生步骤：f(4)=2+4+3=9'),('求函数 f(x)=3x+1 在 x=2 时的值。','学生步骤：f(2)=3+2+1=6')]):
 image=Image.new('RGB',(900,450),'#fffdfa');draw=ImageDraw.Draw(image)
 for y,text in [(45,'练习作答 第'+str(i+1)+'页'),(130,question),(230,work)]:draw.text((55,y),text,font=font,fill='#403c48')
 papers.append(pack(image,'paper-'+str(i+1),'练习作答第'+str(i+1)+'页'))
record={'syntheticOnly':True,'codeAsset':code,'paperAssets':papers,'turns':[]}
def save():(out/'results.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
with httpx.Client(timeout=245,trust_env=False) as client:
 def request(mode,assets,prompt,history=[]):
  started=time.perf_counter();r=client.post('http://127.0.0.1:8776/api/capture/study',json={'mode':mode,'assets':assets,'prompt':prompt,'history':history})
  result=r.json();seconds=round(time.perf_counter()-started,2);record['turns'].append({'mode':mode,'prompt':prompt,'seconds':seconds,'status':r.status_code,'result':result});save()
  print(json.dumps({'mode':mode,'seconds':seconds,'status':r.status_code,'notes':len(result.get('notes',[]))},ensure_ascii=True),flush=True)
  assert r.status_code==200,result
  return result
 code_result=request('code',[code],'解释代码用途、输入输出与关键行，关联截图可见的41到46行；为关键行添加简短注释，并指出潜在问题。')
 assert code_result['notes'] and all(n['lineLabel'].startswith('第 ') for n in code_result['notes'])
 assert all(n['locationSource']=='ocr' and n['pageId']==code['id'] for n in code_result['notes'])
 paper_prompt='比较两页学生作答的共性错误，逐页引用原作答证据，分别添加简短注释，不改写学生答案。'
 paper_result=request('paper',papers,paper_prompt)
 assert {n['pageId'] for n in paper_result['notes']}=={p['id'] for p in papers}
 practice=request('paper',papers,'根据刚才确认的共同错误出两道独立练习，将题目、答案和解析分开，本次不新增或修改图片注释。',[
  {'role':'user','text':paper_prompt},{'role':'assistant','text':paper_result['answer'][:10000]}])
 assert practice['notes']==[] and len(practice['answer'])>40
 record['passed']=True;save()
 print(json.dumps({'passed':True,'codeLabels':[n['lineLabel'] for n in code_result['notes']],
  'paperPages':len(paper_result['pages']),'practicePreservesAnnotations':True},ensure_ascii=True),flush=True)
