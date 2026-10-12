"""Configured cloud-model smoke test; uses only a generated screenshot."""
import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from backend.app import main
from backend.app.agent import run_agent
from backend.app.image_tools import png_data


async def verify():
    if '--cloud' not in sys.argv:raise RuntimeError('Pass --cloud to call the configured model with a generated image')
    image=Image.new('RGB',(600,140),'white')
    ImageDraw.Draw(image).text((24,40),'Hello SnapMind',font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',32),fill='black')
    asset=SimpleNamespace(id='generated-agent-image',name='Generated image',data=png_data(image),width=600,height=140,scenario='custom')
    events=[]
    async def event(data):events.append(data['type'])
    result=await run_agent(main.get_active_profile(main.DB),[asset],asset.id,'请帮我将截图内容原位翻译成简体中文。',[],[],[],main.DB,main.complete,main.locate,on_chunk=event)
    assert any(step['action']=='translate' for step in result['steps']),result.get('agent')
    translated=next(step for step in result['steps'] if step['action']=='translate')
    assert translated['payload']['lines'] and result['answer']
    assert 'chunk' in events and 'tool_result' in events
    print(json.dumps({'status':'PASS','actions':[s['action'] for s in result['steps']],'replyChars':len(result['answer']),'textChunks':events.count('chunk'),'toolCalls':result['agent']['toolCalls']}))


if __name__=='__main__':asyncio.run(verify())
