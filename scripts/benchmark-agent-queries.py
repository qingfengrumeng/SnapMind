"""Reproducible, real-model query benchmark with generated images and stage timings.

No microphone, personal screenshot or new conversation is used. Reports contain
test queries, validated tool results (without image bytes), and measured timings.
"""
import argparse
import asyncio
import json
import math
import sys
import time
from datetime import datetime,timezone
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from fastapi import HTTPException
from backend.app import main
from backend.app.agent import run_agent
from backend.app.agent.tools import REGISTRY
from backend.app.agent.harness import observation
from backend.app.session_memory import CONTEXT
from backend.app.image_tools import png_data,image_from_data


CASES=[
    ('chat','你好，用一句话告诉我你可以帮我做什么，不要修改截图。',[],[],{}),
    ('ocr','提取截图中的全部文字，保留原文和换行。',['ocr','offline'],[],{}),
    ('table','把截图中商品、数量、单价的表格提取出来，方便复制到 Excel。',['table'],[],{}),
    ('entities','提取截图里的邮箱地址，一句话回复。',['entities'],[],{}),
    ('translate','将截图中的英文原位翻译成简体中文，完成后一句话回复。',['translate'],[],{}),
    ('highlight','帮我高亮截图里的 Keyboard，一句话回复。',['highlight'],[],{}),
    ('heal','将截图里的 Keyboard 涂抹掉，修补背景，不要打马赛克。',['heal'],['heal'],{}),
    ('mosaic','给截图里的 Keyboard 打马赛克，不要擦除。',['mosaic'],['mosaic'],{}),
    ('heal_correction','我要的是涂抹掉截图里的 Keyboard，不是打马赛克。',['heal'],['heal'],{}),
    ('crop','把截图裁剪成 [20,20,440,280] 这个区域，一句话回复。',['crop'],[],{}),
    ('crop_title','把标题那一行裁剪出来。',['offline','crop'],['offline','crop'],{}),
    ('multi_step','先裁剪 [20,20,440,280]，再在裁剪后的图片 [10,10,180,65] 位置画一个矩形，完成后一句话回复。',['crop','draw'],['crop','annotate'],{}),
    ('undo','先裁剪 [20,20,440,280]，然后撤销这次裁剪，完成后一句话回复。',['crop','undo'],['crop','restore_image'],{}),
    ('memory_followup','按我上一条消息提供的坐标裁剪截图，一句话回复。',['crop'],[],{'history':[{'role':'user','text':'裁剪坐标是 [20,20,440,280]，等我下一条消息再执行。'}]}),
    ('ambiguous','帮我处理一下这张截图。',[],[],{'no_mutation':True}),
    ('missing_image','我还没有给你截图，请把截图内容原位翻译成中文。',[],[],{'no_image':True,'no_mutation':True}),
    ('preference_override','Please introduce your screenshot capabilities in one English sentence. Do not edit the image.',[],[],{'no_mutation':True,'memories':'用户偏好：默认使用简体中文回答。'}),
]


def fixture():
    image=Image.new('RGB',(760,430),'white');draw=ImageDraw.Draw(image)
    face=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',25)
    draw.text((30,24),'Order Summary',font=face,fill='black')
    for y,row in [(94,['Product','Quantity','Price']),(150,['Keyboard','2','100.00']),(206,['Mouse','1','50.00'])]:
        for x,text in zip([30,330,520],row):draw.text((x,y),text,font=face,fill='black')
    for y in [84,140,196,252]:draw.line((20,y,720,y),fill='#888888',width=1)
    draw.text((30,286),'Contact: support@example.com',font=face,fill='black')
    draw.text((30,348),'Hello SnapMind',font=face,fill='black')
    return image


async def benchmark_case(case,image,profile,index,repeat):
    name,query,expected_tools,expected_actions,options=case
    asset=SimpleNamespace(id='benchmark-image',name='Generated order table',data=png_data(image),width=image.width,height=image.height,scenario='custom')
    history=[SimpleNamespace(**m) for m in options.get('history',[])]
    assets=[] if options.get('no_image') else [asset]
    started=time.perf_counter();model_calls=[];tool_calls=[];trace=[];events=[];first_chunk=None;active_tool=None
    policy=main.MEMORY.policy()
    token=CONTEXT.set({'policy':policy,'summary':'','memories':options.get('memories',''),'history':[{'role':m.role,'content':m.text} for m in history],'trace':lambda kind,payload:trace.append({'kind':kind,'payload':payload})})
    original_execute=REGISTRY.execute
    async def measured_model(*args,**kwargs):
        t=time.perf_counter();entry={'action':args[3],'stage':'tool' if active_tool else 'planning','tool':active_tool,'streaming':bool(kwargs.get('on_chunk')),'startSeconds':round(t-started,4)};model_calls.append(entry)
        try:
            response=await main.complete(*args,**kwargs)
            if entry['stage']=='planning':
                try:entry['decision']=json.loads(response['text'])
                except (ValueError,KeyError):entry['decision']='invalid JSON'
            return response
        finally:entry['seconds']=round(time.perf_counter()-t,4)
    async def measured_tool(name,*args,**kwargs):
        nonlocal active_tool
        active_tool=name
        t=time.perf_counter();entry={'name':name,'arguments':args[0].model_dump(exclude_none=True),'startSeconds':round(t-started,4)};tool_calls.append(entry)
        try:
            result=await original_execute(name,*args,**kwargs);entry['status']='success';return result
        except Exception as e:
            entry['status']='failed';entry['error']=str(e)[:400];raise
        finally:entry['seconds']=round(time.perf_counter()-t,4);active_tool=None
    async def event(data):
        nonlocal first_chunk
        if data['type']=='chunk' and first_chunk is None:first_chunk=time.perf_counter()-started
        events.append({'type':data['type'],'timeSeconds':round(time.perf_counter()-started,4),'phase':data.get('phase'),'tool':data.get('tool',data.get('name'))})
    REGISTRY.execute=measured_tool
    result=None;error=None
    try:
        result=await run_agent(profile,assets,asset.id if assets else None,query,history,[],[],main.DB,measured_model,main.locate,on_chunk=event)
    except Exception as e:error={'type':type(e).__name__,'status':e.status_code if isinstance(e,HTTPException) else None,'message':str(e)[:900]}
    finally:REGISTRY.execute=original_execute;CONTEXT.reset(token)
    total=time.perf_counter()-started;steps=result.get('steps',[]) if result else []
    actions=[r['action'] for r in steps];successful=[t['name'] for t in tool_calls if t['status']=='success'];checks={}
    checks['completed']=result is not None
    checks['nonempty_answer']=bool(result and result.get('answer','').strip())
    checks['intent_tools']=all(tool in successful for tool in expected_tools) if name!='ocr' else bool(set(expected_tools)&set(successful))
    if expected_actions:checks['operation_order']=actions==expected_actions
    if options.get('no_mutation'):checks['no_unrequested_edit']=not any(REGISTRY.get(t).mutates for t in successful)
    if name=='chat':checks['no_edit']=not actions
    if name=='ocr':checks['visible_text']='keyboard' in ' '.join(s.get('answer','') for s in steps).lower()
    if name=='entities':checks['correct_email']='support@example.com' in json.dumps(steps)
    if name=='table':
        tables=[t for s in steps if s['action']=='table' for t in s['payload'].get('tables',[])]
        cells=[c for t in tables for row in t['rows'] for c in row]
        checks['table_data']=all(v in cells for v in ['Keyboard','Mouse','100.00','50.00'])
    if name=='translate':checks['translated_lines']=any(s['payload'].get('lines') for s in steps if s['action']=='translate')
    if name in ('crop','memory_followup','multi_step'):
        crops=[s for s in steps if s['action']=='crop'];checks['crop_pixels']=bool(crops and image_from_data(crops[0]['payload']['data']).size==(420,260))
    if name=='undo':checks['restored_pixels']=bool(steps and image_from_data(steps[-1]['payload']['data']).size==image.size)
    if name=='memory_followup':checks['short_term_used']=bool(result and result['agent']['memory']['shortTermTurns']==1)
    if name=='preference_override':
        import re
        checks['current_query_overrides_preference']=bool(result and not re.search(r'[\u4e00-\u9fff]',result['answer']))
        checks['long_term_injected']=bool(result and result['agent']['memory']['hasLongTermPreferences'])
    planning=[c for c in model_calls if c['stage']=='planning']
    row={'id':name,'repeat':repeat,'query':query,'passed':all(checks.values()),'checks':checks,'error':error,
         'timing':{'totalSeconds':round(total,4),'firstTextSeconds':round(first_chunk,4) if first_chunk is not None else None,'firstDecisionSeconds':planning[0]['seconds'] if planning else None,'planningSeconds':round(sum(c['seconds'] for c in planning),4),'toolSeconds':round(sum(c['seconds'] for c in tool_calls if c['name']!='answer'),4),'answerSeconds':round(sum(c['seconds'] for c in tool_calls if c['name']=='answer'),4)},
         'actualTools':[c['name'] for c in tool_calls],'actions':actions,'modelCalls':model_calls,'toolCalls':tool_calls,'events':events,
         'validationRetries':sum(t['kind']=='agent_validation' for t in trace),'toolErrors':sum(t['kind']=='agent_tool_error' for t in trace),
         'output':{'answer':result['answer'],'steps':[observation(s,24000) for s in steps],'agent':result['agent']} if result else None}
    print(json.dumps({'case':name,'repeat':repeat,'passed':row['passed'],'timing':row['timing'],'tools':row['actualTools'],'error':error},ensure_ascii=False),flush=True)
    return row


def write_reports(folder,rows,model,elapsed):
    folder.mkdir(parents=True,exist_ok=True)
    report={'createdAt':datetime.now(timezone.utc).isoformat(),'model':model,'mode':'real configured LLM and tools; generated screenshot; no saved sessions','suiteSeconds':round(elapsed,3),'passed':sum(r['passed'] for r in rows),'total':len(rows),'cases':rows}
    (folder/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    lines=['# Agent Query 测试与耗时报告','',f"模型：{model}。使用合成商品表截图与真实模型、真实工具；不使用麦克风或用户截图，不保存测试会话。",'',f"通过 {report['passed']}/{len(rows)}；整套云端测试耗时 {elapsed:.2f} 秒。",'',
           '首次决策 = 第一次规划模型调用耗时；首字 = 用户可见的第一个文本片段到达时间；工具 = 非 answer 工具累计耗时；总耗时包括规划、执行和最终回复。嵌套模型耗时与工具耗时有重叠，不能再次相加。单次测量不代表稳定 P95。','',
           '| Query | 结果 | 实际工具 | 首次决策(s) | 首字(s) | 工具(s) | 回复(s) | 总耗时(s) |',
           '|---|---|---|---:|---:|---:|---:|---:|']
    for r in rows:
        t=r['timing'];fmt=lambda v:'—' if v is None else f'{v:.2f}'
        lines.append(f"| {r['id']}#{r['repeat']} | {'通过' if r['passed'] else '失败'} | {' → '.join(r['actualTools'])} | {fmt(t['firstDecisionSeconds'])} | {fmt(t['firstTextSeconds'])} | {fmt(t['toolSeconds'])} | {fmt(t['answerSeconds'])} | {fmt(t['totalSeconds'])} |")
    lines+=['','## 查询与结果校验','']
    for r in rows:
        lines.extend([f"### {r['id']}#{r['repeat']}",'',r['query'],'',f"校验：`{json.dumps(r['checks'],ensure_ascii=False)}`。Schema 修复 {r['validationRetries']} 次；工具错误 {r['toolErrors']} 次。",''])
        if r['error']:lines.extend([f"错误：{r['error']['message']}",''])
    (folder/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')


async def main_run(args):
    if not args.cloud:raise RuntimeError('需要 --cloud 来确认使用现有模型运行真实测试')
    profile=main.get_active_profile(main.DB)
    if not profile:raise RuntimeError('No active LLM profile')
    selected=[c for c in CASES if not args.cases or c[0] in args.cases.split(',')]
    if not selected:raise RuntimeError('No matching test cases')
    image=fixture();folder=Path(args.output);folder.mkdir(parents=True,exist_ok=True);image.save(folder/'generated-input.png')
    rows=[];start=time.perf_counter()
    for repeat in range(1,args.repeat+1):
        for case in selected:
            rows.append(await benchmark_case(case,image,profile,len(rows),repeat));write_reports(folder,rows,profile['model'],time.perf_counter()-start)
    print(json.dumps({'report':str(folder/'REPORT.md'),'passed':sum(r['passed'] for r in rows),'total':len(rows),'suiteSeconds':round(time.perf_counter()-start,2)},ensure_ascii=False),flush=True)
    if not all(r['passed'] for r in rows):raise SystemExit(1)


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--cloud',action='store_true');parser.add_argument('--cases');parser.add_argument('--repeat',type=int,choices=range(1,4),default=1);parser.add_argument('--output',default='artifacts/agent-query-tests/live')
    asyncio.run(main_run(parser.parse_args()))
