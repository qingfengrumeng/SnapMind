import asyncio
import io
import json
from types import SimpleNamespace
import numpy as np
import pytest
from PIL import Image,ImageDraw
from fastapi import HTTPException
from backend.app.image_tools import png_data,image_from_data,repair,decode_codes,screen_entities,safe_entity_url
from backend.app.image_conversation import converse,direct_intent

def asset(width=240,height=140):
    image=Image.new('RGB',(width,height),'white')
    ImageDraw.Draw(image).text((25,35),'Example text',fill='black')
    return SimpleNamespace(id='test-image',name='Generated example',data=png_data(image),width=width,height=height)

@pytest.mark.parametrize('prompt,action',[('提取文字','ocr'),('翻译成英文','translate'),('识别二维码','qr'),('提取表格到 Excel','table'),('离线识别文字','offline'),('检查试卷作答','chat'),('添加一个箭头标注','annotate'),('理解这段代码','chat'),('注释这篇论文','chat'),('提取公式','chat'),('整理图片笔记','chat'),('解释这张截图','chat')])
def test_explicit_intent(prompt,action):
    assert direct_intent(prompt).action==action

@pytest.mark.parametrize('prompt',['为什么需要 OCR','如何进行翻译','这个功能是什么'])
def test_question_is_not_execution(prompt):
    assert direct_intent(prompt) is None

def test_repair_only_changes_mask_and_lift_transparency():
    a=asset();mask=Image.new('L',(a.width,a.height),0);ImageDraw.Draw(mask).rectangle((20,25,125,65),fill=255)
    output=repair(a.data,png_data(mask),True)
    actual=np.asarray(image_from_data(output['data']));source=np.asarray(image_from_data(a.data));m=np.asarray(mask)
    assert np.array_equal(actual[m==0],source[m==0])
    assert actual[m>0].mean()>245
    layer=Image.open(io.BytesIO(__import__('base64').b64decode(output['layer']['data'].split(',')[1])))
    assert layer.mode=='RGBA' and np.asarray(layer)[:,:,3].max()>240 and np.asarray(layer)[:,:,3].min()==0

def test_repair_rejects_wrong_size_and_full_mask():
    a=asset()
    for m in [Image.new('L',(4,4),255),Image.new('L',(a.width,a.height),255)]:
        with pytest.raises(HTTPException):repair(a.data,png_data(m))

def test_qr_real_round_trip_and_blank():
    import sys
    from pathlib import Path
    sys.path.append(str(Path('backend/vendor').resolve()))
    import zxingcpp
    import cv2
    encoded=cv2.QRCodeEncoder_create().encode('https://example.com/snapmind')
    image=Image.fromarray(encoded).resize((encoded.shape[1]*6,encoded.shape[0]*6),Image.Resampling.NEAREST)
    result=decode_codes(png_data(image))
    assert len(result['codes'])==1 and result['codes'][0]['url']=='https://example.com/snapmind'
    assert not decode_codes(png_data(Image.new('RGB',(200,120),'white')))['codes']

def test_barcode_real_round_trip():
    import sys
    sys.path.append('backend/vendor')
    import zxingcpp
    from reportlab.graphics.barcode.code128 import Code128
    code=Code128('SNAPMIND-001');code._calculate()
    widths=[ord(c.upper())-ord('A')+1 for c in code.decomposed]
    image=Image.new('RGB',(sum(widths)*3+60,110),'white');draw=ImageDraw.Draw(image);x=30
    for c,w in zip(code.decomposed,widths):
        if c.isupper():draw.rectangle((x,10,x+w*3-1,100),fill='black')
        x+=w*3
    result=decode_codes(png_data(image))
    assert result['codes'][0]['text']=='SNAPMIND-001' and result['codes'][0]['url'] is None

def test_entities_schemes_and_deduplication():
    rows=[{'text':'https://example.com/path mail@example.com 13800138000','bbox':[10,10,200,40]}]*2
    result=screen_entities({'regions':rows,'width':240,'height':140})
    assert [x['kind'] for x in result['entities']]==['url','email','phone']
    for url in ['javascript:alert(1)','file:///C:/x','https://user:password@example.com','data:text/html,x']:
        assert safe_entity_url(url) is None

def call(prompt='提取文字',history=None,action=None,reply='Actual text',assets=None,selected='test-image',location=None):
    calls=[]
    async def complete(profile,session,images,kind,text,path):
        calls.append((kind,text,images,session.messages))
        return {'text':reply,'kind':'text'}
    async def locate(path,data,**kwargs):
        return location or {'width':240,'height':140,'mode':'test','regions':[]}
    result=asyncio.run(converse({'vision':True},assets if assets is not None else [asset()],selected,prompt,history or [],[],[],None,complete,locate,action))
    return result,calls

def test_transcription_only_real_text_and_history():
    history=[SimpleNamespace(role='user',text='Earlier question'),SimpleNamespace(role='assistant',text='Earlier answer')]
    response,calls=call(history=history,reply='[无法辨认]Actual\n  text')
    assert response['answer']=='Actual\n  text'
    assert len(calls)==1 and calls[0][0]=='ocr' and len(calls[0][3])==2
    assert '不输出占位符' in calls[0][1]

def test_wrong_picture_rejected_before_model():
    with pytest.raises(HTTPException,match='400'):call(selected='other-image')

def test_bad_image_metadata_rejected_before_model():
    a=asset();a.width=241
    with pytest.raises(HTTPException):call(assets=[a])

def test_empty_chat_allows_plain_question_without_image():
    response,calls=call(prompt='解释一下概念',action='chat',assets=[],selected=None)
    assert response['assetId'] is None and calls[0][2]==[]

def test_multi_image_chat_preserves_all_references():
    second=asset();second.id='second'
    response,calls=call(prompt='比较两张图',action='chat',assets=[asset(),second])
    assert len(calls[0][2])==2

@pytest.mark.parametrize('prompt',['检查试卷作答','理解这段代码','注释这篇论文','提取公式','整理图片笔记','解释这张截图'])
def test_content_requests_use_normal_dialogue_and_keep_all_images(prompt):
    images=[asset(),asset()];images[1].id='second'
    history=[SimpleNamespace(role='user',text='Earlier request')]
    response,calls=call(prompt=prompt,assets=images,history=history,reply='Normal conversational answer')
    assert response['action']=='chat' and response['payload']=={'text':'Normal conversational answer'}
    assert len(calls)==1 and calls[0][0]=='chat' and len(calls[0][2])==2
    assert [(t.role,t.text) for t in calls[0][3]]==[(t.role,t.text) for t in history]

@pytest.mark.parametrize('action',['note','explain','code','paper','exam','formula'])
def test_old_action_requests_become_normal_dialogue(action):
    response,calls=call(prompt='Follow-up request',action=action,reply='Normal conversational answer')
    assert response['action']=='chat' and calls[0][0]=='chat' and len(calls)==1

def test_table_uses_real_structured_service():
    result,calls=call(prompt='提取表格',reply='{"tables":[{"title":"Numbers","rows":[["Code","Value"],["001","0"]]}]}')
    assert result['payload']['tables'][0]['rows'][1]==['001','0'] and calls[0][0]=='table-json'

def test_unmatched_text_never_paints_guessed_bbox():
    with pytest.raises(HTTPException):call(prompt='高亮不存在的文字',reply='{"action":"highlight","targetText":"Missing","language":"zh-CN","bbox":[0,0,40,40]}',location={'regions':[{'text':'Real','bbox':[20,30,80,60]}]})

def test_highlight_geometry_comes_from_ocr():
    response,calls=call(prompt='高亮 Real',reply='{"action":"highlight","targetText":"Real","language":"zh-CN","bbox":[0,0,40,40]}',location={'regions':[{'text':'Real','bbox':[20,30,80,60]}]})
    assert response['payload']['bbox']==[20,30,80,60]

def test_annotation_followup_serializes_real_history():
    history=[SimpleNamespace(role='user',text='Previous text'),SimpleNamespace(role='assistant',text='Previous answer')]
    response,calls=call(prompt='给文字添加箭头标注',action='annotate',history=history,reply='{"answer":"Added","annotations":[{"operation":"add","kind":"arrow","targetIds":["text-1"],"targetText":"Real"}]}',location={'width':240,'height':140,'mode':'test','regions':[{'id':'text-1','text':'Real','bbox':[20,30,80,60],'granularity':'line'}]})
    assert response['payload']['annotations'][0]['kind']=='arrow'
    assert response['payload']['annotations'][0]['bbox']==[20,30,80,60]

def test_crop_never_uses_model_invented_coordinates():
    with pytest.raises(HTTPException):call(prompt='裁剪一下图片',reply='{"action":"crop","targetText":"","language":"zh-CN","bbox":[0,0,40,40]}')
    result,_=call(prompt='裁剪图片 [10,20,110,100]',reply='{"action":"crop","targetText":"","language":"zh-CN","bbox":[0,0,40,40]}')
    assert result['payload']['width']==100 and result['payload']['height']==80
