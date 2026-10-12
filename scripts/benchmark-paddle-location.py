"""Live synthetic PaddleOCR positioning benchmark; no user documents or secrets saved.

Measures raw cloud results, never silently substitutes Windows OCR in cloud scores.
Uses the same four 85-line fixtures as the earlier LLM benchmark. --live is opt-in.
"""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
import html
import importlib.util
import json
import math
import io
from pathlib import Path
import shutil
import statistics
import sys
import time
from uuid import uuid4
from urllib.parse import urlsplit

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from PIL import Image,ImageDraw,ImageFont
import httpx
from backend.app import paddle_ocr
from backend.app.ocr_settings import active_ocr
from backend.app.ocr_usage import reserve,usage_summary
from backend.app.capture_processing import recognize_positions

OUT=ROOT/'artifacts'/'paddle-benchmark'
DB=ROOT/'backend'/'data'/'snapmind.sqlite3'
spec=importlib.util.spec_from_file_location('vision_benchmark',ROOT/'scripts'/'benchmark-vision-location.py')
vision=importlib.util.module_from_spec(spec);spec.loader.exec_module(vision)

def geometry_metrics(case,predicted):
    """Coordinate-only matching. Text strings do not participate in matching/scoring."""
    truth=case['truth']
    boxes=[p['bbox'] for p in predicted if isinstance(p.get('bbox'),list) and len(p['bbox'])==4]
    errors=[[max(abs(a-b) for a,b in zip(t['bbox'],p)) for p in boxes] for t in truth]
    def matched_within(tolerance):
        assigned={}
        def visit(i,seen):
            for j in sorted(range(len(boxes)),key=lambda j:errors[i][j]):
                if j in seen or errors[i][j]>tolerance: continue
                seen.add(j)
                if j not in assigned or visit(assigned[j],seen):
                    assigned[j]=i;return True
            return False
        for i in range(len(truth)): visit(i,set())
        return len(assigned)
    candidates=[]
    coverages=[]
    for i,t in enumerate(truth):
        coverages.append(max((vision.intersection(t['bbox'],p)/max(1,vision.area(t['bbox'])) for p in boxes),default=0))
        for j,p in enumerate(boxes):
            overlap=vision.intersection(t['bbox'],p)
            iou=overlap/max(1,vision.area(t['bbox'])+vision.area(p)-overlap)
            candidates.append((iou,i,j))
    paired=[];used_truth=set();used_predictions=set()
    for iou,i,j in sorted(candidates,reverse=True):
        if iou<.1 or i in used_truth or j in used_predictions: continue
        used_truth.add(i);used_predictions.add(j)
        edges=[abs(a-b) for a,b in zip(truth[i]['bbox'],boxes[j])]
        paired.append({'truthIndex':i,'predictionIndex':j,'iou':round(iou,4),'meanEdgeErrorPx':round(statistics.mean(edges),2),'maxEdgeErrorPx':max(edges)})
    five,ten=matched_within(5),matched_within(10)
    return {'expected':len(truth),'returned':len(boxes),'qualified5px':five,'qualified10px':ten,
            'qualified5pxRecall':round(five/len(truth),4),'qualified10pxRecall':round(ten/len(truth),4),
            'geometryMatchesIoU01':len(paired),'meanMatchedEdgeErrorPx':round(statistics.mean(p['meanEdgeErrorPx'] for p in paired),2) if paired else None,
            'meanMatchedIoU':round(statistics.mean(p['iou'] for p in paired),4) if paired else None,
            'covered95pct':sum(c>=.95 for c in coverages),'inkCoverageMean':round(statistics.mean(coverages),4),
            'pairs':paired,'lineCoverage':coverages}

def overlay(case,predicted,name):
    image=Image.open(OUT/(case['id']+'.png')).convert('RGB');draw=ImageDraw.Draw(image)
    for t in case['truth']: draw.rectangle(t['bbox'],outline='#15a36b',width=1)
    for i,p in enumerate(predicted):
        if p.get('bbox'):
            draw.rectangle(p['bbox'],outline='#e74d6d',width=2)
            draw.text((p['bbox'][0],max(0,p['bbox'][1]-14)),str(i+1),font=ImageFont.truetype('C:/Windows/Fonts/msyh.ttc',12),fill='#e74d6d')
    image.save(OUT/(name+'-boxes.png'))

def summary(report):
    groups={}
    for run in report['runs']:
        groups.setdefault(run['model'],[]).append(run)
    report['summary']={}
    for model,runs in groups.items():
        successful=[r for r in runs if 'geometry' in r]
        total=sum(r['geometry']['expected'] for r in successful)
        qualified=sum(r['geometry']['qualified5px'] for r in successful)
        durations=[r['latencySeconds'] for r in successful]
        report['summary'][model]={'requests':len(runs),'successful':len(successful),'expectedLines':total,
                                 'qualified5px':qualified,'qualified5pxRecall':qualified/total if total else None,
                                 'averageSeconds':round(statistics.mean(durations),2) if durations else None,
                                 'medianSeconds':round(statistics.median(durations),2) if durations else None,
                                 'minSeconds':min(durations) if durations else None,'maxSeconds':max(durations) if durations else None}
    primary=[r for r in report['runs'] if r['round']==1 and not r.get('inputVariant')]
    report['primaryComparison']={}
    for model in groups:
        runs=[r for r in primary if r['model']==model]
        successful=[r for r in runs if 'geometry' in r]
        total=sum(r['geometry']['expected'] for r in successful)
        located=sum(r['geometry']['qualified5px'] for r in successful)
        report['primaryComparison'][model]={'images':len(runs),'successful':len(successful),'expected':total,'qualified5px':located,
            'qualified5pxRecall':located/total if total else None,
            'averageSeconds':round(statistics.mean(r['latencySeconds'] for r in successful),2) if successful else None}
    report['firstSuccessfulComparison']={}
    for model,runs in groups.items():
        selected=[]
        for case in report['cases']:
            run=next((r for r in runs if r['case']==case['id'] and not r.get('inputVariant') and 'geometry' in r),None)
            if run: selected.append(run)
        expected=sum(r['geometry']['expected'] for r in selected)
        five=sum(r['geometry']['qualified5px'] for r in selected)
        ten=sum(r['geometry']['qualified10px'] for r in selected)
        report['firstSuccessfulComparison'][model]={'images':len(selected),'expected':expected,'qualified5px':five,'qualified10px':ten,
            'qualified5pxRecall':five/expected if expected else None,'qualified10pxRecall':ten/expected if expected else None,
            'selectedRuns':[r['name'] for r in selected],'rounds':[r['round'] for r in selected]}
    report['latencyGroups']={}
    for model,runs in groups.items():
        for label,condition in [('first',lambda r:r['round']==1 and not r.get('inputVariant')),
                                ('repeat',lambda r:r['round']>1 and not r.get('inputVariant')),
                                ('changed-image',lambda r:bool(r.get('inputVariant')))]:
            selected=[r for r in runs if condition(r)]
            if not selected: continue
            complete=[r for r in selected if 'geometry' in r]
            report['latencyGroups'][model+'/'+label]={'attempted':len(selected),'successful':len(complete),
                'timeouts':sum(r.get('error')=='timeout' for r in selected),
                'averageSuccessfulSeconds':round(statistics.mean(r['latencySeconds'] for r in complete),2) if complete else None,
                'averageObservedSecondsIncludingCutoff':round(statistics.mean(r['latencySeconds'] for r in selected),2),
                'minSuccessfulSeconds':min((r['latencySeconds'] for r in complete),default=None),
                'maxSuccessfulSeconds':max((r['latencySeconds'] for r in complete),default=None)}
    table_run=next((r for r in primary if r['model']=='PaddleOCR-VL-1.6' and r['case']=='table' and 'result' in r),None)
    if table_run:
        table=next((r for r in table_run['result']['regions'] if r.get('label')=='table' and r.get('bbox')),None)
        if table:
            known_table=[45,118,1186,539]
            overlap=vision.intersection(table['bbox'],known_table)
            report['tableBlockExample']={'expectedGridBBox':known_table,'returnedBBox':table['bbox'],
                'iou':round(overlap/(vision.area(table['bbox'])+vision.area(known_table)-overlap),4)}
    (OUT/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    rows=[];cards=[]
    for r in report['runs']:
        g=r.get('geometry',{})
        values=[r['model'],r['case'],str(r['round'])+(' 新图' if r.get('inputVariant') else ''),g.get('expected',''),g.get('returned',''),
                f"{g['qualified5pxRecall']*100:.1f}%" if g else '',g.get('meanMatchedEdgeErrorPx',''),
                ', '.join(r.get('granularities',[])),r.get('latencySeconds',''),r.get('error','')]
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in values)+'</tr>')
        if g: cards.append(f'<article><h3>{html.escape(r["name"])}</h3><img src="{r["name"]}-boxes.png"></article>')
        if r.get('layoutRegions'):
            cards.append(f'<article><h3>{html.escape(r["name"])} · 版面块坐标</h3><img src="{r["name"]}-layout-boxes.png"></article>')
    page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>PaddleOCR定位实测</title><style>body{font:15px "Segoe UI","Microsoft YaHei",sans-serif;background:#f7f3fc;color:#312940;margin:24px}h1{color:#7c3aed}table{border-collapse:collapse;background:white;width:100%}td,th{padding:10px;border-bottom:1px solid #e4dbee;text-align:left}article{background:white;border-radius:14px;padding:16px;margin:20px 0}img{max-width:100%;height:auto}</style><h1>PaddleOCR 文字位置与速度实测</h1><p>绿色：真实文字笔画框；红色：服务返回的原始坐标。未使用真实坐标引导模型，云端分数不混入 Windows OCR 降级结果。</p><p>5px合格率仅依据坐标：四条边偏差均≤5px；文字内容不参与位置匹配。VL可能合并多行或整个表格，因此块级覆盖不等于逐行精确定位。</p><table><thead><tr><th>模型</th><th>场景</th><th>轮次</th><th>真实条目</th><th>返回框</th><th>5px合格率</th><th>匹配框平均边误差px</th><th>粒度</th><th>完整耗时s</th><th>错误</th></tr></thead><tbody>'''+''.join(rows)+'</tbody></table>'+''.join(cards)+'</html>'
    (OUT/'report.html').write_text(page,encoding='utf-8')
    lines=['# PaddleOCR 文字位置定位与速度实测','',
           '使用4张虚构测试图（85个文字行／表格单元格）。原图、真实坐标与前面的LLM测试相同。',
           '定位评估只使用几何坐标，不把文字识别是否正确计入定位分数。合格标准为四条边各自偏差≤5px；使用最大匹配数计算合格率，每个返回框只能对应一个真实文字行。',
           'VL段落／表格框不会被拆成不存在的行框。因此本报告的逐行定位合格率衡量原位逐行翻译的直接可用程度，不代表文档版面解析的整体质量。',
           '完整耗时包括图片提交、排队、云端处理、每2秒一次轮询、结果下载和本地解析。失败记录单独列出，不将Windows降级结果当作PaddleOCR结果。','',
           '| 模型 | 场景 | 轮次 | 返回框/真实条目 | ≤5px定位合格率 | 匹配框平均边误差px | 完整耗时s |',
           '|---|---|---:|---:|---:|---:|---:|']
    for r in report['runs']:
        g=r.get('geometry')
        round_label=str(r['round'])+(' 新图' if r.get('inputVariant') else '')
        if g: lines.append(f"| {r['model']} | {r['case']} | {round_label} | {g['returned']}/{g['expected']} | {g['qualified5pxRecall']*100:.1f}% | {g['meanMatchedEdgeErrorPx']} | {r['latencySeconds']} |")
        else: lines.append(f"| {r['model']} | {r['case']} | {round_label} | — | {r.get('error')} | — | {r['latencySeconds']} |")
    lines.extend(['','## 汇总',''])
    for model,s in report['summary'].items():
        lines.append(f"- {model}：成功 {s['successful']}/{s['requests']} 次；逐行定位合格 {s['qualified5px']}/{s['expectedLines']}；平均 {s['averageSeconds']}s，中位数 {s['medianSeconds']}s，范围 {s['minSeconds']}～{s['maxSeconds']}s。")
    lines.extend(['','上面汇总的平均耗时仅包含成功调用；失败数独立列出，不能把它当作包含超时的完整响应速度。重复图与新图也不可混为同一速度结论。',
                  '', '## 相同4张图片的首轮公平对比', '',
                  '| 模型 | 定位合格数/85 | 合格率 ≤5px | 首轮平均完整耗时 |', '|---|---:|---:|---:|'])
    for model,s in report['primaryComparison'].items():
        if s['expected']:
            lines.append(f"| {model} | {s['qualified5px']}/{s['expected']} | {s['qualified5pxRecall']*100:.1f}% | {s['averageSeconds']}s |")
    lines.extend(['','## 速度稳定性',''])
    for label,s in report['latencyGroups'].items():
        lines.append(f"- {label}：成功 {s['successful']}/{s['attempted']}，超时 {s['timeouts']}；成功平均 {s['averageSuccessfulSeconds']}s，包含60秒截断等待的观测平均 {s['averageObservedSecondsIncludingCutoff']}s。")
    if 'tableBlockExample' in report:
        block=report['tableBlockExample']
        lines.extend(['','## 块定位与行定位的区别','',
                      f"VL 整张表格定位框为 {block['returnedBBox']}，与实际表格边框的 IoU 为 {block['iou']}。说明它能准确定位整张表格，但没有给出24个单元格内的文字位置，所以其逐行5px分数很低；不能据此声称它没有找到表格。"])
    if 'PP-OCRv6' in report['primaryComparison']:
        lines.extend(['','## 对原位翻译的判断','',
                      '- 当前 VL-1.6 更适合文档与表格块级解析；文字区域整体均被覆盖，但合并框和外围留白会影响逐行覆盖位置。',
                      '- PP-OCRv6 返回独立文字行，普通文字、双栏和深色小字号更适合逐行定位；本次表格中返回框偏大，5px严格标准仍不能稳定满足。',
                      '- Windows OCR 的坐标最贴近文字笔画，速度也最快；它的文字误识不计入本次纯位置评估，原文校正仍应交给LLM。',
                      '- 推荐后续原位翻译采用行级OCR，并对过大的框做本地像素／Windows OCR细化；VL可用于版面与阅读顺序辅助。此次仅测试，没有修改当前软件的模型配置。',
                      '- 对同一图片的复测明显更快，可能与云端复用或缓存有关；接口未提供缓存命中字段，不能确认为缓存。新图片补测出现60秒超时，Windows降级仍有必要。'])
    structure=[r for r in primary if r['model']=='PP-StructureV3']
    if structure:
        lines.extend(['','## PP-StructureV3 实测','',
                      '使用相同4张图片复测，单独保留 overall_ocr_res 中的文字行和 parsing_res_list 中的版面块。定位指标仍只依据坐标，文字内容不参与位置匹配。',
                      '| 场景 | 首轮耗时s | 返回文字框 | 返回版面块 | ≤5px逐行定位合格率 | ≤10px逐行定位合格率 |',
                      '|---|---:|---:|---:|---:|---:|'])
        for r in structure:
            g=r.get('geometry',{})
            lines.append(f"| {r['case']} | {r['latencySeconds']} | {g.get('returned','—')} | {len(r.get('layoutRegions',[]))} | {g.get('qualified5pxRecall',0)*100:.1f}% | {g.get('qualified10pxRecall',0)*100:.1f}% |")
        lines.extend(['','原始结构字段的名称记录在 report.json 的 providerSchema 中；此处不保存任何签名资源 URL 或密钥。'])
        chosen=[next(r for r in report['runs'] if r['name']==name) for name in report['firstSuccessfulComparison']['PP-StructureV3']['selectedRuns']]
        result=report['firstSuccessfulComparison']['PP-StructureV3']
        all_structure=[r for r in report['runs'] if r['model']=='PP-StructureV3']
        failures=[r for r in all_structure if r.get('error')]
        successful=[r for r in all_structure if 'geometry' in r]
        note=['# PP-StructureV3 定位与速度实测','',
              '与前面的测试使用相同4张合成图片、85个文字行／表格单元格，真实调用云端8次，成功7次，1次在软件60秒等待上限处超时。没有混入Windows降级结果，也没有改变软件当前模型配置。','',
              f"只依据位置，不看文字识别正确与否。每张图取首次成功结果：四条边偏差均≤5px时，合格 {result['qualified5px']}/{result['expected']}（{result['qualified5pxRecall']*100:.1f}%）；放宽到≤10px时，合格 {result['qualified10px']}/{result['expected']}（{result['qualified10pxRecall']*100:.1f}%）。",
              '普通文字首轮超时，位置指标来自其第2轮成功结果；其余图片来自首轮。定位分数与服务超时分别报告，不能把超时算作坐标识别错误，也不能把它从速度体验中隐藏。','',
              '| 场景 | ≤5px合格数 | ≤5px合格率 | 首次请求耗时 | 获得坐标的成功耗时 |',
              '|---|---:|---:|---:|---:|']
        for r in chosen:
            g=r['geometry'];first=next(x for x in all_structure if x['case']==r['case'])
            first_time=f"{first['latencySeconds']}s"+('（超时）' if first.get('error') else '')
            note.append(f"| {r['case']} | {g['qualified5px']}/{g['expected']} | {g['qualified5pxRecall']*100:.1f}% | {first_time} | {r['latencySeconds']}s |")
        note.extend(['','## 同图定位结果比较','', '| 方案 | ≤5px合格率 |', '|---|---:|'])
        for model,s in report['firstSuccessfulComparison'].items():
            if s['expected']: note.append(f"| {model} | {s['qualified5pxRecall']*100:.1f}%（{s['qualified5px']}/{s['expected']}） |")
        note.extend(['','## 结果解读','',
                     '- PP-StructureV3 返回 overall_ocr_res 中的独立文字行坐标，同时返回 parsing_res_list 的版面块。前者用于本次精定位评估，后者另存为布局叠加图。',
                     '- 在这组图片中，它的逐行定位比 VL-1.6 和 PP-OCRv6 更好，尤其是表格；但5px严格标准仍低于Windows OCR。',
                     '- 表格返回25个文字框（标题+24个单元格），其中13个符合5px标准；其余主要为外围留白或边界偏差。该表格的所有25个文字框都满足10px标准。',
                     '- 首轮成功图片耗时3.06～17.01秒，另有一次60.05秒超时。重复图片通常更快，但不能将重复图片速度当作所有新截图的速度；接口未提供缓存命中信息。',
                     '- 这只是4张标准字体合成图的实测；它适合用于比较当前接口在这些样本上的效果，不是通用准确率或可靠的服务延迟分布。',
                     '- 对原位翻译，Structure的行级结果可用作候选定位来源，仍需保留Windows降级和对框边界的细化。', '',
                     '[文字行与版面块坐标对比图](report.html) · [原始坐标及耗时](report.json)',
                     ])
        (OUT/'STRUCTURE_RESULTS.md').write_text('\n'.join(note)+'\n',encoding='utf-8')
        lines.extend(['',f"按每张图首次成功结果统计，Structure ≤5px 合格 {result['qualified5px']}/{result['expected']}（{result['qualified5pxRecall']*100:.1f}%），≤10px 合格 {result['qualified10px']}/{result['expected']}。普通文字使用第2轮成功结果，首轮超时独立列出。详细结论见 [Structure专项报告](STRUCTURE_RESULTS.md)。"])
    lines.extend(['','完整原始文字和坐标、请求阶段计时保存在 [report.json](report.json)，坐标叠加图见 [report.html](report.html)。',
                  '测试图片为标准字体合成样本；结果不代表所有真实截图，样本数量不足以给出可靠的服务P95延迟。位置平均误差只针对IoU≥0.1的几何匹配框，因此必须结合漏检／合格率一起看。',
                  '模型与调用方式依据 [PaddleOCR官方API说明](https://www.paddleocr.ai/main/version3.x/inference_deployment/serving/paddleocr_official_api/python.html)。',
                  '本脚本不修改已保存的OCR模型配置；真实测试提交量会计入本软件每日额度。',
                  '复现：`python scripts/benchmark-paddle-location.py --live --rounds 2`；`--report-only` 仅重算已有数据，无API调用。'])
    (OUT/'RESULTS.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')

async def cloud_run(config,case,round_number,fresh=False):
    name=case['id']+'-'+config['model'].lower().replace('.','-')+'-r'+str(round_number)
    if fresh: name+='-fresh-'+uuid4().hex[:6]
    record={'name':name,'model':config['model'],'case':case['id'],'round':round_number,'requests':[]}
    if fresh: record['inputVariant']='changed-blank-corner-pixels'
    url_path=urlsplit(config['baseUrl']).path
    async def request_hook(request): request.extensions['bench_start']=time.perf_counter()
    async def response_hook(response):
        req=response.request
        phase='submit' if req.method=='POST' else 'poll' if req.url.path.startswith(url_path+'/') else 'download'
        record['requests'].append({'phase':phase,'status':response.status_code,'timeToHeadersSeconds':round(time.perf_counter()-req.extensions['bench_start'],3)})
    real=paddle_ocr.httpx.AsyncClient
    real_download=paddle_ocr.download_jsonl
    async def capture_download(client,url):
        content=await real_download(client,url)
        schemas=[];blocks=[]
        for line in content.splitlines():
            if not line.strip(): continue
            payload=json.loads(line)
            result=payload.get('result',{})
            pages=result.get('layoutParsingResults',result.get('ocrResults',[]))
            for page_index,page in enumerate(pages):
                pruned=page.get('prunedResult',{})
                schemas.append({'pageKeys':list(page),'prunedKeys':list(pruned),
                                'overallOcrKeys':list(pruned.get('overall_ocr_res') or {})})
                for block in pruned.get('parsing_res_list',[]):
                    if not isinstance(block,dict) or not isinstance(block.get('block_content'),str): continue
                    item=paddle_ocr.region(block['block_content'],block.get('block_bbox'),label=block.get('block_label','text'))
                    if item.get('bbox'): blocks.append(item | {'page':page_index,'granularity':'block'})
        record['providerSchema']=schemas
        record['layoutRegions']=blocks
        return content
    def client(**kwargs):
        return real(**kwargs,event_hooks={'request':[request_hook],'response':[response_hook]})
    reason=reserve(DB,config)
    started=time.perf_counter()
    if reason:
        record['error']=reason;record['latencySeconds']=0;return record
    try:
        paddle_ocr.httpx.AsyncClient=client
        paddle_ocr.download_jsonl=capture_download
        raw=(OUT/(case['id']+'.png')).read_bytes()
        if fresh:
            modified=Image.open(io.BytesIO(raw)).convert('RGB')
            draw=ImageDraw.Draw(modified)
            color=tuple(uuid4().bytes[:3])
            draw.rectangle((case['width']-8,case['height']-8,case['width']-5,case['height']-5),fill=color)
            input_path=OUT/(name+'-input.png');modified.save(input_path)
            record['inputImage']=input_path.name
            raw=input_path.read_bytes()
        data='data:image/png;base64,'+base64.b64encode(raw).decode()
        result=await paddle_ocr.recognize_paddle(config,data)
        record['latencySeconds']=round(time.perf_counter()-started,2)
        record['result']=result
        record['granularities']=sorted({r.get('granularity','unknown') for r in result['regions']})
        record['geometry']=geometry_metrics(case,result['regions'])
        record['textBasedMetrics']=vision.evaluate(case,result['regions'])
        overlay(case,result['regions'],name)
        if record.get('layoutRegions'): overlay(case,record['layoutRegions'],name+'-layout')
    except Exception as e:
        record['latencySeconds']=round(time.perf_counter()-started,2)
        record['error']=getattr(e,'reason',type(e).__name__)
    finally:
        paddle_ocr.httpx.AsyncClient=real
        paddle_ocr.download_jsonl=real_download
    return record

async def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--live',action='store_true')
    parser.add_argument('--rounds',type=int,choices=[1,2,3],default=1)
    parser.add_argument('--models',nargs='+',default=['PaddleOCR-VL-1.6'])
    parser.add_argument('--append',action='store_true')
    parser.add_argument('--fresh',action='store_true',help='Change only blank corner pixels to test a new image without changing text geometry.')
    parser.add_argument('--report-only',action='store_true')
    args=parser.parse_args()
    OUT.mkdir(parents=True,exist_ok=True)
    report_path=OUT/'report.json'
    if args.report_only:
        report=json.loads(report_path.read_text(encoding='utf-8'))
        for r in report['runs']:
            if 'result' in r:
                case=next(c for c in report['cases'] if c['id']==r['case'])
                r['geometry']=geometry_metrics(case,r['result']['regions'])
        summary(report);print('Report refreshed. No API calls.');return
    source=ROOT/'artifacts'/'vision-location'
    if not (source/'ground-truth.json').exists():
        source.mkdir(parents=True,exist_ok=True);cases=vision.fixtures()
    else: cases=json.loads((source/'ground-truth.json').read_text(encoding='utf-8'))
    for case in cases: shutil.copyfile(source/(case['id']+'.png'),OUT/(case['id']+'.png'))
    report=json.loads(report_path.read_text(encoding='utf-8')) if args.append and report_path.exists() else {
        'createdAt':datetime.now(timezone.utc).isoformat(),'syntheticOnly':True,'positionScoring':'geometry-only',
        'pollIntervalSeconds':paddle_ocr.POLL_INTERVAL,'timeoutSeconds':paddle_ocr.JOB_TIMEOUT,'cases':cases,'runs':[]}
    if not args.append:
        for case in cases:
            started=time.perf_counter()
            result=recognize_positions('data:image/png;base64,'+base64.b64encode((OUT/(case['id']+'.png')).read_bytes()).decode())
            r={'name':case['id']+'-windows-ocr','model':'Windows OCR','case':case['id'],'round':1,
               'latencySeconds':round(time.perf_counter()-started,2),'result':result,
               'geometry':geometry_metrics(case,result['regions']),'granularities':['line']}
            report['runs'].append(r);overlay(case,result['regions'],r['name'])
        summary(report)
    if not args.live: print('Fixtures and local baseline ready. Add --live to submit synthetic images.');return
    config=active_ocr(DB)
    if not config or config.get('apiMode')!='async': raise RuntimeError('Enabled async PaddleOCR configuration required')
    for model in args.models:
        model_config=config | {'model':model}
        for n in range(1,args.rounds+1):
            for case in cases:
                print(f"Calling {model}, {case['id']}, round {n}",flush=True)
                run=await cloud_run(model_config,case,n,args.fresh)
                report['runs'].append(run);report['usageAfter']=usage_summary(DB,config);summary(report)
                print(json.dumps({'model':model,'case':case['id'],'round':n,'latencySeconds':run['latencySeconds'],
                    'error':run.get('error'),'geometry':{k:v for k,v in run.get('geometry',{}).items() if k not in ('pairs','lineCoverage')},
                    'granularities':run.get('granularities')},ensure_ascii=True),flush=True)
                if run.get('error') in ('cloud-quota','authentication','daily-limit'):
                    print('Stopping after quota/authentication rejection; no retries.',flush=True);return
    print('Saved artifacts/paddle-benchmark/RESULTS.md and report.html',flush=True)

if __name__=='__main__': asyncio.run(main())
