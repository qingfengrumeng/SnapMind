"""Read-only aggregation of prior synthetic tests. Never calls any model API.

Regenerate after appending tests to the existing benchmark reports. Source JSON
and image evidence are archived by content hash; previous summaries are retained.
"""
from datetime import datetime,timedelta,timezone
import csv
import hashlib
import importlib.util
import inspect
import json
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'location-comparison'
spec=importlib.util.spec_from_file_location('paddle_benchmark',ROOT/'scripts'/'benchmark-paddle-location.py')
bench=importlib.util.module_from_spec(spec);spec.loader.exec_module(bench)
LABELS={'simple':'普通文字','columns':'双栏','dense-dark':'小字号深色界面','table':'表格','smoke-six':'接口接入验证（6条文字）'}
MODELS=['DeepSeek Flash（基础模式）','PaddleOCR-VL-1.6','PP-OCRv6','PP-StructureV3','Windows OCR']

def read(path): return json.loads(path.read_text(encoding='utf-8'))
def sha(raw): return hashlib.sha256(raw).hexdigest()
def percent(count,total): return f'{count/total*100:.1f}%' if total else '—'
def number(value): return f'{value:.2f}' if value is not None else '—'

def archive(path,kind):
    raw=path.read_bytes();digest=sha(raw)
    name=f'{kind}/{path.stem}-{digest[:16]}{path.suffix}'
    target=OUT/name;target.parent.mkdir(parents=True,exist_ok=True)
    if target.exists(): assert target.read_bytes()==raw
    else: target.write_bytes(raw)
    return {'path':name,'sha256':digest,'original':path.relative_to(ROOT).as_posix()}

def evidence(path): return archive(path,'evidence')['path'] if path.exists() else None

def build():
    OUT.mkdir(parents=True,exist_ok=True)
    vision_path=ROOT/'artifacts'/'vision-location'/'report.json'
    paddle_path=ROOT/'artifacts'/'paddle-benchmark'/'report.json'
    smoke_path=ROOT/'artifacts'/'paddle-location'/'result.json'
    truth_path=ROOT/'artifacts'/'vision-location'/'ground-truth.json'
    vision,paddle,smoke,cases=read(vision_path),read(paddle_path),read(smoke_path),read(truth_path)
    assert cases==paddle['cases'],'Comparison fixtures must match exactly'
    sources=[archive(p,'sources') for p in [vision_path,paddle_path,smoke_path,truth_path]]
    fixture_info=[archive(ROOT/'artifacts'/'vision-location'/(c['id']+'.png'),'fixtures') for c in cases]
    dataset_hash=sha(json.dumps(cases,ensure_ascii=False,sort_keys=True).encode()+''.join(p['sha256'] for p in fixture_info).encode())
    runs=[]
    def add(source,r,model,phase,regions,latency,root,name):
        case=next(c for c in cases if c['id']==r['case'])
        metrics=bench.geometry_metrics(case,regions) if regions is not None else None
        runs.append({'id':source+':'+name,'source':source,'sourceName':name,'model':model,'case':r['case'],
                     'caseLabel':LABELS[r['case']],'phase':phase,'round':r.get('round',1),'latencySeconds':latency,
                     'status':'failed' if r.get('error') else 'success','error':r.get('error'),'expected':len(case['truth']),
                     'geometry':metrics,'granularities':sorted({p.get('granularity','estimated-line') for p in regions}) if regions is not None else [],
                     'image':evidence(root/(name+'-boxes.png')),'layoutImage':evidence(root/(name+'-layout-boxes.png')),
                     'historicalMetrics':r.get('metrics') or r.get('textBasedMetrics'),
                     'coordinates':regions,'requests':r.get('requests',[]),'providerSchema':r.get('providerSchema'),
                     'batchSeconds':vision.get('ocrBatchLatencySeconds') if source=='vision' and model=='Windows OCR' else None})
    for r in vision['runs']:
        name=r['name'];model='Windows OCR' if r['engine']=='windows-ocr' else 'DeepSeek Flash（基础模式）'
        phase='早期本地批量对照' if model=='Windows OCR' else '基础首轮'
        if 'repeat' in name: phase='重复图片'
        if r.get('coordinateMode')=='normalized1000': model='DeepSeek Flash（归一化坐标）';phase='归一化坐标补测'
        if r.get('thinking'): model='DeepSeek Flash（high 思考模式）';phase='思考模式补测'
        add('vision',r,model,phase,r.get('predictions'),r.get('latencySeconds'),vision_path.parent,name)
    for r in paddle['runs']:
        phase='本地逐图对照' if r['model']=='Windows OCR' else '首轮'
        if r.get('inputVariant'): phase='微变新图片'
        elif r['round']>1: phase='重复图片／补测'
        add('paddle',r,r['model'],phase,r.get('result',{}).get('regions'),r['latencySeconds'],paddle_path.parent,r['name'])
    runs.append({'id':'smoke:paddle-vl-six','source':'smoke','sourceName':'paddle-vl-six','model':'PaddleOCR-VL-1.6',
                 'case':'smoke-six','caseLabel':LABELS['smoke-six'],'phase':'接口接入验证','round':1,'status':'success','error':None,
                 'latencySeconds':smoke['latencySeconds'],'expected':len(smoke['truth']),'geometry':None,
                 'granularities':sorted({r['granularity'] for r in smoke['result']['regions']}),
                 'coordinates':smoke['result']['regions'],'image':evidence(smoke_path.parent/'position-overlay.png'),'layoutImage':None,
                 'note':'接入验证采用另一张图；其真实框不是逐笔画像素框，不计入85条文字的定位准确率对比。'})
    comparisons=[]
    extra_models=[model for model in dict.fromkeys(r['model'] for r in runs if r['source']=='paddle') if model not in MODELS]
    for model in MODELS+extra_models:
        candidates=[r for r in runs if r['model']==model and (r['source']=='vision' if model.startswith('DeepSeek') else r['source']=='paddle') and r['phase']!='微变新图片']
        selected=[];first=[]
        for c in cases:
            available=[r for r in candidates if r['case']==c['id']]
            first.append(available[0])
            accepted=next((r for r in available if r['geometry'] is not None and r['status']=='success'),None)
            if accepted: selected.append(accepted)
        total=sum(r['expected'] for r in selected)
        count5=sum(r['geometry']['qualified5px'] for r in selected)
        count10=sum(r['geometry']['qualified10px'] for r in selected)
        durations=[r['latencySeconds'] for r in first if r['latencySeconds'] is not None]
        comparisons.append({'model':model,'expected':total,'qualified5px':count5,'qualified10px':count10,
                            'rate5':count5/total,'rate10':count10/total,'selectedRunIds':[r['id'] for r in selected],
                            'firstRunIds':[r['id'] for r in first],
                            'firstMeanWaitSeconds':round(statistics.mean(durations),2),
                            'firstSuccesses':sum(r['status']=='success' for r in first),'firstAttempts':len(first),
                            'firstTimeouts':sum(r['error']=='timeout' for r in first),
                            'note':'普通文字采用第2轮成功结果；首轮60秒超时计入平均等待' if model=='PP-StructureV3' else ''})
    performance=[]
    for model,phase in dict.fromkeys((r['model'],r['phase']) for r in runs):
        selected=[r for r in runs if r['model']==model and r['phase']==phase]
        times=[r['latencySeconds'] for r in selected if r['latencySeconds'] is not None]
        successful=[r['latencySeconds'] for r in selected if r['status']=='success' and r['latencySeconds'] is not None]
        performance.append({'model':model,'phase':phase,'attempts':len(selected),'successes':sum(r['status']=='success' for r in selected),
                            'timeouts':sum(r['error']=='timeout' for r in selected),'meanObservedSeconds':round(statistics.mean(times),2) if times else None,
                            'meanSuccessfulSeconds':round(statistics.mean(successful),2) if successful else None,
                            'minSuccessfulSeconds':min(successful) if successful else None,'maxSuccessfulSeconds':max(successful) if successful else None,
                            'note':'4张图批量共0.87秒，不能当成每张图耗时' if phase=='早期本地批量对照' else ''})
    now=datetime.now(timezone(timedelta(hours=8)))
    result={'schemaVersion':1,'generatedAt':now.isoformat(),'timezone':'Asia/Shanghai','syntheticOnly':True,
            'scoring':'geometry-only; max one-to-one matches; all four edges within tolerance',
            'scoringCodeSha256':sha(inspect.getsource(bench.geometry_metrics).encode()),
            'datasetId':'standard-4-v1','datasetSha256':dataset_hash,'cases':cases,'fixtures':fixture_info,
            'sources':sources,'comparisons':comparisons,'performance':performance,'runs':runs,
            'counts':{'records':len(runs),'llmCalls':sum(r['source']=='vision' and r['model'].startswith('DeepSeek') for r in runs),
                      'paddleCalls':sum(r['source']=='paddle' and r['model']!='Windows OCR' for r in runs),
                      'smokeCalls':1,'localRecords':sum(r['model']=='Windows OCR' for r in runs),
                      'timeouts':sum(r.get('error')=='timeout' for r in runs)}}
    fingerprint=sha(json.dumps({'sources':sources,'datasetSha256':dataset_hash,'scoringCodeSha256':result['scoringCodeSha256']},sort_keys=True).encode())[:16]
    result['snapshotId']=fingerprint
    (OUT/'comparison.json').write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    history=OUT/'history'/f'{now.date()}-{fingerprint}.json';history.parent.mkdir(exist_ok=True)
    if not history.exists(): history.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    return result

def write_csv(report):
    columns=['id','model','case','caseLabel','phase','round','status','error','expected','returned',
             'qualified5px','rate5','qualified10px','rate10','meanMatchedEdgeErrorPx','latencySeconds','granularities']
    with (OUT/'all-runs.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns);writer.writeheader()
        for r in report['runs']:
            g=r.get('geometry') or {}
            writer.writerow({k:r.get(k) for k in columns} | {'returned':g.get('returned'),
                'qualified5px':g.get('qualified5px'),'rate5':g.get('qualified5pxRecall'),
                'qualified10px':g.get('qualified10px'),'rate10':g.get('qualified10pxRecall'),
                'meanMatchedEdgeErrorPx':g.get('meanMatchedEdgeErrorPx'),'granularities':','.join(r['granularities'])})

def write_markdown(report):
    by_id={r['id']:r for r in report['runs']}
    lines=['# 文字位置定位测试总汇','',f"更新时间：{report['generatedAt']}（北京时间）。",'',
           '**用途：作为后续定位模型、调用方式与框边界优化的对比基线。此文件仅汇总既有数据，没有发起新模型调用。**','',
           '## 统一统计口径','',
           '- 标准数据集：`standard-4-v1`，4张合成截图，85个文字行／表格单元格。普通文字10、双栏21、深色小字号29、表格25。所有主要方案使用完全相同的原图与真实文字像素框。',
           '- 只看坐标。文字是否识别正确不影响定位匹配；按照几何位置做一对一匹配。一个段落框或整个表格框不能重复算成多个文字行定位成功。',
           '- 5px／10px标准：一个框的左、上、右、下四条边偏差都不超过对应阈值。分母为真实文字条目数，漏检或合并框会降低合格率。',
           '- 精度主表：每张原图取首次成功结果，避免挑选最高分。PP-StructureV3普通文字首轮超时，使用第2轮成功结果；超时仍单列记录。',
           '- 速度主表：首轮平均完整等待时间，包含网络、提交、排队、轮询、下载与解析；60秒超时的实际等待也计入。重复图与微变新图的耗时独立列出。',
           '- 早期LLM报告的文字辅助匹配分数保留在原始记录里；本总汇从原始坐标重算纯几何分数。5px主表数值与此前结论一致。','',
           '## 主方案对比','',
           '| 方案 | ≤5px合格数 | ≤5px合格率 | ≤10px合格率 | 首轮平均等待 | 首轮成功/请求 | 备注 |',
           '|---|---:|---:|---:|---:|---:|---|']
    for c in report['comparisons']:
        lines.append(f"| {c['model']} | {c['qualified5px']}/{c['expected']} | {percent(c['qualified5px'],c['expected'])} | {percent(c['qualified10px'],c['expected'])} | {number(c['firstMeanWaitSeconds'])}秒 | {c['firstSuccesses']}/{c['firstAttempts']} | {c['note']} |")
    lines.extend(['','## 各场景定位合格率（≤5px）','',
                  '| 方案 | 普通文字 | 双栏 | 深色小字号 | 表格 |','|---|---:|---:|---:|---:|'])
    for c in report['comparisons']:
        chosen=[by_id[i] for i in c['selectedRunIds']]
        values=[percent(r['geometry']['qualified5px'],r['expected']) for r in chosen]
        lines.append('| '+c['model']+' | '+' | '.join(values)+' |')
    lines.extend(['','## 全部补测与速度记录','',
                  '| 方案 | 测试阶段 | 成功/请求 | 超时 | 平均等待（含超时） | 成功请求平均 | 成功耗时范围 | 说明 |',
                  '|---|---|---:|---:|---:|---:|---:|---|'])
    for p in report['performance']:
        interval=number(p['minSuccessfulSeconds'])+'～'+number(p['maxSuccessfulSeconds']) if p['minSuccessfulSeconds'] is not None else '—'
        lines.append(f"| {p['model']} | {p['phase']} | {p['successes']}/{p['attempts']} | {p['timeouts']} | {number(p['meanObservedSeconds'])}秒 | {number(p['meanSuccessfulSeconds'])}秒 | {interval}秒 | {p['note']} |")
    lines.extend(['','## LLM补测的定位结果','',
                  '| 模式／阶段 | 场景 | 合格数 ≤5px | 合格率 ≤5px | 合格率 ≤10px | 耗时 |',
                  '|---|---|---:|---:|---:|---:|'])
    for r in report['runs']:
        if r['source']=='vision' and r['model'].startswith('DeepSeek') and r['phase']!='基础首轮':
            g=r['geometry']
            lines.append(f"| {r['model']} / {r['phase']} | {r['caseLabel']} | {g['qualified5px']}/{r['expected']} | {percent(g['qualified5px'],r['expected'])} | {percent(g['qualified10px'],r['expected'])} | {number(r['latencySeconds'])}秒 |")
    lines.extend(['','## 重要区别与结论','',
                  '- Windows OCR：本组纯坐标精度最高、响应最快；这不表示它的文字识别质量最好，文字校正仍可由LLM完成。',
                  '- PP-StructureV3：确实返回文字行坐标；5px合格率81.2%，10px合格率100%。其原图首轮有1次超时，必须保留本地降级。',
                  '- PP-OCRv6：独立文字行模型，普通文字、双栏和小字号表现较好，但本组表格框偏大。',
                  '- PaddleOCR-VL-1.6：善于定位段落或整张表格，粒度与精确逐行覆盖不同。此前整表格框IoU约99.0%，不能把逐行低分解读成它没有找出表格。',
                  '- DeepSeek：本组文字转录准确，但自行输出的精确坐标不稳定；开启思考模式或改归一化坐标也未统一改善所有场景。',
                  '- 云端重复图片更快，可能与服务复用或缓存有关，但接口没有缓存命中信息。微变新图的VL补测有2次60秒超时。',
                  '- PP-StructureV3为8次请求，成功7次；VL主测试及补测为12次请求，成功10次；PP-OCRv6为4次请求，均成功。初始VL接入验证另有1次，21.82秒返回6个块，不纳入标准85条精度对比。',
                  '- 5px与10px是本软件精定位的评估门槛，数据集只有4张标准字体合成图。不能把这些数值视为模型在任意文档上的通用准确率，也不足以推断可靠的服务P95延迟。','',
                  '## 全部记录与后续追加','',
                  f"共归档 {report['counts']['records']} 条记录：LLM {report['counts']['llmCalls']} 次、Paddle标准测试 {report['counts']['paddleCalls']} 次、接入验证1次、本地OCR记录 {report['counts']['localRecords']} 条。3次超时均保留。",'',
                  '- [可筛选总览及坐标图](index.html)',
                  '- [全部数据 JSON](comparison.json)',
                  '- [Excel可导入的全部记录 CSV](all-runs.csv)',
                  '- `sources/`：按内容哈希归档原始JSON；`evidence/`：归档坐标图；`fixtures/`：归档原图；`history/`：保存历史总汇。',
                  '- 后续运行原测试脚本追加测试，再执行 `python scripts/summarize-location-benchmarks.py`，即可更新总汇；汇总脚本不调用任何模型。',
                  '- 新测试记录应包括模型版本、图片尺寸、输入变化、请求阶段、精度阈值、完整耗时与失败原因。不同图片集应另建数据集，不能直接混入85条的主表。','',
                  f"数据集SHA256：`{report['datasetSha256']}`。本次快照：`{report['snapshotId']}`。",''])
    (OUT/'README.md').write_text('\n'.join(lines),encoding='utf-8')

def write_html(report):
    data=json.dumps(report,ensure_ascii=False).replace('</','<\\/')
    template='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>文字定位测试总汇</title>
<style>*{box-sizing:border-box}body{margin:0;background:#f7f4fc;color:#332b43;font:14px "Segoe UI","Microsoft YaHei",sans-serif}main{max-width:1300px;margin:32px auto;padding:0 24px}h1{font-size:27px;margin:0;color:#7432cf}p{line-height:1.8;color:#766a86}section{padding:22px;background:#fff;border:1px solid #e7dff0;border-radius:16px;margin:20px 0}h2{font-size:18px;margin:0 0 16px}button,select,input{font:inherit;border:1px solid #ded1ef;border-radius:8px;background:#fff;color:#4c3b61;padding:8px 12px}button{cursor:pointer}.active{background:#7c3aed;color:white;border-color:#7c3aed}.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.chart-row{display:grid;grid-template-columns:230px 1fr 70px;gap:12px;align-items:center;margin:16px 0}.track{height:24px;background:#f1eafb;border-radius:7px;overflow:hidden}.bar{background:#8b5cf6;height:100%;transition:width .2s;border-radius:7px}.value{font-weight:600;color:#7137c1}table{border-collapse:collapse;width:100%}th,td{text-align:left;padding:11px 10px;border-bottom:1px solid #eee7f5;white-space:nowrap}th{font-weight:600;color:#78638e;font-size:12px}.scroll{overflow:auto}a{color:#7c3aed}.warning{color:#b7574d}.note{font-size:12px}.cards{display:grid;grid-template-columns:repeat(auto-fit,minmax(310px,1fr));gap:16px}article{padding:14px;border:1px solid #e9e0f4;border-radius:12px}article h3{font-size:13px;line-height:1.7;margin:0 0 10px}article img{max-width:100%;height:auto;border:1px solid #eee}.cards .empty{padding:20px;color:#93849f}@media(max-width:650px){main{padding:0 12px}.chart-row{grid-template-columns:145px 1fr 58px;font-size:12px}section{padding:16px}}</style>
<main><h1>文字位置定位 · 历次测试总汇</h1><p id="intro"></p><section><h2>同图定位结果</h2><div class="controls"><button id="five" class="active">四边偏差 ≤5px</button><button id="ten">四边偏差 ≤10px</button><select id="scene" aria-label="对比场景"><option value="all">全部85条文字</option><option value="simple">普通文字</option><option value="columns">双栏</option><option value="dense-dark">深色小字号</option><option value="table">表格</option></select></div><p class="note">只看几何坐标，不看文字识别是否正确。每张图取首次成功结果；Structure普通文字采用补测，首轮超时仍保留。</p><div id="chart"></div><div class="scroll"><table><thead><tr><th>方案</th><th>合格数</th><th>合格率</th><th>首轮平均等待（含超时）</th><th>首轮成功/请求</th><th>说明</th></tr></thead><tbody id="comparison"></tbody></table></div></section>
<section><h2>全部测试记录</h2><div class="controls"><select id="provider" aria-label="筛选模型"><option value="all">所有模型</option></select><select id="runScene" aria-label="筛选测试场景"><option value="all">所有场景</option></select><select id="status" aria-label="筛选状态"><option value="all">全部状态</option><option value="success">成功</option><option value="failed">失败／超时</option></select><span id="count"></span></div><p class="note">早期Windows批量测试：4张共0.87秒，单张耗时未知。其后逐图测试约0.61～0.91秒。重复图、新图与首轮分别列出。</p><div class="scroll"><table><thead><tr><th>方案</th><th>场景</th><th>阶段</th><th>轮次</th><th>状态</th><th>≤5px合格</th><th>≤10px合格</th><th>完整耗时</th><th>返回粒度</th><th>坐标图</th></tr></thead><tbody id="runs"></tbody></table></div></section>
<section><h2>当前筛选的坐标图</h2><p class="note">绿色为真实文字像素框，红色为识别框；版面图展示独立段落或表格块。最多展示前8条有图记录，可点击原图查看。</p><div id="images" class="cards"></div></section>
<section><h2>后续比较</h2><p>保留同一数据集、同一坐标口径；新增测试需记录模型、输入变化、耗时和错误。速度统计保留失败，重复图片速度不代表新图片速度。</p><p><a href="README.md">完整文字报告</a> · <a href="all-runs.csv" download>下载全部记录 CSV</a> · <a href="comparison.json" download>下载全部数据 JSON</a></p><p class="note" id="snapshot"></p></section></main>
<script>const report=__DATA__;let tolerance=5;const byId=Object.fromEntries(report.runs.map(r=>[r.id,r]));const el=id=>document.getElementById(id);const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const rate=(n,d)=>d?(100*n/d).toFixed(1)+'%':'—';const seconds=n=>n==null?'—':Number(n).toFixed(2)+'s';el('intro').textContent=`${report.counts.records} 条归档记录 · 4张标准图 / 85条文字 · 更新 ${report.generatedAt} · 无新API调用`;el('snapshot').textContent=`数据集 ${report.datasetId} · 快照 ${report.snapshotId} · ${report.datasetSha256}`;
function draw(){const scene=el('scene').value;const items=report.comparisons.map(c=>{const rs=c.selectedRunIds.map(id=>byId[id]).filter(r=>scene==='all'||r.case===scene);return {...c,n:rs.reduce((s,r)=>s+r.geometry['qualified'+tolerance+'px'],0),d:rs.reduce((s,r)=>s+r.expected,0)}}).sort((a,b)=>b.n/b.d-a.n/a.d);el('chart').innerHTML=items.map(c=>`<div class="chart-row"><span>${esc(c.model)}</span><div class="track"><div class="bar" style="width:${c.n/c.d*100}%"></div></div><span class="value">${rate(c.n,c.d)}</span></div>`).join('');el('comparison').innerHTML=items.map(c=>`<tr><td>${esc(c.model)}</td><td>${c.n}/${c.d}</td><td>${rate(c.n,c.d)}</td><td>${seconds(c.firstMeanWaitSeconds)}</td><td>${c.firstSuccesses}/${c.firstAttempts}</td><td>${esc(c.note)}</td></tr>`).join('')}
for(const model of [...new Set(report.runs.map(r=>r.model))]){const o=new Option(model,model);el('provider').add(o)}for(const [key,label] of Object.entries(Object.fromEntries(report.runs.map(r=>[r.case,r.caseLabel])))){el('runScene').add(new Option(label,key))}
function filter(){const rows=report.runs.filter(r=>(el('provider').value==='all'||r.model===el('provider').value)&&(el('runScene').value==='all'||r.case===el('runScene').value)&&(el('status').value==='all'||r.status===el('status').value));el('count').textContent=rows.length+' 条';el('runs').innerHTML=rows.map(r=>{const g=r.geometry;return `<tr><td>${esc(r.model)}</td><td>${esc(r.caseLabel)}</td><td>${esc(r.phase)}</td><td>${r.round}</td><td class="${r.status==='failed'?'warning':''}">${r.error?esc(r.error):'成功'}</td><td>${g?rate(g.qualified5px,r.expected)+' ('+g.qualified5px+'/'+r.expected+')':'—'}</td><td>${g?rate(g.qualified10px,r.expected):'—'}</td><td>${seconds(r.latencySeconds)}</td><td>${esc(r.granularities.join(' / '))}</td><td>${r.image?`<a href="${esc(r.image)}" target="_blank">文字框</a>`:''} ${r.layoutImage?`<a href="${esc(r.layoutImage)}" target="_blank">版面块</a>`:''}</td></tr>`}).join('');el('images').innerHTML=rows.filter(r=>r.image).slice(0,8).map(r=>`<article><h3>${esc(r.model)} · ${esc(r.caseLabel)} · ${esc(r.phase)}</h3><a href="${esc(r.image)}" target="_blank"><img loading="lazy" src="${esc(r.image)}" alt="${esc(r.caseLabel)}坐标对比"></a></article>`).join('')||'<div class="empty">当前筛选没有坐标图</div>'}
el('five').onclick=()=>{tolerance=5;el('five').classList.add('active');el('ten').classList.remove('active');draw()};el('ten').onclick=()=>{tolerance=10;el('ten').classList.add('active');el('five').classList.remove('active');draw()};el('scene').onchange=draw;for(const id of ['provider','runScene','status'])el(id).onchange=filter;draw();filter();</script></html>'''
    (OUT/'index.html').write_text(template.replace('__DATA__',data),encoding='utf-8')

if __name__=='__main__':
    report=build();write_csv(report);write_markdown(report);write_html(report)
    print(json.dumps({'records':report['counts']['records'],'snapshotId':report['snapshotId'],
                      'comparison':[{k:c[k] for k in ['model','qualified5px','expected','firstMeanWaitSeconds']} for c in report['comparisons']]},ensure_ascii=True))
    print('Saved artifacts/location-comparison/README.md, index.html, comparison.json, all-runs.csv and source/history snapshots. No API calls.')
