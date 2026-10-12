import json
import pytest
from fastapi import HTTPException
from backend.app.annotation_grounding import match_text,refine_control
from backend.tests.test_ai_annotations import client,text_location
from backend.tests.test_inline_translation import asset


def control(id='control-1',text='保存',bbox=None,controlType='Button'):
    return {'id':id,'text':text,'bbox':bbox or [10,10,95,45],'controlType':controlType}


def text_target(id,text,box):return {'id':id,'type':'text','text':text,'bbox':box}


def test_ocr_target_text_repairs_wrong_selected_line(client,monkeypatch):
    c,module=client
    async def locate(*args,**kwargs):return text_location()
    async def complete(*args):return {'text':json.dumps({'annotations':[{'kind':'circle','targetIds':['text-1'],'targetText':'右栏内容'}]})}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出右栏内容文字'})
    assert r.status_code==200
    assert r.json()['annotations'][0]['bbox']==[125,15,185,28]
    assert r.json()['annotations'][0]['locationSource']=='ocr'


def test_original_text_matches_without_inventing_model_geometry(client,monkeypatch):
    c,module=client
    async def locate(*args,**kwargs):return text_location()
    async def complete(*args):return {'text':json.dumps({'annotations':[{'kind':'callout','text':'说明','targetText':'第二行文字','bbox':[0,0,1000,1000]}]})}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'注释第二行文字'})
    assert r.status_code==200 and r.json()['annotations'][0]['bbox']==[12,35,105,48]


@pytest.mark.parametrize('query',['不存在的文字','这是注释而不是原文'])
def test_missing_original_text_rejected(client,monkeypatch,query):
    c,module=client
    async def locate(*args,**kwargs):return text_location()
    async def complete(*args):return {'text':json.dumps({'annotations':[{'kind':'circle','targetText':query}]})}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出文字'}).status_code==502


def test_repeated_label_requires_local_evidence():
    targets=[text_target('text-1','Save',[10,10,40,20]),text_target('text-2','Save',[100,10,130,20])]
    assert match_text('Save',targets) is None
    assert match_text('Save',targets,[90,5,135,25])['id']=='text-2'
    assert match_text('ＡＢＣ：123',[text_target('t','abc 123',[0,0,100,20])])['id']=='t'
    assert match_text('保',[text_target('t','保存',[0,0,100,20])]) is None
    assert match_text('if value != 0',[text_target('t','if value == 0',[0,0,100,20])]) is None


@pytest.mark.parametrize('query,status',[('第一行文字\n第二行文字',200),('右栏内容',502)])
def test_multiline_original_text_is_checked(client,monkeypatch,query,status):
    c,module=client
    async def locate(*args,**kwargs):return text_location()
    async def complete(*args):return {'text':json.dumps({'annotations':[{'kind':'circle','targetIds':['text-2','text-1'],'targetText':query}]})}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出左边两行文字'}).status_code==status


def test_uia_target_is_available_even_when_ocr_unavailable(client,monkeypatch):
    c,module=client
    async def locate(*args,**kwargs):raise HTTPException(503,'unavailable')
    async def complete(*args):
        assert 'control-1' in args[4] and 'UI Automation' in args[4]
        return {'text':'{"annotations":[{"kind":"circle","targetIds":["control-1"],"bbox":[0,0,1000,1000]}]}'}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出保存按钮','controls':[control()]})
    assert r.status_code==200 and r.json()['annotations'][0]['bbox']==[10,10,95,45]
    assert r.json()['annotations'][0]['locationSource']=='uia' and not r.json()['approximate']


def test_button_text_automatically_expands_to_exact_control(client,monkeypatch):
    c,module=client
    async def locate(*args,**kwargs):return {'width':200,'height':120,'mode':'windows','regions':[{'id':'text-1','text':'保存','bbox':[30,20,65,34],'granularity':'line'}]}
    async def complete(*args):return {'text':'{"annotations":[{"kind":"callout","text":"保存入口","targetIds":["text-1"]}]}'}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'给保存按钮添加注释','controls':[control()]})
    assert r.status_code==200 and r.json()['annotations'][0]['bbox']==[10,10,95,45]
    assert r.json()['annotations'][0]['locationSource']=='uia'
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出保存按钮上的文字','controls':[control()]})
    assert r.status_code==200 and r.json()['annotations'][0]['bbox']==[30,20,65,34]
    assert r.json()['annotations'][0]['locationSource']=='ocr'


def test_wrong_name_adjacent_and_ambiguous_controls_are_not_used():
    selected=[text_target('text-1','保存',[30,20,65,34])]
    assert refine_control(selected,[control(text='取消')],'保存按钮') is None
    assert refine_control(selected,[control(bbox=[110,10,190,45])],'保存按钮') is None
    assert refine_control(selected,[control(),control(id='control-2')],'保存按钮') is None
    assert refine_control(selected,[control()],'保存文字') is None


@pytest.mark.parametrize('controls,status',[
    ([control(bbox=[0,0,210,45])],400),
    ([control(),control()],400),
    ([control(controlType='Window')],422),
    ([control(bbox=[0,0,float('inf'),45])],422),
])
def test_bad_controls_never_call_llm(client,monkeypatch,controls,status):
    c,module=client
    async def forbidden(*args,**kwargs):raise AssertionError('bad controls must not upload')
    monkeypatch.setattr(module,'complete',forbidden)
    # NaN/Inf cannot be JSON-encoded by the client; send a valid JSON numeric overflow.
    body=json.dumps({'asset':asset(),'prompt':'圈出按钮','controls':controls}).replace('Infinity','1e999')
    assert c.post('/api/capture/annotate',content=body,headers={'Content-Type':'application/json'}).status_code==status


@pytest.mark.parametrize('ids',[['control-9'],['control-1','control-2']])
def test_unknown_or_grouped_controls_are_rejected(client,monkeypatch,ids):
    c,module=client
    async def complete(*args):return {'text':json.dumps({'annotations':[{'kind':'circle','targetIds':ids}]})}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出按钮','controls':[control(),control('control-2',bbox=[105,10,190,45])]}).status_code==502


def test_uia_cannot_be_used_for_a_physical_object(client,monkeypatch):
    c,module=client
    async def complete(*args):
        if args[3]=='objects':return {'text':'{"objects":[{"label":"杯子","bbox":[100,100,300,900]}]}'}
        return {'text':'{"annotations":[{"kind":"circle","targetIds":["control-1"]}]}'}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出杯子','controls':[control()]}).status_code==502
