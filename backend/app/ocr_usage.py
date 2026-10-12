"""Atomic per-token daily submission budget and persistent provider cooldown."""
from datetime import datetime, timedelta, timezone
import hashlib
import sqlite3
import time
from uuid import uuid4
from .model_profiles import unprotect_key

SHANGHAI = timezone(timedelta(hours=8))

def today():
    return datetime.now(SHANGHAI).date().isoformat()

def account(config):
    return hashlib.sha256((unprotect_key(config.get('apiKeyProtected')) or '').encode()).hexdigest()

def schema(db):
    db.execute('CREATE TABLE IF NOT EXISTS ocr_daily_usage (account TEXT NOT NULL, day TEXT NOT NULL, submitted INTEGER NOT NULL DEFAULT 0, blocked_until REAL NOT NULL DEFAULT 0, reason TEXT, PRIMARY KEY(account,day))')
    db.execute('CREATE TABLE IF NOT EXISTS ocr_model_usage (account TEXT NOT NULL, day TEXT NOT NULL, model TEXT NOT NULL, submitted INTEGER NOT NULL DEFAULT 0, PRIMARY KEY(account,day,model))')
    db.execute('CREATE TABLE IF NOT EXISTS ocr_submission_usage (id TEXT PRIMARY KEY, account TEXT NOT NULL, day TEXT NOT NULL, model TEXT NOT NULL, submitted_at TEXT NOT NULL)')
    db.execute('CREATE INDEX IF NOT EXISTS ocr_submission_day ON ocr_submission_usage(day)')

def model_totals(db):
    """All-time task submissions; old daily counters have no recoverable model ID."""
    schema(db)
    # Read model and legacy counters together so concurrent reservations cannot
    # appear once as a historical request and again as a model request.
    return db.execute('''
        SELECT model,SUM(submitted),0 FROM ocr_model_usage GROUP BY model HAVING SUM(submitted)>0
        UNION ALL
        SELECT 'PaddleOCR（历史调用）',SUM(MAX(d.submitted-COALESCE(m.total,0),0)),1
        FROM ocr_daily_usage d LEFT JOIN
          (SELECT account,day,SUM(submitted) AS total FROM ocr_model_usage GROUP BY account,day) m
        ON d.account=m.account AND d.day=m.day
        HAVING SUM(MAX(d.submitted-COALESCE(m.total,0),0))>0
    ''').fetchall()

def usage_summary(path,config):
    with sqlite3.connect(path) as db:
        schema(db)
        row=db.execute('SELECT submitted,blocked_until,reason FROM ocr_daily_usage WHERE account=? AND day=?',(account(config),today())).fetchone()
    used,until,reason = row or (0,0,None)
    limit=config.get('dailyLimit',20000)
    limited=used>=limit
    cooling=until>time.time()
    return {'date':today(),'timezone':'Asia/Shanghai','dailyLimit':limit,'submitted':used,'remaining':max(0,limit-used),
            'cloudAvailable':bool(config.get('enabled') and config.get('apiKeyProtected') and not limited and not cooling),
            'reason':'daily-limit' if limited else reason if cooling else None,
            'retryAfterSeconds':max(0,round(until-time.time())) if cooling else 0,'counterScope':'this-installation'}

def reserve(path,config):
    with sqlite3.connect(path,timeout=10) as db:
        schema(db)
        db.execute('BEGIN IMMEDIATE')
        key,day=account(config),today()
        db.execute('INSERT OR IGNORE INTO ocr_daily_usage(account,day) VALUES(?,?)',(key,day))
        used,until,reason=db.execute('SELECT submitted,blocked_until,reason FROM ocr_daily_usage WHERE account=? AND day=?',(key,day)).fetchone()
        if used>=config.get('dailyLimit',20000): return 'daily-limit'
        if until>time.time(): return reason or 'unavailable'
        # Reserve before sending; ambiguous network failures can still consume cloud quota.
        db.execute('UPDATE ocr_daily_usage SET submitted=submitted+1 WHERE account=? AND day=?',(key,day))
        db.execute('INSERT INTO ocr_model_usage(account,day,model,submitted) VALUES(?,?,?,1) ON CONFLICT(account,day,model) DO UPDATE SET submitted=submitted+1',(key,day,config.get('model','PaddleOCR')))
        db.execute('INSERT INTO ocr_submission_usage(id,account,day,model,submitted_at) VALUES(?,?,?,?,?)',(str(uuid4()),key,day,config.get('model','PaddleOCR'),datetime.now(timezone.utc).isoformat()))
    return None

def pause_cloud(path,config,reason):
    now=time.time()
    until=now+60
    if reason=='cloud-quota':
        next_day=datetime.now(SHANGHAI).replace(hour=0,minute=0,second=0,microsecond=0)+timedelta(days=1)
        until=next_day.timestamp()
    with sqlite3.connect(path) as db:
        schema(db)
        db.execute('INSERT INTO ocr_daily_usage(account,day,blocked_until,reason) VALUES(?,?,?,?) ON CONFLICT(account,day) DO UPDATE SET blocked_until=excluded.blocked_until,reason=excluded.reason',(account(config),today(),until,reason))
