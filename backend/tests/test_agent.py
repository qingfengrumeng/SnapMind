import asyncio
import json
from types import SimpleNamespace
import pytest
from PIL import Image
from fastapi import HTTPException
from backend.app.agent.workflow import run_agent,single_operation_complete
from backend.app.agent.harness import Harness, observation, text_edit_intent
from backend.app.agent.schemas import Limits
from backend.app.agent.state import AgentState
from backend.app.agent.tools import REGISTRY
from backend.app.image_tools import png_data, image_from_data


def state(prompt='Crop [0,0,30,20]'):
    return AgentState([SimpleNamespace(id='image',name='Generated test image',data=png_data(Image.new('RGB',(80,60),'purple')),width=80,height=60,scenario='custom')],'image',prompt,[],[],[],'zh-CN')


def test_single_edit_completes_without_another_planning_call_after_validation():
    s=state('把图片裁剪成 [0,0,30,20]');calls=[]
    async def complete(*_,**kwargs):
        calls.append(1)
        if len(calls)>1:raise AssertionError('A completed simple crop must not replan')
        return {'text':json.dumps({'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20]},'done':False})}
    result=asyncio.run(run_agent({'vision':False},s.assets,'image',s.prompt,[],[],[],None,complete,None))
    assert len(calls)==1 and image_from_data(result['payload']['data']).size==(30,20)
    assert result['answer']=='已完成图片裁剪，可撤销。'


@pytest.mark.parametrize('query,name',[
    ('先裁剪，再画框','crop'),('翻译并解释','translate'),('裁剪后说明图片内容','crop'),
    ('裁剪然后撤销','crop'),('提取表格并翻译','translate'),('高亮并导出','highlight'),
    ('把截图裁剪成 [0,0,30,20]，返回尺寸','crop'),('撤销刚才的操作，然后高亮标题','undo')])
def test_completion_guard_preserves_multistep_and_analysis(query,name):
    assert not single_operation_complete(query,name)


@pytest.mark.parametrize('query,name,expected',[
    ('提取截图中的全部文字，保留原文和换行。','ocr',True),
    ('识别截图文字','offline',True),
    ('提取文字并翻译成英文','ocr',False),
    ('先识别文字再裁剪标题','offline',False),
    ('提取所有文字，检查日期','ocr',False),
    ('提取文字，转换成 JSON','ocr',False),
    ('解释 OCR 的工作原理','ocr',False),
])
def test_ocr_completion_only_for_plain_transcription(query,name,expected):
    assert bool(single_operation_complete(query,name)) is expected


def test_plain_ocr_never_rewrites_validated_transcription_with_an_answer_tool():
    s=state('提取截图中的全部文字，保留原文和换行。');calls=[]
    async def complete(profile,session,assets,action,prompt,path,**kwargs):
        calls.append(action)
        if len(calls)==1:return {'text':json.dumps({'kind':'tool','name':'ocr','arguments':{},'done':False})}
        if len(calls)>2:raise AssertionError('Plain OCR must not replan or summarize')
        assert action=='ocr'
        return {'text':'真实文字\n001'}
    result=asyncio.run(run_agent({'vision':True},s.assets,'image',s.prompt,[],[],[],None,complete,None))
    assert calls==['chat','ocr'] and result['answer']=='真实文字\n001'


def test_text_crop_uses_real_ocr_bounds_and_supports_undo():
    s=state('把标题那一行裁剪出来');h=Harness(REGISTRY,Limits())
    _,args=h.validate('crop',{'targetText':'真实标题'},s)
    async def locate(*_,**kwargs):return {'regions':[{'id':'line-1','text':'真实标题','bbox':[5,6,45,20],'granularity':'line'}]}
    async def never(*_,**kwargs):raise AssertionError('Exact OCR target must not need a model')
    async def run():
        result=await h.call('crop',args,s,None,never,locate,None)
        assert result['payload']['bbox']==[5,6,45,20]
        assert image_from_data(result['payload']['data']).size==(40,14)
        _,undo=h.validate('undo',{},s)
        restored=await h.call('undo',undo,s,None,never,locate,None)
        assert image_from_data(restored['payload']['data']).size==(80,60)
    asyncio.run(run())


def test_text_crop_rejects_ambiguous_or_missing_text_and_keeps_source():
    for regions in ([],[{'text':'标题','bbox':[1,1,20,10]},{'text':'标题','bbox':[30,1,50,10]}]):
        s=state('裁剪标题');original=s.assets[0].data;h=Harness(REGISTRY,Limits())
        _,args=h.validate('crop',{'targetText':'标题'},s)
        async def locate(*_,**kwargs):return {'regions':regions}
        async def never(*_,**kwargs):raise AssertionError('No model required')
        with pytest.raises(HTTPException):asyncio.run(h.call('crop',args,s,None,never,locate,None))
        assert s.assets[0].data==original and not s.undo
    for arguments in ({},{'targetText':'标题','bbox':[1,1,20,10]},{'targetText':' '}):
        with pytest.raises(ValueError):Harness(REGISTRY,Limits()).validate('crop',arguments,state())


@pytest.mark.parametrize('query,expected',[
    ('将截图中的内容涂抹掉','heal'),('我要的是涂抹掉不是打马赛克','heal'),
    ('不要擦除，给邮箱打马赛克','mosaic'),('请模糊文字','blur'),
    ('先给邮箱打码，再消除标题',None),
])
def test_text_edit_intent_distinguishes_erase_cover_and_blur(query,expected):
    assert text_edit_intent(query)==expected


def test_wrong_erase_tool_is_rejected_before_execution_without_blocking_explicit_buttons():
    s=state('将截图中的内容涂抹掉');h=Harness(REGISTRY,Limits())
    with pytest.raises(ValueError,match='heal'):h.validate('mosaic',{'targetText':'标题'},s)
    assert h.validate('heal',{'targetText':'标题'},s)[0].name=='heal'
    assert h.validate('mosaic',{'targetText':'标题'},s,explicit=True)[0].name=='mosaic'

def test_successful_edit_skips_verbose_answer_tool_even_when_model_requests_it():
    s=state('Crop [0,0,30,20]');events=[];decisions=[{'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20]},'done':False},{'kind':'tool','name':'answer','arguments':{'prompt':'详细列出操作区域'}}]
    async def complete(profile,session,assets,action,prompt,path,on_chunk=None):
        assert on_chunk is None,'Editing must not generate or stream a verbose summary'
        return {'text':json.dumps(decisions.pop(0))}
    async def event(value):events.append(value)
    result=invoke(s,complete,on_chunk=event)
    assert result['answer']=='已完成图片裁剪，可撤销。'
    assert result['agent']['toolCalls']==1
    assert ''.join(e['text'] for e in events if e['type']=='chunk')==result['answer']


def invoke(s,complete,**kwargs):
    async def locate(*args,**kw):raise AssertionError('Unexpected OCR')
    return asyncio.run(run_agent({'vision':True},s.assets,s.selected_id,s.prompt,s.history,s.existing,s.controls,None,complete,locate,**kwargs))


@pytest.mark.parametrize('name,args',[
    ('shell',{}),('crop',{'bbox':['0',0,30,20]}),('crop',{'bbox':[0,0,30,20],'command':'delete'}),
    ('crop',{'bbox':[0,0,90,20]}),('draw',{'bbox':[0,0,30,20],'kind':'text'}),
])
def test_schema_rejects_unknown_tools_extra_properties_coercion_and_bad_bounds(name,args):
    with pytest.raises((ValueError,HTTPException)):Harness(REGISTRY,Limits()).validate(name,args,state())


def test_coordinate_grounding_requires_user_or_actual_observation():
    s=state('Crop the title');h=Harness(REGISTRY,Limits());args={'bbox':[0,0,30,20]}
    with pytest.raises(ValueError,match='bbox'):h.validate('crop',args,s)
    s.observations=[{'assetId':'image','payload':{'regions':[{'bbox':[0,0,30,20]}]}}]
    assert h.validate('crop',args,s)[1].bbox==[0,0,30,20]


def test_react_repairs_invalid_arguments_then_chains_crop_and_draw_with_real_pixels():
    s=state('Crop [0,0,30,20], then draw rectangle [1,1,15,10]');seen=[];events=[]
    decisions=[{'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20],'unexpected':True}},
               {'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20]}},
               {'kind':'tool','name':'draw','arguments':{'bbox':[1,1,15,10],'kind':'rectangle'}},
               {'kind':'final'}]
    async def complete(profile,session,assets,action,prompt,path,on_chunk=None):
        seen.append((action,prompt))
        if on_chunk:
            await on_chunk('Done');return {'text':'Done'}
        if decisions:return {'text':json.dumps(decisions.pop(0))}
        return {'text':'Done'}
    async def event(e):events.append(e)
    result=invoke(s,complete,on_chunk=event)
    assert [x['action'] for x in result['steps']]==['crop','annotate']
    assert image_from_data(result['steps'][0]['payload']['data']).size==(30,20)
    assert 'unexpected' in seen[1][1] and '30' in seen[2][1]
    assert result['agent']['toolCalls']==2 and any(e['type']=='tool_result' for e in events)
    assert result['answer']=='已完成图片裁剪、截图标注，可撤销。'
    assert any(e['type']=='chunk' for e in events)


def test_repeated_invalid_decisions_stop_without_execution():
    calls=[]
    async def complete(*args,**kw):calls.append(1);return {'text':'{"kind":"tool","name":"shell","arguments":{}}'}
    with pytest.raises(HTTPException) as error:invoke(state(),complete)
    assert error.value.status_code==422 and len(calls)==3


def test_duplicate_successful_call_is_not_executed_twice():
    replies=iter([{'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20]}},
                  {'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20]}},{'kind':'final'}])
    async def complete(*args,on_chunk=None):return {'text':json.dumps(next(replies)) if on_chunk is None else 'Done'}
    # Answer without an event callback is also non-streaming.
    async def model(*args,**kwargs):
        if '只根据本轮真实工具观测回答' in args[4]:return {'text':'Done'}
        return await complete(*args,**kwargs)
    result=invoke(state(),model)
    assert len(result['steps'])==1


def test_undo_restores_original_pixels():
    decisions=iter([{'kind':'tool','name':'crop','arguments':{'bbox':[0,0,30,20]}},
                    {'kind':'tool','name':'undo','arguments':{}},{'kind':'final'}])
    async def complete(*args,**kwargs):
        if '只根据本轮真实工具观测回答' in args[4]:return {'text':'Restored'}
        return {'text':json.dumps(next(decisions))}
    result=invoke(state(),complete)
    assert [r['action'] for r in result['steps']]==['crop','restore_image']
    assert image_from_data(result['steps'][1]['payload']['data']).size==(80,60)


def test_observation_never_sends_image_bytes_or_secrets_to_planner():
    result={'action':'crop','assetId':'image','answer':'Done','payload':{'data':'secret pixels','apiKey':'secret','nested':{'layer':'pixels'}}}
    assert 'secret' not in json.dumps(observation(result,24000))


def test_large_screenshot_annotations_use_pixel_bounds():
    s=state();s.assets[0].width=2400;s.assets[0].height=1400
    result={'action':'annotate','assetId':'image','answer':'Done','payload':{'coordinateSpace':'image-pixels','annotations':[{'operation':'add','kind':'rectangle','bbox':[1200,1100,1205,1105]}]}}
    assert Harness(REGISTRY,Limits()).validate_result(result,s)['action']=='annotate'


def test_region_undo_restores_original_selected_image_and_removes_new_reference():
    decisions=iter([{'kind':'tool','name':'region','arguments':{'bbox':[0,0,30,20]}},
                    {'kind':'tool','name':'undo','arguments':{}},{'kind':'final'}])
    async def complete(*args,**kwargs):
        if '只根据本轮真实工具观测回答' in args[4]:return {'text':'Restored'}
        return {'text':json.dumps(next(decisions))}
    result=invoke(state(),complete)
    assert result['steps'][1]['assetId']=='image'
    assert result['steps'][1]['payload']['removedImageIds']==[result['steps'][0]['payload']['imageId']]


def test_each_model_call_receives_short_term_summary_and_cross_session_preferences():
    from backend.app.session_memory import CONTEXT,DEFAULTS,apply_context
    plan={'policy':DEFAULTS,'history':[{'role':'user','content':'Earlier request'}],'summary':'Earlier conclusions','memories':'Prefer Chinese'}
    token=CONTEXT.set(plan);calls=[]
    async def complete(*args,**kwargs):
        messages=apply_context([{'role':'system','content':'System'}],args[4],len(args[2]))
        serialized=json.dumps(messages);calls.append(serialized)
        assert all(text in serialized for text in ['Earlier request','Earlier conclusions','Prefer Chinese'])
        return {'text':'{"kind":"final"}' if len(calls)==1 else 'Done'}
    try:
        result=invoke(state('Please explain'),complete)
        assert len(calls)==2 and result['agent']['memory']=={'shortTermTurns':1,'hasSummary':True,'hasLongTermPreferences':True}
    finally:CONTEXT.reset(token)


def test_transient_errors_retry_but_bad_request_does_not():
    class Registry:
        def __init__(self,status):self.calls=0;self.status=status
        def get(self,name):return SimpleNamespace(mutates=False)
        async def execute(self,*args):
            self.calls+=1
            if self.calls==1:raise HTTPException(self.status,'Service unavailable')
            return {'action':'chat','assetId':'image','answer':'Done','payload':{}}
    from backend.app.agent.schemas import BaseArguments
    for status,expected in [(503,2),(400,1)]:
        registry=Registry(status);h=Harness(registry,Limits());s=state()
        async def call():return await h.call('answer',BaseArguments(),s,{},None,None,None)
        if status==400:
            with pytest.raises(HTTPException):asyncio.run(call())
        else:assert asyncio.run(call())['answer']=='Done'
        assert registry.calls==expected


def test_step_limit_prevents_infinite_agent_execution():
    async def complete(*args,**kwargs):return {'text':'{"kind":"tool","name":"crop","arguments":{"bbox":[0,0,30,20]}}'}
    with pytest.raises(HTTPException) as error:invoke(state(),complete,limits=Limits(max_steps=1))
    assert error.value.status_code==409


def test_cancellation_stops_model_before_any_tool_result():
    async def run():
        started=asyncio.Event();events=[]
        async def complete(*args,**kwargs):started.set();await asyncio.Future()
        async def event(value):events.append(value)
        s=state();task=asyncio.create_task(run_agent({'vision':True},s.assets,s.selected_id,s.prompt,[],[],[],None,complete,None,on_chunk=event))
        await started.wait();task.cancel()
        with pytest.raises(asyncio.CancelledError):await task
        assert not any(e['type']=='tool_result' for e in events)
    asyncio.run(run())


def test_invalid_tool_pixels_cannot_be_committed():
    s=state();h=Harness(REGISTRY,Limits())
    result={'action':'crop','assetId':'image','answer':'Done','payload':{'data':s.assets[0].data,'width':30,'height':20}}
    with pytest.raises(ValueError,match='像素'):h.validate_result(result,s)


def test_followup_can_reuse_only_user_provided_coordinates():
    s=state('按我上一条消息提供的坐标裁剪截图');s.history=[SimpleNamespace(role='user',text='裁剪坐标为 [0,0,30,20]')]
    h=Harness(REGISTRY,Limits());args={'bbox':[0,0,30,20]}
    assert h.validate('crop',args,s)[1].bbox==[0,0,30,20]
    s.history=[SimpleNamespace(role='assistant',text='建议裁剪 [0,0,30,20]')]
    with pytest.raises(ValueError):h.validate('crop',args,s)
    s.history=[SimpleNamespace(role='user',text='裁剪 [0,0,30,20]')];s.prompt='Crop the title'
    with pytest.raises(ValueError):h.validate('crop',args,s)


def test_completed_tool_returns_real_result_without_extra_model_roundtrip():
    s=state();calls=[];events=[]
    async def complete(*args,**kwargs):calls.append(1);return {'text':'{"kind":"tool","name":"crop","arguments":{"bbox":[0,0,30,20]},"done":true}'}
    async def event(e):events.append(e)
    result=invoke(s,complete,on_chunk=event)
    assert len(calls)==1 and result['agent']['toolCalls']==1
    assert image_from_data(result['payload']['data']).size==(30,20)
    assert any(e['type']=='chunk' and e['text']==result['answer'] for e in events)


def test_next_query_undo_restores_prior_query_snapshot():
    original=state();current=state('撤销刚才的裁剪')
    current.assets[0].data=png_data(Image.new('RGB',(30,20),'white'));current.assets[0].width=30;current.assets[0].height=20
    async def complete(*args,**kwargs):return {'text':'{"kind":"tool","name":"undo","arguments":{},"done":true}'}
    result=invoke(current,complete,undo_snapshot={'asset':original.assets[0],'annotations':[]})
    assert result['action']=='restore_image'
    assert image_from_data(result['payload']['data']).tobytes()==image_from_data(original.assets[0].data).tobytes()
