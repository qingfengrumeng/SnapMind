import asyncio
import copy
import importlib
import json
import sqlite3
import sys
from datetime import datetime,timezone,timedelta
import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from backend.app.local_storage import migrate_legacy,atomic_write,json_text
from backend.app.session_store import SessionStore
from backend.app.session_memory import MemoryManager,CONTEXT,apply_context

def session(turns=2,sid='memory-test'):
    stamp=datetime.now(timezone.utc).isoformat()
    return {'id':sid,'title':'Synthetic conversation','scenario':'custom',
            'assets':[{'id':'a','name':'synthetic','data':'data:image/png;base64,aGVsbG8=','width':100,'height':100,'scenario':'custom'}],
            'messages':[{'id':str(i),'role':'user' if i%2==0 else 'assistant','text':'Preference example '+str(i)} for i in range(turns*2)],
            'formula':'','rows':[],'createdAt':stamp,'updatedAt':stamp,'pinned':False}

def setup(tmp_path,turns=2):
    store=SessionStore(tmp_path);store.save(session(turns));return store,MemoryManager(store)

def events(store):
    with store.connection() as db:path=store.root/db.execute('SELECT journal FROM sessions').fetchone()['journal']
    return path,store.read_journal(path)

def test_blob_refs_full_history_stable_path_and_recovery(tmp_path):
    store,memory=setup(tmp_path,120);before=store.get('memory-test');path,records=events(store)
    assert len(before['messages'])==240
    assert 'aGVsbG8=' not in path.read_text(encoding='utf-8')
    assert list((tmp_path/'data/images/local').glob('*'))
    before['title']='Changed title';before['updatedAt']='2030-01-01T00:00:00Z';store.save(before)
    assert events(store)[0]==path
    with store.connection() as db:db.execute('DELETE FROM sessions')
    restored=SessionStore(tmp_path)
    assert restored.get('memory-test')==before
    assert len(restored.get('memory-test')['messages'])==240

def test_outbox_retries_event_once_after_append_before_commit(tmp_path,monkeypatch):
    store,memory=setup(tmp_path)
    path,records=events(store)
    original=store.flush
    monkeypatch.setattr(store,'flush',lambda:None)
    store.event('memory-test','tool_call',{'name':'synthetic'})
    with store.connection() as db:row=db.execute('SELECT * FROM outbox WHERE delivered=0').fetchone()
    item=json.loads(row['body']);item['seq']=len(records)+1
    with path.open('ab') as stream:stream.write((json_text(item)+'\n').encode())
    monkeypatch.setattr(store,'flush',original);store.flush();store.flush()
    records=events(store)[1]
    assert sum(record['event_id']==row['event_id'] for record in records)==1
    with store.connection() as db:assert db.execute('SELECT COUNT(*) FROM outbox WHERE delivered=0').fetchone()[0]==0

def test_partial_tail_is_backed_up_and_completed_corruption_errors(tmp_path):
    store,_=setup(tmp_path);path,records=events(store)
    with path.open('ab') as stream:stream.write(b'{"partial":')
    assert store.read_journal(path)==records
    assert list((tmp_path/'backups/state').glob('torn-*.bin'))
    with path.open('ab') as stream:stream.write(b'broken completed line\n')
    with pytest.raises(RuntimeError,match='Corrupt'):store.read_journal(path)

def test_delete_cancels_pending_and_does_not_remove_shared_image(tmp_path,monkeypatch):
    store,_=setup(tmp_path);path,_=events(store);blob=list((tmp_path/'data/images/local').glob('*'))[0]
    monkeypatch.setattr(store,'flush',lambda:None);store.event('memory-test','run_trace',{})
    store.delete('memory-test')
    assert not path.exists() and blob.exists()
    assert SessionStore(tmp_path).get('memory-test') is None

def configure(memory,**changes):
    text=(memory.store.root/'config.toml').read_text(encoding='utf-8')
    for key,value in changes.items():
        import re
        text=re.sub(r'^'+key+r' = .*$',key+' = '+str(value),text,flags=re.M)
    atomic_write(memory.store.root/'config.toml',text)

def test_compaction_retains_ten_user_turns_and_covers_every_message(tmp_path):
    store,memory=setup(tmp_path,12)
    configure(memory,auto_compact_token_limit=2100)
    captured=[]
    async def summarize(summary,messages,budget):captured.append((summary,[m['id'] for m in messages]));return 'Confirmed cumulative summary'
    plan=asyncio.run(memory.plan('memory-test','Current question',0,summarize))
    assert len(plan['history'])==20 and sum(m['role']=='user' for m in plan['history'])==10
    path,records=events(store);windows=[r['payload'] for r in records if r['type']=='compacted']
    assert windows[0]['covered_message_ids']==['0','1','2','3']
    assert windows[0]['covered_message_ids']+windows[0]['retained_message_ids']==[str(i) for i in range(24)]
    body=store.get('memory-test');body['messages'] += [{'id':'24','role':'user','text':'New turn'},{'id':'25','role':'assistant','text':'New answer'}];store.save(body)
    plan=asyncio.run(memory.plan('memory-test','Next question',0,summarize))
    assert captured[-1]==('Confirmed cumulative summary',['4','5'])
    windows=[r['payload'] for r in events(store)[1] if r['type']=='compacted']
    assert windows[1]['previous_window_id']==windows[0]['id']
    body=store.get('memory-test');body['messages'][0]['text']='Edited source';store.save(body)
    assert memory.valid_compaction('memory-test',body['messages']) is None
    asyncio.run(memory.plan('memory-test','After edit',0,summarize))
    assert captured[-1][0]==''
    assert len(store.get('memory-test')['messages'])==26

def test_recent_history_overflow_is_explicit_without_deleting_raw_data(tmp_path):
    store,memory=setup(tmp_path,10)
    body=store.get('memory-test')
    for message in body['messages']:message['text']='x'*1800
    store.save(body)
    async def forbidden(*args):raise AssertionError('Recent ten turns cannot be compacted')
    with pytest.raises(HTTPException) as caught:asyncio.run(memory.plan('memory-test','Question',0,forbidden))
    assert caught.value.status_code==413 and store.get('memory-test')==body

def test_source_checked_memory_invalidates_on_edit_and_delete(tmp_path):
    store,memory=setup(tmp_path)
    async def extract(messages,policy):
        return {'memories':[
          {'kind':'preference','text':'Use concise answers','source_message_ids':['0'],'evidence':'Preference example 0'},
          {'kind':'preference','text':'Unverified assistant suggestion','source_message_ids':['1'],'evidence':'Preference example 1'},
          {'kind':'fact','text':'Missing source','source_message_ids':['missing'],'evidence':'Missing source'},
          {'kind':'fact','text':'apiKey=top-secret-123','source_message_ids':['0'],'evidence':'Preference example 0'}]}
    # Default idle rule prevents a background extraction of an active session.
    assert asyncio.run(memory.generate(extract))['processed']==0
    report=asyncio.run(memory.generate(extract,manual=True))
    assert report['stored']==1 and memory.retrieve('anything')=='- Use concise answers'
    assert 'memory-test' in (tmp_path/'memories/local/MEMORY.md').read_text()
    assert asyncio.run(memory.generate(extract,manual=True))['processed']==0
    body=store.get('memory-test');body['messages'][0]['text']='Changed source';store.save(body);memory.publish()
    assert memory.retrieve('anything')=='' and 'Use concise answers' not in (tmp_path/'memories/local/MEMORY.md').read_text()
    store.delete('memory-test');memory.publish()
    assert not list((tmp_path/'memories/local/rollout_summaries').glob('*.md'))

def test_legacy_migration_preserves_all_tables_and_is_idempotent(tmp_path):
    source=tmp_path/'old.sqlite';config=tmp_path/'old.json';root=tmp_path/'snapmind'
    with sqlite3.connect(source) as db:
        db.execute('CREATE TABLE sessions(id TEXT PRIMARY KEY,body TEXT,updated_at TEXT)')
        body=session();db.execute('INSERT INTO sessions VALUES(?,?,?)',(body['id'],json_text(body),body['updatedAt']))
        db.execute('CREATE TABLE app_settings(name TEXT PRIMARY KEY,body TEXT)');db.execute('INSERT INTO app_settings VALUES(?,?)',('fixture','unchanged'))
    config.write_text('{"schemaVersion":1,"models":[]}',encoding='utf-8')
    migrate_legacy(root,source,config);migrate_legacy(root,source,config)
    store=SessionStore(root);store.import_sessions(root/'data/snapmind.sqlite3')
    assert store.get(body['id'])==body
    with sqlite3.connect(root/'data/snapmind.sqlite3') as db:
        assert db.execute('SELECT body FROM app_settings').fetchone()[0]=='unchanged'
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='sessions'").fetchone()
    with sqlite3.connect(source) as db:assert db.execute('SELECT COUNT(*) FROM sessions').fetchone()[0]==1
    assert (root/'backups/legacy/models.json').read_bytes()==config.read_bytes()
    assert json.loads((root/'backups/legacy/migration.json').read_text())['status']=='complete'

def test_legacy_conflict_never_overwrites_destination(tmp_path):
    config=tmp_path/'old.json';config.write_text('{}');root=tmp_path/'snapmind'
    atomic_write(root/'models.json','{"different":true}')
    with pytest.raises(RuntimeError,match='conflicts'):migrate_legacy(root,tmp_path/'absent.sqlite',config)
    assert (root/'models.json').read_text()=='{"different":true}'

def test_durable_image_api_uses_authoritative_history_and_idempotent_run(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_HOME',str(tmp_path/'snapmind'))
    monkeypatch.delenv('SNAPMIND_DATA_DIR',raising=False)
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'snapmind/models.json'))
    sys.modules.pop('backend.app.main',None);module=importlib.import_module('backend.app.main')
    monkeypatch.setattr(module,'get_active_profile',lambda _:None)
    calls=[]
    async def fake(profile,assets,selected,prompt,history,*args,**kwargs):
        calls.append([h.text for h in history]);assert CONTEXT.get() is not None
        return {'action':'chat','assetId':None,'answer':'Synthetic answer','payload':{}}
    monkeypatch.setattr(module,'run_agent',fake)
    request={'sessionId':'api-memory-test','turnId':'first','prompt':'Question 1','assets':[],'history':[]}
    with TestClient(module.app) as client:
        assert client.post('/api/capture/conversation',json=request).status_code==200
        assert client.post('/api/capture/conversation',json=request).status_code==200
        assert len(calls)==1
        request|={'turnId':'second','prompt':'Question 2','history':[{'role':'user','text':'Untrusted truncated client history'}]}
        assert client.post('/api/capture/conversation',json=request).status_code==200
        assert calls[-1]==['Question 1','Synthetic answer']
        saved=client.get('/api/sessions').json()[0]
        assert len(saved['messages'])==4
        request['prompt']='Different same turn'
        assert client.post('/api/capture/conversation',json=request).status_code==409
        assert client.get('/api/memories').json()['pending_events']==0
        assert client.put('/api/settings/preferences',json={'snapmind-theme':'dark'}).status_code==200
        assert client.put('/api/settings/preferences',json={'snapmind-language':'en'}).json()=={'snapmind-theme':'dark','snapmind-language':'en'}
        assert client.delete('/api/sessions/api-memory-test').status_code==200
        assert client.get('/api/sessions').json()==[]

def test_failed_model_request_keeps_user_prompt_and_can_retry(tmp_path,monkeypatch):
    store,memory=setup(tmp_path,0)
    from backend.app.conversation_runtime import ConversationRuntime
    from types import SimpleNamespace
    runtime=ConversationRuntime(store,memory)
    context=SimpleNamespace(sessionId='memory-test',turnId='retry-turn',assets=[],selectedId=None,history=[])
    async def fail(_):raise HTTPException(502,'Synthetic failure')
    with pytest.raises(HTTPException):asyncio.run(runtime.image_run(context,'Preserve this question',None,{},None,None,None,fail))
    assert store.get('memory-test')['messages'][0]['text']=='Preserve this question'
    async def success(history):return {'action':'chat','assetId':None,'answer':'Recovered','payload':{}}
    asyncio.run(runtime.image_run(context,'Preserve this question',None,{},None,None,None,success))
    assert [m['role'] for m in store.get('memory-test')['messages']]==['user','assistant']

def test_data_url_text_is_preserved_as_message_text_not_an_image(tmp_path):
    store,_=setup(tmp_path)
    body=store.get('memory-test');body['messages'][0]['text']='data:image/png;base64,this is a literal question'
    store.save(body)
    assert store.get('memory-test')['messages'][0]['text']==body['messages'][0]['text']

def test_workspace_response_is_durable_before_stream_and_retry_is_idempotent(tmp_path,monkeypatch):
    monkeypatch.setenv('SNAPMIND_HOME',str(tmp_path/'snapmind'))
    monkeypatch.delenv('SNAPMIND_DATA_DIR',raising=False)
    monkeypatch.setenv('SNAPMIND_CONFIG_FILE',str(tmp_path/'snapmind/models.json'))
    sys.modules.pop('backend.app.main',None);module=importlib.import_module('backend.app.main')
    monkeypatch.setattr(module,'get_active_profile',lambda _: {'vision':False})
    calls=[]
    async def complete(profile,body,selected,action,prompt,db):
        calls.append(prompt);assert CONTEXT.get() is not None
        return {'text':'Durable synthetic reply','kind':'text'}
    monkeypatch.setattr(module,'complete',complete)
    body=session(0,'workspace-durable');body['messages']=[{'id':'original-question','role':'user','text':'Synthetic question'}]
    with TestClient(module.app) as client:
        request={'session':body,'action':'chat','prompt':'Synthetic question'}
        with client.stream('POST','/api/chat',json=request) as response:
            assert response.status_code==200
            assert module.STORE.get(body['id'])['messages'][-1]['text']=='Durable synthetic reply'
        repeated=client.post('/api/chat',json=request)
        assert repeated.status_code==200 and len(calls)==1
        assert len(module.STORE.get(body['id'])['messages'])==2
        # Reconstructing a lost state projection also restores request deduplication.
        with module.STORE.connection() as db:
            db.execute('DELETE FROM sessions');db.execute('DELETE FROM runs')
        recovered=SessionStore(module.HOME)
        with recovered.connection() as db:assert db.execute("SELECT status FROM runs WHERE id=?",(body['id']+':original-question',)).fetchone()['status']=='complete'

def test_conversation_routing_records_real_selected_tool(tmp_path):
    from backend.app.image_conversation import converse
    from backend.app.image_tools import png_data
    from types import SimpleNamespace
    from PIL import Image
    store,memory=setup(tmp_path,0)
    asset=SimpleNamespace(id='a',name='Synthetic',data=png_data(Image.new('RGB',(100,100),'white')),width=100,height=100)
    records=[]
    token=CONTEXT.set({'trace':lambda kind,payload:records.append((kind,payload))})
    try:
        result=asyncio.run(converse(None,[asset],'a','Extra image region',[],[],[],None,None,None,'region',arguments={'bbox':[10,10,50,50]}))
    finally:CONTEXT.reset(token)
    assert result['action']=='region' and records[0][0]=='tool_call' and records[0][1]['name']=='region'
