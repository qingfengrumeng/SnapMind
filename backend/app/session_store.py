"""SQLite query projection + transactional outbox + append-only session rollouts."""
import base64
import hashlib
import json
import re
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from contextlib import contextmanager,closing
from .local_storage import atomic_write, file_lock, json_text

def now(): return datetime.now(timezone.utc).isoformat()
def fingerprint(value): return hashlib.sha256(json_text(value).encode('utf-8')).hexdigest()

class SessionStore:
    def __init__(self, root):
        self.root = Path(root)
        self.path = self.root / 'state_1.sqlite'
        self.lock = self.root / 'thread-writer-locks/state.lock'
        with self.connection() as db:
            db.executescript('''
              CREATE TABLE IF NOT EXISTS sessions(id TEXT PRIMARY KEY, body TEXT NOT NULL, updated_at TEXT NOT NULL, journal TEXT NOT NULL UNIQUE, revision TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS outbox(event_id TEXT NOT NULL UNIQUE, session_id TEXT NOT NULL, body TEXT NOT NULL, delivered INTEGER NOT NULL DEFAULT 0, ordinal INTEGER PRIMARY KEY AUTOINCREMENT);
            ''')
            db.executescript('''
              CREATE TABLE IF NOT EXISTS compactions(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,status TEXT NOT NULL,request TEXT NOT NULL,result TEXT,updated_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS memories(id TEXT PRIMARY KEY,session_id TEXT NOT NULL,revision TEXT NOT NULL,body TEXT NOT NULL,created_at TEXT NOT NULL);
              CREATE TABLE IF NOT EXISTS memory_jobs(session_id TEXT PRIMARY KEY,revision TEXT NOT NULL,status TEXT NOT NULL,updated_at TEXT NOT NULL);
            ''')
        self.recover()
        self.flush()

    @contextmanager
    def connection(self):
        db = sqlite3.connect(self.path, timeout=30)
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA journal_mode=DELETE')
        db.execute('PRAGMA synchronous=FULL')
        try:
            with db:yield db
        finally:db.close()

    def pack(self, value, image=False):
        """Externalize image data fields, including generated tool results, as blob references."""
        if isinstance(value, dict): return {key:self.pack(item,image=key=='data') for key,item in value.items()}
        if isinstance(value, list): return [self.pack(item) for item in value]
        if image and isinstance(value, str) and re.match(r'^data:image/(png|jpeg|webp);base64,', value):
            prefix, content = value.split(',',1)
            raw = base64.b64decode(content, validate=True)
            extension = prefix.split('/')[1].split(';')[0]
            name = hashlib.sha256(raw).hexdigest()+'.'+extension
            relative = 'data/images/local/'+name
            path = self.root / relative
            if path.exists():
                if path.read_bytes() != raw: raise RuntimeError('Image checksum conflict')
            else: atomic_write(path,raw)
            return {'$image':relative, 'mime':prefix[5:].split(';')[0]}
        return value

    def unpack(self, value):
        if isinstance(value,dict):
            if '$image' in value:
                path = (self.root / value['$image']).resolve()
                if not path.is_relative_to((self.root/'data/images/local').resolve()): raise ValueError('Invalid image reference')
                raw = path.read_bytes()
                if hashlib.sha256(raw).hexdigest() != path.stem: raise RuntimeError('Image checksum mismatch')
                return 'data:'+value['mime']+';base64,'+base64.b64encode(raw).decode('ascii')
            return {key:self.unpack(item) for key,item in value.items()}
        if isinstance(value,list): return [self.unpack(item) for item in value]
        return value

    def _event(self, db, session_id, kind, payload):
        event = {'event_id':str(uuid4()),'timestamp':now(),'type':kind,'payload':payload}
        db.execute('INSERT INTO outbox(event_id,session_id,body) VALUES(?,?,?)', (event['event_id'],session_id,json_text(event)))

    def save(self, session):
        if not re.fullmatch(r'[a-zA-Z0-9-]{1,80}',session['id']): raise ValueError('Invalid session ID')
        packed = self.pack(session)
        revision = fingerprint(packed.get('messages',[]))
        with file_lock(self.lock), self.connection() as db:
            old = db.execute('SELECT * FROM sessions WHERE id=?',(session['id'],)).fetchone()
            if old:
                journal = old['journal']; previous = json.loads(old['body'])
            else:
                # Stable UTC creation date; title and later activity never change the path.
                try: created = datetime.fromisoformat(session['createdAt'].replace('Z','+00:00')).astimezone(timezone.utc)
                except (ValueError,KeyError): created = datetime.now(timezone.utc)
                journal = created.strftime('sessions/%Y/%m/%d/rollout-%Y-%m-%dT%H-%M-%S-')+session['id']+'.jsonl'
                previous = {}
                self._event(db,session['id'],'session_meta',{'id':session['id'],'created_at':session.get('createdAt',now()),'owner':'local','format_version':1})
            prior = {m['id']:m for m in previous.get('messages',[])}
            current = {m['id']:m for m in packed.get('messages',[])}
            if len(current) != len(packed.get('messages',[])): raise ValueError('Duplicate message IDs')
            for key in prior.keys()-current.keys(): self._event(db,session['id'],'message_deleted',{'id':key})
            for key,message in current.items():
                if prior.get(key)!=message:
                    self._event(db,session['id'],'response_item',{'message':message})
                    request=message.get('imageRequest')
                    if request and request!=prior.get(key,{}).get('imageRequest'):
                        self._event(db,session['id'],'run_trace',{'message_id':key,'request':request})
                        if request.get('context'):self._event(db,session['id'],'context_snapshot',{'message_id':key,'context':request['context']})
                    if message.get('role')=='assistant' and message.get('action'):
                        self._event(db,session['id'],'tool_result',{'message_id':key,'action':message['action'],'text':message.get('text',''),'result':message.get('imageOutput') or message.get('imageResult')})
            if old and old['revision']!=revision:
                # Invalid extraction is never read or injected while a new one is pending.
                db.execute('DELETE FROM memories WHERE session_id=?',(session['id'],))
            db.execute('INSERT INTO sessions VALUES(?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET body=excluded.body,updated_at=excluded.updated_at,revision=excluded.revision',
                       (session['id'],json_text(packed),session['updatedAt'],journal,revision))
            if previous != packed:
                metadata={key:value for key,value in packed.items() if key!='messages'}
                self._event(db,session['id'],'session_state',{'session':metadata,'message_ids':list(current),'revision':revision})
        self.flush()

    def get(self, session_id):
        with self.connection() as db: row=db.execute('SELECT body FROM sessions WHERE id=?',(session_id,)).fetchone()
        return self.unpack(json.loads(row['body'])) if row else None

    def list(self):
        self.flush()
        with self.connection() as db: rows=db.execute('SELECT body FROM sessions ORDER BY updated_at DESC').fetchall()
        return [self.unpack(json.loads(row['body'])) for row in rows]

    def image_history(self):
        """List metadata without loading image files or message bodies into the UI."""
        with self.connection() as db:
            rows=db.execute('SELECT body FROM sessions ORDER BY updated_at DESC').fetchall()
        result=[]
        for row in rows:
            session=json.loads(row['body'])
            if not session.get('imageConversation') or not session.get('messages'):continue
            result.append({key:session[key] for key in ('id','title','createdAt','updatedAt','pinned')}|({'hasVoiceCall':True} if session.get('voiceCall') else {}))
        return result

    def patch_image_metadata(self,session_id,title=None,pinned=None):
        with file_lock(self.lock),self.connection() as db:
            row=db.execute('SELECT body,revision FROM sessions WHERE id=?',(session_id,)).fetchone()
            if not row:return None
            session=json.loads(row['body'])
            if not session.get('imageConversation'):return None
            if title is not None:session['title']=title;session['imageConversation']['titleGenerated']=True
            if pinned is not None:session['pinned']=pinned
            session['updatedAt']=now()
            db.execute('UPDATE sessions SET body=?,updated_at=? WHERE id=?',(json_text(session),session['updatedAt'],session_id))
            self._event(db,session_id,'session_state',{'session':{key:value for key,value in session.items() if key!='messages'},'message_ids':[m['id'] for m in session.get('messages',[])],'revision':row['revision']})
        self.flush()
        return {key:session[key] for key in ('id','title','createdAt','updatedAt','pinned')}|{'titleGenerated':session['imageConversation'].get('titleGenerated',False)}|({'hasVoiceCall':True} if session.get('voiceCall') else {})

    def event(self, session_id, kind, payload):
        packed=self.pack(payload)
        with file_lock(self.lock), self.connection() as db:
            if not db.execute('SELECT 1 FROM sessions WHERE id=?',(session_id,)).fetchone(): raise KeyError(session_id)
            self._event(db,session_id,kind,packed)
        self.flush()

    def read_journal(self, path):
        path=Path(path)
        if not path.exists(): return []
        raw=path.read_bytes()
        # Only an incomplete last line may be repaired, never a completed corrupt record.
        boundary=raw.rfind(b'\n')+1
        if boundary<len(raw):
            atomic_write(self.root/'backups/state'/('torn-'+str(uuid4())+'.bin'),raw[boundary:])
            with path.open('r+b') as output: output.truncate(boundary);output.flush();__import__('os').fsync(output.fileno())
        events=[];identifiers=set()
        for line in raw[:boundary].splitlines():
            try: item=json.loads(line)
            except (ValueError,UnicodeError) as error: raise RuntimeError('Corrupt completed session event') from error
            if not isinstance(item,dict) or item.get('seq')!=len(events)+1 or not isinstance(item.get('event_id'),str) or not isinstance(item.get('payload'),dict) or not isinstance(item.get('type'),str): raise RuntimeError('Invalid session event sequence')
            if item['event_id'] in identifiers:raise RuntimeError('Duplicate session event ID')
            identifiers.add(item['event_id'])
            events.append(item)
        return events

    def flush(self):
        with file_lock(self.lock), self.connection() as db:
            rows=db.execute('SELECT o.*,s.journal FROM outbox o JOIN sessions s ON s.id=o.session_id WHERE delivered=0 ORDER BY ordinal').fetchall()
            journals={}
            for row in rows:
                path=self.root/row['journal']
                if path not in journals: journals[path]=self.read_journal(path)
                records=journals[path]
                if row['event_id'] not in {event['event_id'] for event in records}:
                    event=json.loads(row['body']);event['seq']=len(records)+1
                    path.parent.mkdir(parents=True,exist_ok=True)
                    with path.open('ab') as output:
                        output.write((json_text(event)+'\n').encode('utf-8'));output.flush();__import__('os').fsync(output.fileno())
                    records.append(event)
                db.execute("UPDATE outbox SET delivered=1,body='' WHERE event_id=?",(row['event_id'],))
            index=[{'id':row['id'],'path':row['journal'],'updated_at':row['updated_at'],'title':json.loads(row['body'])['title']} for row in db.execute('SELECT * FROM sessions ORDER BY updated_at DESC')]
            atomic_write(self.root/'session_index.jsonl',''.join(json_text(item)+'\n' for item in index))

    def delete(self, session_id):
        with file_lock(self.lock), self.connection() as db:
            row=db.execute('SELECT journal FROM sessions WHERE id=?',(session_id,)).fetchone()
            for table in ('outbox','runs','compactions','memories','memory_jobs'): db.execute('DELETE FROM '+table+' WHERE session_id=?',(session_id,))
            db.execute('DELETE FROM sessions WHERE id=?',(session_id,))
            # Tombstone first: a crash before journal unlink cannot resurrect a deleted session.
            if row:
                atomic_write(self.root/'backups/state'/('deleted-'+session_id+'.json'),json_text({'id':session_id,'deleted_at':now()}))
                (self.root/row['journal']).unlink(missing_ok=True)
        self.flush()

    def recover(self):
        with file_lock(self.lock), self.connection() as db:
            # Rebuild absent projections without replaying over pending committed updates.
            for path in (self.root/'sessions').rglob('rollout-*.jsonl'):
                events=self.read_journal(path)
                states=[];messages={}
                for event in events:
                    payload=event['payload']
                    if event['type']=='response_item':
                        message=payload['message'];messages[message['id']]=message
                    elif event['type']=='message_deleted':messages.pop(payload['id'],None)
                    elif event['type']=='session_state':
                        snapshot=dict(payload);session=dict(payload['session'])
                        if 'messages' not in session:
                            try:session['messages']=[messages[mid] for mid in payload['message_ids']]
                            except KeyError as error:raise RuntimeError('Missing source event during session recovery') from error
                        snapshot['session']=session;states.append(snapshot)
                if not states: continue
                snapshot=states[-1];session=snapshot['session'];sid=session['id']
                tombstone=self.root/'backups/state'/('deleted-'+sid+'.json')
                if tombstone.exists():
                    deleted=json.loads(tombstone.read_text(encoding='utf-8'))['deleted_at']
                    creation=next((event['timestamp'] for event in events if event['type']=='session_meta'),'')
                    if creation<=deleted:continue
                if not db.execute('SELECT 1 FROM sessions WHERE id=?',(sid,)).fetchone():
                    db.execute('INSERT INTO sessions VALUES(?,?,?,?,?)',(sid,json_text(session),session['updatedAt'],str(path.relative_to(self.root)),snapshot['revision']))
                    for event in events:
                        if event['type']=='compacted':
                            payload=event['payload']
                            db.execute('INSERT OR IGNORE INTO compactions VALUES(?,?,?,?)',(payload['id'],sid,json_text(payload),event['timestamp']))
                        elif event['type'] in ('tool_call','run_trace') and 'request' in event['payload']:
                            payload=event['payload']
                            db.execute('INSERT OR REPLACE INTO runs VALUES(?,?,?,?,?,?)',(payload['run_id'],sid,'interrupted',json_text(payload['request']),None,event['timestamp']))
                        elif event['type']=='tool_result':
                            payload=event['payload']
                            db.execute('UPDATE runs SET status=?,result=?,updated_at=? WHERE id=?',('complete',json_text(payload['result']),event['timestamp'],payload['run_id']))
                        elif event['type']=='memory_extraction' and event['payload']['revision']==snapshot['revision']:
                            for candidate in event['payload']['candidates']:
                                mid=fingerprint([sid,fingerprint(candidate['text'])])
                                db.execute('INSERT OR REPLACE INTO memories VALUES(?,?,?,?,?)',(mid,sid,snapshot['revision'],json_text(candidate),event['timestamp']))
                            db.execute('INSERT OR REPLACE INTO memory_jobs VALUES(?,?,?,?)',(sid,snapshot['revision'],'complete',event['timestamp']))

    def import_sessions(self, business):
        with sqlite3.connect(business) as db:
            exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='sessions'").fetchone()
            if not exists:return
            rows=db.execute('SELECT body FROM sessions').fetchall()
        for (body,) in rows:
            session=json.loads(body);existing=self.get(session['id'])
            if existing is not None and existing!=session: raise RuntimeError('Session migration conflict')
            self.save(session)
            if self.get(session['id'])!=session: raise RuntimeError('Session migration verification failed')
        # SQLite backup protects the full old table before removing the business projection.
        if rows:
            backup=self.root/'backups/business/pre-session-migration.sqlite3'
            backup.parent.mkdir(parents=True,exist_ok=True)
            if not backup.exists():
                with closing(sqlite3.connect(business)) as source,closing(sqlite3.connect(backup)) as destination:source.backup(destination)
        with sqlite3.connect(business) as db:db.execute('DROP TABLE sessions')
