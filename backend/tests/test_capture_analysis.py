import importlib
import json
import sys
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app.capture_analysis import parse,Tables,Objects


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'.snapmind'))
    monkeypatch.setenv('SNAPMIND_DATA_DIR',str(tmp_path))
    sys.modules.pop('backend.app.main',None)
    module=importlib.import_module('backend.app.main')
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':True})
    with TestClient(module.app) as c: yield c,module


def asset():
    from backend.tests.test_inline_translation import asset as image
    return image()


def test_table_preserves_columns_empty_cells_unicode_numbers_and_formula_text(client,monkeypatch):
    c,module=client
    expected={'tables':[{'title':'统计表','rows':[['名称','数量','备注'],['产品 A','001',''],['产品 B','-3.5','=1+2']]}]}
    async def complete(profile,session,images,action,prompt,path):
        assert action=='table-json' and len(images)==1 and session.messages==[]
        assert '不翻译、不计算' in prompt and '合并单元格' in prompt
        return {'text':'```json\n'+json.dumps(expected)+'\n```'}
    monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/analyze',json={'asset':asset(),'action':'table'})
    assert r.status_code==200 and r.json()==expected


@pytest.mark.parametrize('body',[
    {'tables':[{'rows':[['a','b'],['c']]}]},
    {'tables':[{'rows':[[1,2]]}]},
    {'tables':[{'rows':[[]]}]},
    {'tables':[{'rows':[['a']]*301}]},
])
def test_invalid_table_response_cannot_shift_or_invent_cells(body):
    with pytest.raises(HTTPException) as e: parse(json.dumps(body),Tables)
    assert e.value.status_code==502


def test_empty_tables_are_not_replaced_with_demo_content():
    assert parse('{"tables":[]}',Tables).tables==[]


def test_detect_maps_normalized_coordinates_to_original_pixels_and_deduplicates(client,monkeypatch):
    c,module=client
    async def complete(profile,session,images,action,prompt,path):
        assert action=='objects' and '车辆' in prompt and '0到1000' in prompt
        return {'text':json.dumps({'objects':[{'label':'汽车','bbox':[100,200,400,600]},{'label':'汽车','bbox':[100,200,400,600]}, {'label':'客车','bbox':[500,200,900,700]}]})}
    monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/analyze',json={'asset':asset(),'action':'detect','target':'vehicles'})
    assert r.status_code==200
    result=r.json()
    assert len(result['objects'])==2 and result['objects'][0]['bbox']==[20,24,80,72]
    assert result['objects'][1]['bbox']==[100,24,180,84]
    assert result['coordinateSpace']=='image-pixels' and result['approximate']


@pytest.mark.parametrize('bbox',[[0,0,1200,100],[-5,0,50,50],[100,100,20,20],[0,0,float('nan'),10],[0,0,True,100]])
def test_invalid_or_nonfinite_boxes_are_not_drawn(bbox):
    with pytest.raises(HTTPException):parse(json.dumps({'objects':[{'label':'汽车','bbox':bbox}]}),Objects)


def test_text_only_profile_and_missing_profile_do_not_upload_images(client,monkeypatch):
    c,module=client
    async def forbidden(*args): raise AssertionError('Must not upload')
    monkeypatch.setattr(module,'complete',forbidden)
    for profile in [None,{'vision':False}]:
        monkeypatch.setattr(module,'get_active_profile',lambda _,value=profile:value)
        for action in ['table','detect']:
            assert c.post('/api/capture/analyze',json={'asset':asset(),'action':action}).status_code==400


def test_empty_detection_and_bad_json(client,monkeypatch):
    c,module=client
    async def complete(*args): return {'text':'{"objects":[]}'}
    monkeypatch.setattr(module,'complete',complete)
    r=c.post('/api/capture/analyze',json={'asset':asset(),'action':'detect'})
    assert r.status_code==200 and r.json()['objects']==[]
    with pytest.raises(HTTPException):parse('Here is a table: invalid',Tables)
