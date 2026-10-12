from fastapi.testclient import TestClient
from backend.tests.test_capture_processing import module,ASSET


def session():
    return {'id':'imagechat-saved-test','title':'截图历史','scenario':'custom','assets':[{**ASSET,'id':'picture-1'}],
            'messages':[{'id':'answer-1','role':'assistant','text':'Earlier answer','action':'table','imageResult':{'assetId':'picture-1','tables':[{'title':'数据','rows':[['A','B'],['1','2']]}]}}],
            'formula':'','rows':[],'createdAt':'2026-10-10T00:00:00Z','updatedAt':'2026-10-10T00:00:00Z','pinned':False,
            'imageConversation':{'version':1,'selectedId':'picture-1','pictures':[{'assetId':'picture-1','annotations':[]}]}}


def test_image_scene_roundtrip(module):
    client=TestClient(module.app);body=session()
    assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    saved=client.get('/api/sessions/'+body['id']).json()
    assert saved['messages']==body['messages'] and saved['assets']==body['assets']
    assert saved['imageConversation']['pictures']==body['imageConversation']['pictures']

def test_recorded_voice_survives_session_roundtrip(module):
    from backend.tests.test_voice_message import recording
    client=TestClient(module.app);body=session()
    body['messages'].insert(0,{'id':'voice-message','role':'user','text':'真实 ASR 转录文本','voice':recording()})
    assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    assert client.get('/api/sessions/'+body['id']).json()['messages'][0]['voice']==body['messages'][0]['voice']


def call_session():
    body=session()
    body['id']='voicecall-history-test'
    body['messages']=[{'id':'question-1','role':'user','text':'识别截图文字','images':body['assets']},
                      {'id':'answer-1','role':'assistant','text':'截图文字内容'}]
    body['voiceCall']={'startedAt':body['createdAt'],'endedAt':body['updatedAt'],
                       'startMessageId':'question-1','endMessageId':'answer-1'}
    return body


def test_voice_call_history_and_text_continuation(module):
    client=TestClient(module.app);body=call_session()
    assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    assert client.get('/api/image-history').json()[0]['hasVoiceCall'] is True
    saved=client.get('/api/sessions/'+body['id']).json()
    assert saved['voiceCall']==body['voiceCall'] and saved['messages']==body['messages']
    saved['messages'] += [{'id':'text-question','role':'user','text':'解释刚才识别的内容'},
                          {'id':'text-answer','role':'assistant','text':'文字问答回复'}]
    assert client.put('/api/sessions/'+body['id'],json=saved).status_code==200
    assert client.get('/api/sessions/'+body['id']).json()['voiceCall']['endMessageId']=='answer-1'
    assert client.patch('/api/sessions/'+body['id']+'/metadata',json={'title':'通话记录'}).json()['hasVoiceCall'] is True


def test_voice_call_requires_answer_and_first_screenshot(module):
    client=TestClient(module.app)
    for case in ('no-answer','failed-answer','no-screenshot','missing-boundary','missing-end'):
        body=call_session()
        if case=='no-answer':body['messages'].pop();body['voiceCall']['endMessageId']='question-1'
        if case=='failed-answer':body['messages'][1]['failed']=True
        if case=='no-screenshot':body['messages'][0].pop('images')
        if case=='missing-boundary':body['voiceCall']['startMessageId']='missing'
        if case=='missing-end':body['voiceCall'].pop('endMessageId')
        assert client.put('/api/sessions/'+body['id'],json=body).status_code==422,case
    assert client.get('/api/image-history').json()==[]


def test_first_voice_query_never_precreates_backend_history(module):
    import asyncio
    from types import SimpleNamespace
    from fastapi import HTTPException
    context=SimpleNamespace(sessionId='voicecall-provisional-test',history=[],assets=[])
    async def invoke(history):return {'action':'chat','answer':'有效回复','payload':{}}
    async def fail(history):raise HTTPException(502,'测试首问失败')
    async def cancelled(history):raise asyncio.CancelledError()
    async def run():
        for handler in (invoke,fail,cancelled):
            try:await module.RUNTIME.image_run(context,'测试首问',None,{},None,None,module.DB,handler)
            except (HTTPException,asyncio.CancelledError):pass
            assert module.STORE.get(context.sessionId) is None
            assert module.STORE.list()==[]
    asyncio.run(run())


def test_entities_and_codes_roundtrip(module):
    client=TestClient(module.app);body=session()
    body['messages'][0]['imageResult'].update({'entities':[{'kind':'url','text':'example','url':'https://example.com','bbox':[0,0,10,10]}],'codes':[{'text':'example','format':'qr','bbox':[0,0,10,10],'url':'https://example.com'}]})
    assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    assert client.get('/api/sessions/'+body['id']).json()['messages']==body['messages']


def test_unknown_selected_image_rejected(module):
    body=session();body['imageConversation']['selectedId']='missing'
    assert TestClient(module.app).put('/api/sessions/'+body['id'],json=body).status_code==422


def test_unknown_scene_image_rejected(module):
    body=session();body['imageConversation']['pictures'][0]['assetId']='missing'
    assert TestClient(module.app).put('/api/sessions/'+body['id'],json=body).status_code==422


def test_duplicate_images_rejected(module):
    body=session();body['assets'].append(body['assets'][0].copy())
    assert TestClient(module.app).put('/api/sessions/'+body['id'],json=body).status_code==422


def test_duplicate_scenes_rejected(module):
    body=session();body['imageConversation']['pictures'].append(body['imageConversation']['pictures'][0].copy())
    assert TestClient(module.app).put('/api/sessions/'+body['id'],json=body).status_code==422


def test_annotation_bounds_rejected(module):
    body=session();body['imageConversation']['pictures'][0]['annotations']=[{'id':'annotation-1','kind':'rectangle','text':'','bbox':[0,0,150,150]}]
    assert TestClient(module.app).put('/api/sessions/'+body['id'],json=body).status_code==422


def test_legacy_session_without_scene_supported(module):
    body=session();body.pop('imageConversation')
    client=TestClient(module.app);assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    assert client.get('/api/image-history').json()==[]


def test_history_metadata_title_and_journal(module,monkeypatch):
    body={'id':'imagechat-history-test','title':'截图对话','scenario':'custom','assets':[ASSET],
          'messages':[{'id':'user-one','role':'user','text':'这是啥','sources':['fixture']},
                      {'id':'answer-one','role':'assistant','text':'已暂停输出','paused':True,'imageRequest':{'question':'这是啥','userId':'user-one'}}],
          'formula':'','rows':[],'createdAt':'2026-10-10T00:00:00Z','updatedAt':'2026-10-10T01:00:00Z','pinned':False,
          'imageConversation':{'version':1,'selectedId':'fixture','pictures':[{'assetId':'fixture','annotations':[]}]}}
    client=TestClient(module.app)
    assert client.put('/api/sessions/'+body['id'],json=body).status_code==200
    before=list(module.HOME.glob('sessions/**/*.jsonl'));assert len(before)==1
    assert client.get('/api/image-history').json()==[{key:body[key] for key in ('id','title','createdAt','updatedAt','pinned')}]
    async def recognize(data):return {'text':'PaddleOCR 多模态识别\n识别与定位功能说明'}
    captured=[]
    async def complete(profile,session,assets,action,prompt,path):
        captured.append((assets,action,prompt));return {'text':'标题：多模态文字识别'}
    monkeypatch.setattr(module,'recognize_positions_async',recognize)
    monkeypatch.setattr(module,'complete',complete)
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':False})
    result=client.post('/api/sessions/'+body['id']+'/image-title').json()
    assert result=={'title':'多模态文字识别','source':'summary'}
    assert captured[0][0]==[] and 'PaddleOCR' in captured[0][2] and '这是啥' not in captured[0][2]
    result=client.patch('/api/sessions/'+body['id']+'/metadata',json={'title':'重命名标题','pinned':True})
    assert result.status_code==200 and result.json()['pinned']
    assert result.json()['updatedAt'] != body['updatedAt']
    assert client.get('/api/image-history').json()[0]['updatedAt'] == result.json()['updatedAt']
    with module.STORE.connection() as db:
        assert db.execute('SELECT updated_at FROM sessions WHERE id=?',(body['id'],)).fetchone()['updated_at'] == result.json()['updatedAt']
    stored=client.get('/api/sessions/'+body['id']).json();assert stored['messages']==body['messages'];assert stored['assets']==[ASSET];assert stored['imageConversation']['titleGenerated']
    assert list(module.HOME.glob('sessions/**/*.jsonl'))==before
    assert '重命名标题' in before[0].read_text(encoding='utf-8')
    assert client.patch('/api/sessions/'+body['id']+'/metadata',json={'title':'   '}).status_code==400
    assert client.delete('/api/sessions/'+body['id']).status_code==200
    assert client.get('/api/image-history').json()==[] and client.get('/api/sessions/'+body['id']).status_code==404
    assert not before[0].exists();assert list((module.HOME/'backups/state').glob('deleted-*.json'))


def test_title_fallback_and_vision_permission(module,monkeypatch):
    from backend.app.image_history import generate_title
    import asyncio
    from fastapi import HTTPException
    async def fail(_):raise HTTPException(400,'No OCR')
    async def never(*_):raise AssertionError('Non-vision profile must not receive screenshots')
    result=asyncio.run(generate_title({'vision':False},module.Asset.model_validate(ASSET),fail,never,module.DB))
    assert result=={'title':'截图对话','source':'fallback'}
