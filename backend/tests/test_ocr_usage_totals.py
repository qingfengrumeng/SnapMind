import sqlite3
from concurrent.futures import ThreadPoolExecutor
from backend.app import ocr_usage
from backend.tests.test_api import client


def config(model='PP-StructureV3',limit=20):
    return {'model':model,'dailyLimit':limit,'apiKeyProtected':None}


def test_cloud_ocr_counts_with_llm_without_inventing_tokens(client):
    import sys
    path=sys.modules['backend.app.main'].DB
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO model_usage(id,model,input_tokens,output_tokens,created_at) VALUES(?,?,?,?,?)',('llm','test-vision',120,30,'2026-10-07'))
    assert ocr_usage.reserve(path,config()) is None
    assert ocr_usage.reserve(path,config('PaddleOCR-VL-1.6')) is None
    result=client.get('/api/usage').json()
    assert result['requests']==3 and result['llmRequests']==1 and result['ocrRequests']==2
    assert result['inputTokens']==120 and result['outputTokens']==30
    assert result['unreportedRequests']==2
    rows={row['model']:row for row in result['models']}
    assert rows['PP-StructureV3']['requests']==1 and rows['PaddleOCR-VL-1.6']['requests']==1
    assert rows['PP-StructureV3']['kind']=='ocr' and rows['PP-StructureV3']['inputTokens'] is None


def test_historical_totals_and_new_reservations_are_not_duplicated(client,monkeypatch):
    import sys
    path=sys.modules['backend.app.main'].DB
    with sqlite3.connect(path) as db:
        ocr_usage.schema(db)
        db.executemany('INSERT INTO ocr_daily_usage(account,day,submitted) VALUES(?,?,?)',[
            (ocr_usage.account(config()),ocr_usage.today(),7),('old-key','2026-10-01',4)])
    assert ocr_usage.reserve(path,config()) is None
    for _ in range(2):
        result=client.get('/api/usage').json()
        assert result['requests']==12 and result['ocrRequests']==12 and result['llmRequests']==0
        rows={row['model']:row for row in result['models']}
        assert rows['PaddleOCR（历史调用）']['requests']==11 and rows['PaddleOCR（历史调用）']['historical']
        assert rows['PP-StructureV3']['requests']==1
    monkeypatch.setattr(ocr_usage,'today',lambda:'2099-01-02')
    assert ocr_usage.reserve(path,config()) is None
    assert client.get('/api/usage').json()['ocrRequests']==13


def test_atomic_model_counts_and_bypassed_cloud_not_counted(client):
    import sys
    path=sys.modules['backend.app.main'].DB
    with ThreadPoolExecutor(max_workers=6) as pool:
        results=list(pool.map(lambda _:ocr_usage.reserve(path,config(limit=2)),range(6)))
    assert results.count(None)==2
    assert client.get('/api/usage').json()['ocrRequests']==2
    assert ocr_usage.reserve(path,config(limit=2))=='daily-limit'
    assert client.get('/api/usage').json()['requests']==2
    ocr_usage.pause_cloud(path,config(),'unavailable')
    assert ocr_usage.reserve(path,config())=='unavailable'
    assert client.get('/api/usage').json()['requests']==2
