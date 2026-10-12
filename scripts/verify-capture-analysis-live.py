"""Opt-in cloud checks; upload only generated fixtures, never the desktop."""
import base64
import io
import json
from pathlib import Path
import sys
import time
import httpx
from PIL import Image,ImageDraw,ImageFont

ROOT=Path(__file__).resolve().parents[1]
if '--live' not in sys.argv:raise SystemExit('Pass --live to send generated fixtures to the configured model.')
out=ROOT/'artifacts/capture-analysis-live';out.mkdir(parents=True,exist_ok=True)
font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',24)
table=Image.new('RGB',(900,390),'white');d=ImageDraw.Draw(table)
rows=[['Item','Qty','Price'],['Apples','12','3.50'],['Oranges','8','4.20'],['Pears','','5.00']]
xs=[40,360,560,850];ys=[65,125,185,245,305]
for x in xs:d.line((x,ys[0],x,ys[-1]),fill='#9b8daf',width=2)
for y in ys:d.line((xs[0],y,xs[-1],y),fill='#9b8daf',width=2)
for ri,row in enumerate(rows):
    for ci,text in enumerate(row):d.text((xs[ci]+14,ys[ri]+15),text,font=font,fill='#30263c')

# Deliberately simple illustrated traffic, not a photographic detection benchmark.
traffic=Image.new('RGB',(960,620),'#70a375');d=ImageDraw.Draw(traffic)
d.rectangle((30,20,930,600),fill='#53596a')
for x in [320,640]:
    for y in range(40,610,90):d.rectangle((x-3,y,x+3,y+50),fill='#fff7cc')
boxes=[[120,70,255,300],[430,350,565,580],[730,90,865,320]]
for box,color in zip(boxes,['#f7cc55','#e95d5d','#83c8ff']):
    x1,y1,x2,y2=box
    for tx in [x1-6,x2-5]:
        d.rounded_rectangle((tx,y1+35,tx+11,y1+85),radius=4,fill='#191b21')
        d.rounded_rectangle((tx,y2-85,tx+11,y2-35),radius=4,fill='#191b21')
    d.rounded_rectangle(tuple(box),radius=22,fill=color,outline='#262a35',width=3)
    d.rounded_rectangle((x1+13,y1+46,x2-13,y1+93),radius=7,fill='#36465f',outline='#aecbe2',width=2)
    d.rounded_rectangle((x1+13,y2-78,x2-13,y2-40),radius=7,fill='#36465f')
    d.rectangle((x1+10,y1+12,x1+30,y1+19),fill='#fff4ba');d.rectangle((x2-30,y1+12,x2-10,y1+19),fill='#fff4ba')
    d.line((x1+14,y1+112,x1+14,y2-97),fill='#262a35',width=2);d.line((x2-14,y1+112,x2-14,y2-97),fill='#262a35',width=2)

def asset(image,name):
    image.save(out/(name+'.png'));b=io.BytesIO();image.save(b,format='PNG')
    return {'id':'analysis-live-'+name,'name':'Synthetic '+name,'width':image.width,'height':image.height,'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()}

records={}
with httpx.Client(timeout=160,trust_env=False) as client:
    for name,image,action,target in [('table',table,'table','all'),('objects',traffic,'detect','vehicles')]:
        value=asset(image,name);started=time.perf_counter()
        r=client.post('http://127.0.0.1:8776/api/capture/analyze',json={'asset':value,'action':action,'target':target})
        elapsed=round(time.perf_counter()-started,2)
        records[name]={'asset':value,'status':r.status_code,'seconds':elapsed,'result':r.json()}
        if r.status_code!=200:print(json.dumps({'fixture':name,'status':r.status_code,'seconds':elapsed}),flush=True);continue
        if action=='table':
            tables=r.json()['tables'];actual=tables[0]['rows'] if tables else []
            correct=sum(ri<len(actual) and ci<len(actual[ri]) and actual[ri][ci]==text for ri,row in enumerate(rows) for ci,text in enumerate(row))
            records[name]['evaluation']={'exactCells':correct,'totalCells':12,'rowsAndColumns':len(actual)==4 and all(len(row)==3 for row in actual)}
        else:
            objects=r.json()['objects'];matches=[]
            def iou(a,b):
                intersection=max(0,min(a[2],b[2])-max(a[0],b[0]))*max(0,min(a[3],b[3])-max(a[1],b[1]))
                return intersection/((a[2]-a[0])*(a[3]-a[1])+(b[2]-b[0])*(b[3]-b[1])-intersection)
            for box in boxes:matches.append(round(max((iou(box,o['bbox']) for o in objects),default=0),3))
            records[name]['evaluation']={'visibleCars':3,'returnedObjects':len(objects),'bestIoUPerCar':matches,'fixtureType':'simple illustration; not a photographic accuracy benchmark'}
        print(json.dumps({'fixture':name,'seconds':elapsed,'evaluation':records[name]['evaluation']},ensure_ascii=True),flush=True)
(out/'results.json').write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
if any(record['status']!=200 for record in records.values()):raise SystemExit('At least one live request failed; inspect the recorded status.')
