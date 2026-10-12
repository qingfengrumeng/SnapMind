import importlib
import json
import sys
import pytest
from fastapi.testclient import TestClient
from backend.tests.test_inline_translation import asset

@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    async def locate(*args,**kwargs):return {'width':200,'height':120,'mode':'windows','regions':[]}
    monkeypatch.setattr(module,'locate',locate)
    with TestClient(module.app) as c:yield c,module

def test_add_bubble_check_circle_and_shorten_labels(client,monkeypatch):
    c,module=client
    async def complete(profile,session,images,action,prompt,path):
        assert action=='annotate' and len(images)==1 and not session.messages
        assert '注释要精简' in prompt and '气泡位置' in prompt
        return {'text':json.dumps({'answer':'已标注。','annotations':[
            {'kind':'callout','text':'注释内容'*20,'bbox':[100,100,400,500]},
            {'kind':'circle','bbox':[500,100,900,500]},
            {'kind':'check','bbox':[500,600,900,900]}]})}
    monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'添加气泡说明、圈选和勾选'})
    assert r.status_code==200
    result=r.json();assert result['annotations'][0]['bbox']==[20,12,80,60]
    assert len(result['annotations'][0]['text'])==40 and result['annotations'][0]['text'].endswith('…')
    assert [a['kind'] for a in result['annotations']]==['callout','circle','check']

def test_followup_uses_existing_ids_and_conversation(client,monkeypatch):
    c,module=client
    async def complete(*args):
        prompt=args[4]
        assert '更短' in prompt and '原始问题' in prompt and 'ai-7' in prompt
        assert '[100.0, 100.0, 400.0, 500.0]' in prompt
        return {'text':json.dumps({'answer':'已修改。','annotations':[{'operation':'update','id':'ai-7','kind':'callout','text':'简要说明'},{'operation':'remove','id':'ai-8'}]})}
    monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'更短，删除另一个圈',
        'history':[{'role':'user','text':'原始问题'},{'role':'assistant','text':'已标注'}],
        'existing':[{'id':'ai-7','kind':'callout','text':'原注释','bbox':[20,12,80,60]}, {'id':'ai-8','kind':'circle','text':'','bbox':[100,12,180,60]}]})
    assert r.status_code==200
    assert [a['operation'] for a in r.json()['annotations']]==['update','remove']
    assert r.json()['annotations'][0]['bbox']==[20,12,80,60]

@pytest.mark.parametrize('edit',[
 {'kind':'callout','text':'','bbox':[10,10,100,100]},
 {'kind':'circle','bbox':[100,100,10,10]},
 {'kind':'circle','bbox':[0,0,1001,100]},
 {'kind':'circle','bbox':[0,0,float('nan'),100]},
 {'operation':'remove','id':'ai-99'},
 {'operation':'update','id':'ai-99','kind':'callout','text':'更新','bbox':[0,0,100,100]},
])
def test_invalid_model_reply_is_not_applied(client,monkeypatch,edit):
    c,module=client
    async def complete(*args):return {'text':json.dumps({'annotations':[edit]})}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'测试'}).status_code==502

def test_missing_vision_or_invalid_client_context_never_uploads(client,monkeypatch):
    c,module=client
    async def forbidden(*args):raise AssertionError('Must not upload')
    monkeypatch.setattr(module,'complete',forbidden)
    for profile in [None,{'vision':False}]:
        monkeypatch.setattr(module,'get_active_profile',lambda _,p=profile:p)
        assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'说明'}).status_code==400
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    for extra in [{'prompt':'  '},{'existing':[{'id':'ai-1','kind':'circle','bbox':[0,0,400,200]}]}]:
        assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'说明',**extra}).status_code==400

def test_question_can_return_answer_without_invented_annotations(client,monkeypatch):
    c,module=client
    async def complete(*args):return {'text':'{"answer":"This is a settings screen.","annotations":[]}'}
    monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'这是做什么的？'})
    assert r.status_code==200 and r.json()['annotations']==[]

@pytest.mark.parametrize('label',[None,'AI 标注功能说明文字','Text paragraph'])
def test_text_only_screenshot_does_not_substitute_paragraph_for_object(client,monkeypatch,label):
    c,module=client;calls=[]
    async def complete(*args):
        calls.append(args[3]);assert args[3]=='objects'
        return {'text':json.dumps({'objects':[] if label is None else [{'label':label,'bbox':[100,100,900,500]}]})}
    async def forbidden(*args,**kwargs):raise AssertionError('Object request must not use text targets')
    monkeypatch.setattr(module,'complete',complete);monkeypatch.setattr(module,'locate',forbidden)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出截图中的主要物品'})
    assert r.status_code==200 and r.json()['annotations']==[]
    assert '未找到' in r.json()['answer'] and calls==['objects']

def test_physical_annotation_uses_detected_candidate_not_second_model_coordinates(client,monkeypatch):
    c,module=client;calls=[]
    async def complete(*args):
        calls.append(args[3])
        if args[3]=='objects':return {'text':'{"objects":[{"label":"杯子","bbox":[100,200,300,800]}]}'}
        assert 'object-1' in args[4] and 'objectsOnly": true' in args[4]
        return {'text':'{"annotations":[{"kind":"circle","targetIds":["object-1"],"bbox":[0,0,1000,1000]}]}'}
    monkeypatch.setattr(module,'complete',complete)
    result=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出杯子'}).json()
    assert calls==['objects','annotate']
    assert result['annotations'][0]['bbox']==[20,24,60,96]
    assert result['annotations'][0]['locationSource']=='object-detection'

@pytest.mark.parametrize('edit',[
    {'kind':'circle','bbox':[0,0,1000,1000]},
    {'kind':'circle','targetIds':['object-9']},
    {'kind':'circle','targetIds':['object-1','object-2']},
])
def test_object_scope_rejects_fabricated_or_grouped_targets(client,monkeypatch,edit):
    c,module=client
    async def complete(*args):
        if args[3]=='objects':return {'text':json.dumps({'objects':[
            {'label':'杯子','bbox':[100,100,300,900]}, {'label':'瓶子','bbox':[600,100,800,900]}]})}
        return {'text':json.dumps({'annotations':[edit]})}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出物品'}).status_code==502

def text_location():
    return {'width':200,'height':120,'mode':'paddle','regions':[
        {'id':'text-1','text':'第一行文字','bbox':[12,15,98,28],'granularity':'line'},
        {'id':'text-2','text':'第二行文字','bbox':[12,35,105,48],'granularity':'line'},
        {'id':'text-3','text':'右栏内容','bbox':[125,15,185,28],'granularity':'line'},
    ]}

def test_text_annotation_is_grounded_to_exact_ocr_lines(client,monkeypatch):
    c,module=client
    async def locate(*args,**kwargs):
        assert kwargs['require_lines'] is True
        assert kwargs['cloud_timeout']==15
        return text_location()
    async def complete(*args):
        assert '第一行文字' in args[4] and 'text-3' in args[4]
        return {'text':json.dumps({'annotations':[{'kind':'callout','text':'说明','targetIds':['text-1','text-2'],'bbox':[0,0,1000,1000]}]})}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'注释左侧两行文字'})
    assert r.status_code==200
    result=r.json();assert result['annotations'][0]['bbox']==[12,15,105,48]
    assert result['annotations'][0]['locationSource']=='ocr' and not result['approximate']
    assert 'targetIds' not in result['annotations'][0]

@pytest.mark.parametrize('edit',[
    {'kind':'circle','bbox':[0,0,1000,1000]},
    {'kind':'circle','targetIds':['text-99']},
    {'kind':'circle','targetIds':['text-1','text-1']},
])
def test_text_scope_rejects_estimated_paragraph_and_unknown_lines(client,monkeypatch,edit):
    c,module=client
    async def locate(*args,**kwargs):return text_location()
    async def complete(*args):return {'text':json.dumps({'annotations':[edit]})}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出第一行文字'}).status_code==502

def test_unavailable_ocr_does_not_fall_back_to_estimated_text_coordinates(client,monkeypatch):
    from fastapi import HTTPException
    c,module=client
    async def locate(*args,**kwargs):raise HTTPException(503,'OCR unavailable')
    async def complete(*args):return {'text':'{"annotations":[{"kind":"circle","bbox":[100,100,900,300]}]}'}
    monkeypatch.setattr(module,'locate',locate);monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出标题文字'}).status_code==502

def test_empty_ocr_result_never_estimates_text_position(client,monkeypatch):
    c,module=client
    async def complete(*args):return {'text':'{"annotations":[{"kind":"circle","bbox":[100,100,900,300]}]}'}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'圈出标题文字'}).status_code==502

def test_excluding_text_does_not_change_physical_object_scope(client,monkeypatch):
    c,module=client
    async def complete(*args):
        assert args[3]=='objects'
        return {'text':'{"objects":[]}'}
    monkeypatch.setattr(module,'complete',complete)
    assert c.post('/api/capture/annotate',json={'asset':asset(),'prompt':'只圈出主要物品，不要圈文字'}).json()['annotations']==[]

@pytest.mark.parametrize('prompt',['把圈出的物品改成勾选','把圈选改成气泡注释，内容是“注释指向对应内容”，保留原来的位置。'])
def test_editing_existing_physical_mark_does_not_redetect_or_move_it(client,monkeypatch,prompt):
    c,module=client
    async def forbidden(*args,**kwargs):raise AssertionError('Existing edit needs no new OCR')
    async def complete(*args):
        assert args[3]=='annotate' and 'existingEditsOnly": true' in args[4]
        return {'text':'{"annotations":[{"operation":"update","id":"ai-7","kind":"check","bbox":[0,0,1000,1000]}]}'}
    monkeypatch.setattr(module,'locate',forbidden);monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/annotate',json={'asset':asset(),'prompt':prompt,
        'existing':[{'id':'ai-7','kind':'circle','bbox':[20,12,80,60]}]})
    assert r.status_code==200 and r.json()['annotations'][0]['bbox']==[20,12,80,60]
