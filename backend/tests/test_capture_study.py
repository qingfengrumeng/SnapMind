import asyncio
from concurrent.futures import CancelledError
import importlib
import json
import sys
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.tests.test_inline_translation import asset
from backend.app.capture_study import code_lines

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    async def locate(*args,**kwargs):
        assert kwargs=={'require_lines':True,'cloud_timeout':15}
        return {'width':200,'height':120,'mode':'paddleocr','regions':[
            {'id':'text-1','text':'41','bbox':[5,10,15,22],'granularity':'line'},
            {'id':'text-2','text':'def add(a, b):','bbox':[25,10,180,22],'granularity':'line'},
            {'id':'text-3','text':'42','bbox':[5,35,15,47],'granularity':'line'},
            {'id':'text-4','text':'    return a + b','bbox':[40,35,180,47],'granularity':'line'},
        ]}
    monkeypatch.setattr(module,'locate',locate)
    with TestClient(module.app) as c:yield c,module

def post(c,**kwargs):
    return c.post('/api/capture/study',json={'assets':[asset()],'mode':'code','prompt':'逐行解释代码',**kwargs})

def test_editor_line_mapping_and_authoritative_geometry(client,monkeypatch):
    c,module=client
    async def complete(*args):
        assert args[3]=='study' and len(args[2])==1
        prompt=args[4];assert '输入、输出' in prompt and '不要运行' in prompt
        assert '"lineNumber": 42' in prompt and '"lineSource": "editor"' in prompt
        assert '"id": "text-1"' not in prompt
        return {'text':json.dumps({'answer':'第41行定义函数，第42行返回两数之和。','notes':[
            {'pageId':'fixture','targetIds':['text-4'],'text':'返回两数之和','explanation':'第42行将参数相加后返回。','bbox':[0,0,1000,1000]}]})}
    monkeypatch.setattr(module,'complete',complete)
    r=post(c);assert r.status_code==200
    note=r.json()['notes'][0]
    assert note['lineLabel']=='第 42 行' and note['bbox']==[40,35,180,47] and note['locationSource']=='ocr'

def test_no_gutter_uses_relative_rows_and_keeps_indentation():
    regions=[{'id':'a','text':'def f():','bbox':[25,10,180,22]}, {'id':'b','text':'    return 1','bbox':[40,35,180,47]}]
    result=code_lines(regions)
    assert [r['lineNumber'] for r in result]==[1,2]
    assert all(r['lineSource']=='selection' for r in result)
    assert result[1]['text'].startswith('    ')

@pytest.mark.parametrize('split',[False,True])
def test_numeric_expression_is_not_invented_editor_gutter(split):
    regions=[{'id':'a','text':'1 + 2','bbox':[25,10,180,22]}, {'id':'b','text':'2 + 3','bbox':[25,35,180,47]}]
    if split:regions=[{'id':'a','text':'1','bbox':[25,10,35,22]}, {'id':'b','text':'+ 2','bbox':[45,10,90,22]}, {'id':'c','text':'2','bbox':[25,35,35,47]}, {'id':'d','text':'+ 3','bbox':[45,35,90,47]}]
    assert all(r['lineSource']=='selection' for r in code_lines(regions))

def test_paper_uses_all_ordered_pages_and_separate_coordinates(client,monkeypatch):
    c,module=client
    async def complete(*args):
        assert len(args[2])==2 and [a.id for a in args[2]]==['fixture','page-two']
        assert '至少两页' in args[4] and '答案和解析分开' in args[4] and '不编造' in args[4]
        return {'text':json.dumps({'answer':'第1页和第2页的步骤都缺少解释。','notes':[
            {'pageId':'page-two','targetIds':['text-2'],'text':'说明步骤依据','explanation':'第2页这一步应注明计算依据。'}]})}
    monkeypatch.setattr(module,'complete',complete)
    r=post(c,mode='paper',assets=[asset(),asset()|{'id':'page-two'}],prompt='比较多页的共同错误')
    assert r.status_code==200 and r.json()['notes'][0]['pageId']=='page-two'
    assert [p['number'] for p in r.json()['pages']]==[1,2]

@pytest.mark.parametrize('note',[
 {'pageId':'missing','targetIds':['text-2']},
 {'pageId':'fixture','targetIds':['missing']},
 {'pageId':'fixture','targetIds':['text-2','text-4']},
 {'pageId':'fixture','targetIds':['text-2','text-2']},
])
def test_bad_or_cross_line_targets_are_never_drawn(client,monkeypatch,note):
    c,module=client
    async def complete(*args):return {'text':json.dumps({'answer':'解释','notes':[note|{'text':'说明','explanation':'详解'}]})}
    monkeypatch.setattr(module,'complete',complete)
    assert post(c).status_code==502

def test_followup_practice_can_preserve_annotations(client,monkeypatch):
    c,module=client
    async def complete(*args):
        assert '上一次的问题' in args[4]
        return {'text':'{"answer":"练习：计算 2+3。答案：5。","notes":[]}'}
    monkeypatch.setattr(module,'complete',complete)
    r=post(c,mode='paper',prompt='生成练习，不添加图片标注',history=[{'role':'user','text':'上一次的问题'},{'role':'assistant','text':'解释'}])
    assert r.status_code==200 and r.json()['notes']==[]

def test_ocr_unavailable_can_explain_but_not_locate(client,monkeypatch):
    c,module=client
    async def locate(*args,**kwargs):raise HTTPException(503,'unavailable')
    async def complete(*args):
        assert 'unavailable' in args[4]
        return {'text':'{"answer":"这段代码定义加法函数。","notes":[]}'}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    r=post(c);assert r.status_code==200 and r.json()['pages'][0]['warning']

def test_invalid_context_and_disabled_vision_do_not_upload(client,monkeypatch):
    c,module=client
    async def forbidden(*args,**kwargs):raise AssertionError('Must not upload')
    monkeypatch.setattr(module,'locate',forbidden);monkeypatch.setattr(module,'complete',forbidden)
    for profile in [None,{'vision':False}]:
        monkeypatch.setattr(module,'get_active_profile',lambda _,p=profile:p)
        assert post(c).status_code==400
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    for payload in [ {'assets':[asset(),asset()]}, {'assets':[asset()|{'width':100}]}, {'prompt':' '}, {'assets':[asset()|{'data':'data:image/png;base64,aGVsbG8='}]} ]:
        assert post(c,**payload).status_code==400
    assert post(c,mode='paper',assets=[asset()]*7).status_code==422

def test_cancellation_does_not_start_llm_after_cancel(client,monkeypatch):
    c,module=client
    async def cancelled(*args,**kwargs):raise asyncio.CancelledError()
    async def forbidden(*args):raise AssertionError('Must not start model after OCR cancellation')
    monkeypatch.setattr(module,'locate',cancelled);monkeypatch.setattr(module,'complete',forbidden)
    with pytest.raises((asyncio.CancelledError,CancelledError)):post(c)
