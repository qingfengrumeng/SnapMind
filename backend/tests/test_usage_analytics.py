import sqlite3
import sys
import asyncio
from types import SimpleNamespace
import httpx
import pytest
from backend.tests.test_api import client
from backend.app import ocr_usage
from backend.app.model_inference import cached_input_tokens


@pytest.mark.parametrize('usage,expected', [
    ({'prompt_cache_hit_tokens':40},40),
    ({'prompt_tokens_details':{'cached_tokens':60}},60),
    ({'prompt_tokens_details':{'cached_tokens':0}},0),
    ({},None),({'prompt_cache_hit_tokens':True},None),
    ({'prompt_cache_hit_tokens':101},None),({'prompt_cache_hit_tokens':-1},None),
    ({'prompt_tokens_details':[]},None),
])
def test_cache_fields_are_actual_valid_subsets(usage,expected):
    assert cached_input_tokens(usage,100)==expected


def analytics(client,kind='llm',start='2026-10-09',end='2026-10-09'):
    response=client.get('/api/usage/analytics',params={'kind':kind,'start':start,'end':end})
    assert response.status_code==200,response.text
    return response.json()


def test_hourly_boundary_cache_and_legacy_data(client):
    with sqlite3.connect(sys.modules['backend.app.main'].DB) as db:
        db.executemany('INSERT INTO model_usage(id,model,input_tokens,output_tokens,created_at,tokens_reported,cached_input_tokens) VALUES(?,?,?,?,?,?,?)',[
            ('before','a',999,999,'2026-10-08T15:59:59Z',1,900),
            ('midnight','a',100,20,'2026-10-08T16:00:00Z',1,40),
            ('last','a',50,10,'2026-10-09T15:59:59Z',1,None),
            ('after','a',999,999,'2026-10-09T16:00:00Z',1,900),
            ('unknown','b',20,5,'2026-10-09',1,None),
            ('no-tokens','b',0,0,'2026-10-09T03:00:00+08:00',0,None),
        ])
    data=analytics(client); summary=data['summary']
    assert summary['requests']==4 and summary['totalTokens']==205
    assert summary['cachedInputTokens']==40 and summary['uncachedInputTokens']==130
    assert summary['cacheHitRate']==23.53 and summary['cacheReportedRequests']==1
    assert summary['unreportedRequests']==1 and summary['unbucketedRequests']==1
    assert len(data['trend'])==24
    assert data['trend'][0]['requests']==1 and data['trend'][23]['requests']==1
    assert sum(point['requests'] for point in data['trend'])==3
    models={row['model']:row for row in data['models']}
    assert models['b']['cachedInputTokens']==0 and models['b']['uncachedInputTokens']==20
    assert data['trend'][23]['cachedInputTokens']==0 and data['trend'][23]['uncachedInputTokens']==50
    assert data['modelTrends'][0]['points'][0]['cachedInputTokens']==40
    daily=analytics(client,start='2026-10-08',end='2026-10-10')
    assert len(daily['trend'])==3 and daily['summary']['requests']==6
    assert daily['summary']['unbucketedRequests']==0
    for snapshot in [data,daily]:
        for row in [snapshot['summary'],*snapshot['models'],*snapshot['trend'],*[p for m in snapshot['modelTrends'] for p in m['points']]]:
            assert row['inputTokens']==row['cachedInputTokens']+row['uncachedInputTokens']
            assert row['totalTokens']==row['cachedInputTokens']+row['uncachedInputTokens']+row['outputTokens']
    with sqlite3.connect(sys.modules['backend.app.main'].DB) as db:
        assert db.execute("SELECT cached_input_tokens FROM model_usage WHERE id='unknown'").fetchone()[0] is None


def test_ocr_historical_totals_and_hourly_submissions(client):
    path=sys.modules['backend.app.main'].DB
    with sqlite3.connect(path) as db:
        ocr_usage.schema(db)
        db.executemany('INSERT INTO ocr_daily_usage(account,day,submitted) VALUES(?,?,?)',[('old','2026-10-08',3),('new','2026-10-09',7)])
        db.execute('INSERT INTO ocr_model_usage(account,day,model,submitted) VALUES(?,?,?,?)',('new','2026-10-09','PP-StructureV3',5))
        db.executemany('INSERT INTO ocr_submission_usage VALUES(?,?,?,?,?)',[
            ('e1','new','2026-10-09','PP-StructureV3','2026-10-08T16:00:00Z'),
            ('e2','new','2026-10-09','PP-StructureV3','2026-10-09T15:59:59Z'),
        ])
    hourly=analytics(client,'ocr')
    assert hourly['summary']=={'requests':7,'unbucketedRequests':5}
    assert hourly['models']==[{'model':'PP-StructureV3','requests':5,'unbucketedRequests':3}]
    assert len(hourly['trend'])==24 and hourly['trend'][0]['requests']==1 and hourly['trend'][23]['requests']==1
    assert 'Token' not in str(hourly)
    daily=analytics(client,'ocr','2026-10-08','2026-10-09')
    assert daily['summary']['requests']==10 and [p['requests'] for p in daily['trend']]==[3,7]
    assert len(daily['models'])==1
    # Reading or refreshing never inserts extra submission records.
    analytics(client,'ocr')
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM ocr_submission_usage').fetchone()[0]==2


def test_empty_buckets_and_invalid_ranges(client):
    assert len(analytics(client)['trend'])==24
    assert len(analytics(client,start='2026-10-03',end='2026-10-09')['trend'])==7
    assert all(point['requests']==0 for point in analytics(client)['trend'])
    assert all(point['cachedInputTokens']==point['uncachedInputTokens']==point['outputTokens']==0 for point in analytics(client)['trend'])
    for start,end in [('bad','2026-10-09'),('2026-10-09','2026-10-08'),('2025-01-01','2026-01-02'),('2026-02-30','2026-03-01')]:
        assert client.get('/api/usage/analytics',params={'start':start,'end':end}).status_code==400


def test_reservations_add_one_event_each_and_no_events_after_limit(client):
    path=sys.modules['backend.app.main'].DB
    config={'model':'PP-StructureV3','dailyLimit':2,'apiKeyProtected':None}
    assert ocr_usage.reserve(path,config) is None
    assert ocr_usage.reserve(path,config) is None
    assert ocr_usage.reserve(path,config)=='daily-limit'
    with sqlite3.connect(path) as db:
        assert db.execute('SELECT COUNT(*) FROM ocr_submission_usage').fetchone()[0]==2


@pytest.mark.parametrize('usage,expected',[
    ({'prompt_tokens':100,'completion_tokens':20,'prompt_cache_hit_tokens':40},40),
    ({'prompt_tokens':100,'completion_tokens':20,'prompt_tokens_details':{'cached_tokens':50}},50),
    ({'prompt_tokens':100,'completion_tokens':20},None),
    ({'prompt_cache_hit_tokens':40},None),
])
def test_provider_cache_persisted_without_double_counting(client,monkeypatch,usage,expected):
    from backend.app import model_inference
    path=sys.modules['backend.app.main'].DB
    real=httpx.AsyncClient
    def handler(request):
        return httpx.Response(200,json={'choices':[{'message':{'content':'synthetic response'}}],'usage':usage})
    monkeypatch.setattr(model_inference.httpx,'AsyncClient',lambda **kw:real(transport=httpx.MockTransport(handler),**kw))
    profile={'provider':'openai-compatible','model':'synthetic','baseUrl':'http://example.invalid/v1','vision':False}
    asyncio.run(model_inference.complete(profile,SimpleNamespace(messages=[]),[],'chat','test',path))
    with sqlite3.connect(path) as db:
        row=db.execute('SELECT input_tokens,output_tokens,cached_input_tokens FROM model_usage').fetchone()
    assert row==(100,20,expected) if 'prompt_tokens' in usage else row==(0,0,None)
