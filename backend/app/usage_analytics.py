"""Beijing-time snapshots; missing cache detail counts as uncached input."""
from datetime import date, datetime, time, timedelta, timezone
import sqlite3
from fastapi import HTTPException
from .ocr_usage import schema as ocr_schema, SHANGHAI

def dates(start, end):
    today=datetime.now(SHANGHAI).date()
    try:
        first=date.fromisoformat(start) if start else today-timedelta(days=6)
        last=date.fromisoformat(end) if end else today
        if first.isoformat()!=(start or first.isoformat()) or last.isoformat()!=(end or last.isoformat()): raise ValueError()
        if first.year<1900 or last.year>9998 or last<first or (last-first).days>365: raise ValueError()
    except (ValueError,TypeError):
        raise HTTPException(400,'请选择有效的起止日期，时间范围最多为 366 天')
    return first,last

def metrics():
    return {'requests':0,'inputTokens':0,'outputTokens':0,'totalTokens':0,
            'cachedInputTokens':0,'uncachedInputTokens':0,'cacheReportedRequests':0,
            'cacheInputTokens':0,'unreportedRequests':0,'unbucketedRequests':0}

def add(target, source):
    for key in metrics(): target[key]+=source.get(key,0) or 0

def public(value, kind):
    result=dict(value)
    if kind=='ocr': return {key:result[key] for key in ('requests','unbucketedRequests')}
    result['cacheHitRate']=round(result['cachedInputTokens']/result['inputTokens']*100,2) if result['inputTokens'] else 0
    return result

def instant(value):
    stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
    return (stamp.replace(tzinfo=timezone.utc) if stamp.tzinfo is None else stamp).astimezone(SHANGHAI)

def get_usage_analytics(path,kind,start=None,end=None):
    first,last=dates(start,end)
    hourly=first==last
    bucket_keys=[f'{first.isoformat()}T{hour:02d}:00' for hour in range(24)] if hourly else [(first+timedelta(days=offset)).isoformat() for offset in range((last-first).days+1)]
    total=metrics(); models={}; buckets={key:metrics() for key in bucket_keys}; model_buckets={}
    def model(name):
        if name not in models:
            models[name]=metrics();model_buckets[name]={key:metrics() for key in bucket_keys}
        return models[name]
    def bucket(stamp): return stamp.strftime('%Y-%m-%dT%H:00') if hourly else stamp.date().isoformat()
    with sqlite3.connect(path) as db:
        ocr_schema(db)
        db.execute('BEGIN')
        if kind=='llm':
            rows=db.execute('SELECT model,input_tokens,output_tokens,created_at,tokens_reported,cached_input_tokens FROM model_usage WHERE created_at>=? AND created_at<?',((first-timedelta(days=1)).isoformat(),(last+timedelta(days=2)).isoformat())).fetchall()
            for name,in_tokens,out_tokens,created,reported,cached in rows:
                try: stamp=instant(created)
                except (ValueError,TypeError): continue
                if not first<=stamp.date()<=last: continue
                value=metrics();value.update(requests=1,inputTokens=in_tokens,outputTokens=out_tokens,totalTokens=in_tokens+out_tokens,uncachedInputTokens=in_tokens,unreportedRequests=int(not reported))
                if reported and cached is not None and 0<=cached<=in_tokens:
                    value.update(cachedInputTokens=cached,uncachedInputTokens=in_tokens-cached,cacheReportedRequests=1,cacheInputTokens=in_tokens)
                record_model=model(name)
                if hourly and len(created)==10:
                    value['unbucketedRequests']=1
                else:
                    key=bucket(stamp);add(buckets[key],value);add(model_buckets[name][key],value)
                add(total,value);add(record_model,value)
        else:
            daily=db.execute('SELECT day,SUM(submitted) FROM ocr_daily_usage WHERE day BETWEEN ? AND ? GROUP BY day',(first.isoformat(),last.isoformat())).fetchall()
            per_model=db.execute('SELECT day,model,SUM(submitted) FROM ocr_model_usage WHERE day BETWEEN ? AND ? GROUP BY day,model',(first.isoformat(),last.isoformat())).fetchall()
            total['requests']=sum(count for _,count in daily)
            for day,name,count in per_model:
                model(name)['requests']+=count
                if not hourly: model_buckets[name][day]['requests']+=count
            if hourly:
                events=db.execute('SELECT model,submitted_at FROM ocr_submission_usage WHERE day=?',(first.isoformat(),)).fetchall()
                for name,created in events:
                    try: stamp=instant(created)
                    except (ValueError,TypeError): continue
                    if stamp.date()!=first: continue
                    key=bucket(stamp)
                    buckets[key]['requests']+=1
                    model(name);model_buckets[name][key]['requests']+=1
                total['unbucketedRequests']=max(0,total['requests']-sum(value['requests'] for value in buckets.values()))
                for name,value in models.items(): value['unbucketedRequests']=max(0,value['requests']-sum(v['requests'] for v in model_buckets[name].values()))
            else:
                for day,count in daily: buckets[day]['requests']=count
    def points(values): return [{'key':key,'label':key[-5:] if hourly else key[5:],**public(values[key],kind)} for key in bucket_keys]
    ordered=sorted(models,key=lambda name:(-models[name]['requests'],name))
    return {'kind':kind,'range':{'start':first.isoformat(),'end':last.isoformat(),'timezone':'Asia/Shanghai','granularity':'hour' if hourly else 'day'},
            'summary':public(total,kind),'models':[{'model':name,**public(models[name],kind)} for name in ordered],
            'trend':points(buckets),'modelTrends':[{'model':name,'points':points(model_buckets[name])} for name in ordered]}
