import asyncio
import base64
import importlib
import io
import json
import sys
from types import SimpleNamespace
import pytest
from PIL import Image,ImageDraw,ImageFont
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app import ocr_locator
from backend.app.inline_translation import TranslationLine,translate_lines,translations

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True,'model':'synthetic'})
    with TestClient(module.app) as c: yield c,module

def asset():
    b=io.BytesIO();Image.new('RGB',(200,120),'white').save(b,format='PNG')
    return {'id':'fixture','name':'synthetic.png','width':200,'height':120,'scenario':'custom','data':'data:image/png;base64,'+base64.b64encode(b.getvalue()).decode()}

def lines():
    return [{'id':'text-1','text':'Left column','bbox':[10,10,85,30]},
            {'id':'text-2','text':'Right column','bbox':[110,10,195,30]}]

def test_fixed_id_translation_ignores_model_geometry_and_preserves_columns(client,monkeypatch):
    c,module=client
    async def complete(profile,session,assets,action,prompt,path):
        assert action=='translate' and len(assets)==1 and not session.messages
        assert all(s in prompt for s in ['English','不要合并行','不输出坐标','根据图片校正'])
        # Reverse response order and supply fabricated coordinates: IDs, not model geometry, control placement.
        return {'text':json.dumps({'lines':[{'id':'text-2','text':'Translated right','bbox':[0,0,1,1]},{'id':'text-1','text':'Translated left\ncontinued'}]})}
    monkeypatch.setattr(module,'complete',complete)
    response=c.post('/api/capture/translate-inline',json={'asset':asset(),'lines':lines(),'language':'en'})
    assert response.status_code==200
    result=response.json()
    assert result['coordinateSpace']=='image-pixels' and result['width']==200
    assert [r['id'] for r in result['lines']]==['text-1','text-2']
    assert result['lines'][0]['bbox']==lines()[0]['bbox']
    assert result['lines'][0]['text']=='Translated left continued'
    assert result['lines'][1]['bbox']==lines()[1]['bbox']
    assert c.get('/api/sessions').json()==[]

@pytest.mark.parametrize('values',[
    [{'id':'text-1','text':'A'}],
    [{'id':'text-1','text':'A'},{'id':'text-1','text':'B'}],
    [{'id':'text-1','text':'A'},{'id':'invented','text':'B'}],
    [{'id':'text-1','text':''},{'id':'text-2','text':'B'}],
])
def test_incomplete_or_duplicate_model_reply_is_not_applied(values):
    with pytest.raises(HTTPException) as e: translations(json.dumps({'lines':values}),{'text-1','text-2'})
    assert e.value.status_code==502

def test_code_fence_json_and_request_validation(client,monkeypatch):
    assert translations('```json\n{"lines":[{"id":"text-1","text":"A"}]}\n```',{'text-1'})=={'text-1':'A'}
    c,module=client
    async def forbidden(*_): raise AssertionError('Invalid lines must not cause model calls')
    monkeypatch.setattr(module,'complete',forbidden)
    for values in [lines()+[lines()[0]],lines()[:1]+[dict(lines()[1],bbox=[0,0,999,40])]]:
        assert c.post('/api/capture/translate-inline',json={'asset':asset(),'lines':values}).status_code==400
    assert c.post('/api/capture/translate-inline',json={'asset':asset(),'lines':[dict(lines()[0],bbox=[20,10,10,30])]}).status_code==422
    assert c.post('/api/capture/translate-inline',json={'asset':asset(),'lines':[]}).json()['lines']==[]
    monkeypatch.setattr(module,'get_active_profile',lambda _:None)
    assert c.post('/api/capture/translate-inline',json={'asset':asset(),'lines':lines()}).status_code==400

def test_text_only_profile_and_batched_translation():
    called=[]
    async def complete(profile,session,assets,action,prompt,path):
        assert assets==[] and action=='chat'
        body=json.loads(prompt.split('\n',1)[1]);called.append(body['lines'])
        return {'text':json.dumps({'lines':[{'id':l['id'],'text':l['text']} for l in body['lines']]})}
    batch=[TranslationLine(id=f'text-{i+1}',text=str(i),bbox=[1,1,20,20]) for i in range(61)]
    result=asyncio.run(translate_lines({'vision':False},SimpleNamespace(width=200,height=120),batch,'zh-CN',None,complete))
    assert len(called)==2 and len(called[0])==60 and len(result['lines'])==61

def test_line_ocr_uses_structure_without_changing_saved_profile(client,monkeypatch):
    c,module=client
    config={'enabled':True,'model':'PaddleOCR-VL-1.6','dailyLimit':20000}
    monkeypatch.setattr(ocr_locator,'active_ocr',lambda _:config)
    monkeypatch.setattr(ocr_locator,'reserve',lambda *_:None)
    monkeypatch.setattr(ocr_locator,'usage_summary',lambda *_:{})
    async def recognize(chosen,data):
        assert chosen['model']=='PP-StructureV3'
        return {'text':'fixture','width':200,'height':120,'regions':[{'text':'fixture','bbox':[10,10,85,30],'granularity':'line','page':0}],'mode':'paddleocr','coordinateSpace':'image-pixels'}
    monkeypatch.setattr(ocr_locator,'recognize_paddle',recognize)
    r=c.post('/api/capture/locate',json={'asset':asset(),'granularity':'line'})
    assert r.status_code==200 and r.json()['model']=='PP-StructureV3'
    assert config['model']=='PaddleOCR-VL-1.6'

def test_block_only_result_degrades_to_local_lines(client,monkeypatch):
    c,module=client
    monkeypatch.setattr(ocr_locator,'active_ocr',lambda _: {'enabled':True,'model':'PP-StructureV3'})
    monkeypatch.setattr(ocr_locator,'reserve',lambda *_:None)
    monkeypatch.setattr(ocr_locator,'usage_summary',lambda *_:{})
    monkeypatch.setattr(ocr_locator,'pause_cloud',lambda *_:None)
    async def cloud(*_): return {'text':'block','width':200,'height':120,'regions':[{'text':'block','bbox':[5,5,190,100],'granularity':'block'}]}
    async def local(*_): return {'text':'local','width':200,'height':120,'regions':[{'text':'local','bbox':[10,10,80,30],'granularity':'line'}],'mode':'windows-ocr'}
    monkeypatch.setattr(ocr_locator,'recognize_paddle',cloud);monkeypatch.setattr(ocr_locator,'recognize_positions_async',local)
    r=c.post('/api/capture/locate',json={'asset':asset(),'granularity':'line'}).json()
    assert r['fallbackReason']=='block-only' and r['regions'][0]['granularity']=='line'

def test_flat_background_padding_refines_without_changing_text():
    image=Image.new('RGB',(240,100),'white');draw=ImageDraw.Draw(image)
    draw.text((20,20),'Translation',font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',24),fill='black',anchor='lt')
    b=io.BytesIO();image.save(b,format='PNG')
    mask=Image.new('L',image.size,0);ImageDraw.Draw(mask).text((20,20),'Translation',font=ImageFont.truetype('C:/Windows/Fonts/segoeui.ttf',24),fill=255,anchor='lt')
    expected=mask.getbbox()
    document={'regions':[{'text':'Translation','bbox':[15,15,150,55],'granularity':'line'}]}
    result=ocr_locator.refine_line_boxes('data:image/png;base64,'+base64.b64encode(b.getvalue()).decode(),document)
    box=result['regions'][0]['bbox']
    assert all(abs(a-b)<=1 for a,b in zip(box,expected))
    assert result['regions'][0]['text']=='Translation' and result['regions'][0]['ocrBbox']==[15,15,150,55]
