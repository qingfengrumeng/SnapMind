import asyncio
import json
from types import SimpleNamespace
from PIL import Image,ImageDraw,ImageFont
import pytest
from fastapi import HTTPException
from backend.app.ocr_recovery import text_strips,strip_atlas,merge_atlas,pending_regions
from backend.app.image_tools import png_data
from backend.app.inline_translation import TranslationLine,translate_lines
from backend.app.agent.tools import REGISTRY
from backend.app.agent.state import AgentState
from backend.app.text_target import resolve_text_target

def test_pixel_regions_preserve_missing_table_header_without_model_geometry():
    image=Image.new('RGB',(400,170),'white');draw=ImageDraw.Draw(image)
    font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',28)
    draw.text((20,20),'商品',font=font,fill='black');draw.text((220,20),'数量',font=font,fill='black')
    draw.line((10,75,390,75),fill='#999')
    strips=text_strips(image)
    assert len(strips)==2
    known={'regions':[{'id':'text-1','text':'商品','bbox':strips[0]['bbox']}]}
    pending=pending_regions(png_data(image),known)
    assert len(pending)==1 and pending[0]['recognitionRequired'] and pending[0]['bbox']==strips[1]['bbox']
    assert strip_atlas(strips)[0][0].height>image.height

def test_recovery_preserves_numeric_and_email_punctuation():
    document={'regions':[{'text':'100.00','bbox':[1,1,40,20]},{'text':'a@b.com','bbox':[1,31,80,50]}]}
    mapping=[{'bbox':[0,0,50,25],'atlasBbox':[0,0,100,50]}, {'bbox':[0,30,90,55],'atlasBbox':[0,60,180,110]}]
    recognized={'lines':[{'words':[{'text':'100,00','bbox':[2,2,80,40]}]},{'words':[{'text':'a@b com','bbox':[2,62,160,100]}]}]}
    assert merge_atlas(document,[mapping],[recognized])['regions']==document['regions']

def test_missing_header_read_and_translated_in_same_request():
    asset=SimpleNamespace(width=200,height=100)
    line=TranslationLine(id='text-1',text='',bbox=[20,20,80,50],recognitionRequired=True)
    calls=[]
    async def complete(profile,session,assets,action,prompt,path):
        calls.append(prompt)
        return {'text':json.dumps({'lines':[{'id':'text-1','sourceText':'数量','text':'Quantity'}]})}
    result=asyncio.run(translate_lines({'vision':True},asset,[line],'en',None,complete))
    assert len(calls)==1 and result['lines'][0]['sourceText']=='数量' and result['lines'][0]['text']=='Quantity'
    assert result['lines'][0]['bbox']==[20,20,80,50]
    async def missing(*args):return {'text':'{"lines":[{"id":"text-1","text":"Quantity"}]}'}
    with pytest.raises(HTTPException):asyncio.run(translate_lines({'vision':True},asset,[line],'en',None,missing))
    with pytest.raises(HTTPException):asyncio.run(translate_lines({'vision':False},asset,[line],'en',None,complete))

def test_failed_matching_reuses_ocr_and_image_change_invalidates_cache():
    asset=SimpleNamespace(id='image',width=120,height=80,data=png_data(Image.new('RGB',(120,80),'white')))
    state=AgentState([asset],'image','高亮标题',[],[],[],'zh-CN');calls=[]
    async def locate(path,data,**kwargs):
        calls.append(data);return {'regions':[{'text':'订单汇总','bbox':[10,10,90,35]}]}
    async def complete(*args):raise AssertionError('Matching does not use LLM')
    async def run():
        for target in ['不存在','订单汇总']:
            args=REGISTRY.get('highlight').schema(imageId='image',targetText=target)
            try:await REGISTRY.execute('highlight',args,state,{},complete,locate,None)
            except HTTPException:pass
        assert len(calls)==1
        state.replace(asset,png_data(Image.new('RGB',(120,80),'black')))
        await REGISTRY.execute('highlight',args,state,{},complete,locate,None)
        assert len(calls)==2
    asyncio.run(run())

def test_visual_spelling_repair_keeps_ocr_coordinates_and_rejects_ambiguity():
    location={'regions':[{'text':'订 单 氵 匚 总','bbox':[10,10,110,40]}]}
    async def complete(profile,session,assets,action,prompt,path):
        return {'text':json.dumps({'matches':[{'id':'line-0','sourceText':'订单汇总'}]})}
    target=asyncio.run(resolve_text_target({'vision':True},object(),'订单汇总',location,None,complete))
    assert target['text']=='订单汇总' and target['bbox']==location['regions'][0]['bbox']
    async def invented(*args):return {'text':json.dumps({'matches':[{'id':'line-9','sourceText':'订单汇总'}]})}
    with pytest.raises(HTTPException):asyncio.run(resolve_text_target({'vision':True},object(),'订单汇总',location,None,invented))
    duplicate={'regions':[{'text':'订单汇总','bbox':[0,0,20,10]},{'text':'订单汇总','bbox':[30,0,50,10]}]}
    async def forbidden(*args):raise AssertionError('Repeated exact labels cannot be disambiguated by guessing')
    assert asyncio.run(resolve_text_target({'vision':True},object(),'订单汇总',duplicate,None,forbidden)) is None
