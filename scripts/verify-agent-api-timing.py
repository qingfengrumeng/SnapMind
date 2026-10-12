"""Measure real HTTP/SSE latency using generated input and transient queries."""
import asyncio
import base64
import io
import json
import sys
import time
from pathlib import Path
import httpx
from PIL import Image,ImageDraw,ImageFont


async def run():
    if '--cloud' not in sys.argv:raise RuntimeError('Pass --cloud to test configured cloud models through the local API')
    image=Image.new('RGB',(600,140),'white')
    ImageDraw.Draw(image).text((24,40),'Hello SnapMind',font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',32),fill='black')
    buffer=io.BytesIO();image.save(buffer,format='PNG')
    asset={'id':'api-timing-generated','name':'Generated input','data':'data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode(),'width':600,'height':140,'scenario':'custom'}
    rows=[]
    async with httpx.AsyncClient(timeout=260) as client:
        for name,query,expected in [('ocr','提取截图全部文字。','ocr'),('crop','裁剪截图 [20,20,440,120]，只需一句话回复。','crop')]:
            start=time.perf_counter();events=[];result=None;headers_time=None;first_text=None;error=None
            async with client.stream('POST','http://127.0.0.1:8776/api/capture/conversation?stream=true',json={'assets':[asset],'selectedId':asset['id'],'prompt':query,'history':[],'existing':[]}) as response:
                headers_time=time.perf_counter()-start
                async for line in response.aiter_lines():
                    if not line.startswith('data: '):continue
                    event=json.loads(line[6:]);stamp=time.perf_counter()-start
                    events.append({'type':event['type'],'phase':event.get('phase'),'tool':event.get('name',event.get('tool')),'seconds':round(stamp,4)})
                    if event['type']=='chunk' and first_text is None:first_text=stamp
                    if event['type']=='result':result=event['result']
                    if event['type']=='error':error=event
            total=time.perf_counter()-start
            actions=[s['action'] for s in result.get('steps',[])] if result else []
            passed=bool(result and expected in actions and first_text is not None and not error)
            if name=='ocr':passed=passed and 'Hello' in json.dumps(result)
            if name=='crop':passed=passed and any(s['payload']['width']==420 and s['payload']['height']==100 for s in result.get('steps',[]) if s['action']=='crop')
            row={'query':query,'case':name,'passed':passed,'status':response.status_code,'contentType':response.headers.get('content-type'),'headersSeconds':round(headers_time,4),'firstTextSeconds':round(first_text,4) if first_text else None,'totalSeconds':round(total,4),'events':events,'actions':actions,'error':error}
            rows.append(row);print(json.dumps(row,ensure_ascii=False),flush=True)
    folder=Path('artifacts/agent-query-tests');folder.mkdir(parents=True,exist_ok=True)
    (folder/'api-timing.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2),encoding='utf-8')
    if not all(row['passed'] for row in rows):raise RuntimeError('An HTTP/SSE test failed; see api-timing.json')


if __name__=='__main__':asyncio.run(run())
