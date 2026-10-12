"""Synthetic, ground-truth text localization benchmark. --live explicitly calls the active LLM.

Only generated fixtures leave this PC. Credentials are read in memory, never printed/saved.
No application model configuration or screenshot behavior is modified.
"""
import argparse
import asyncio
import base64
from datetime import datetime, timezone
from difflib import SequenceMatcher
import html
import json
import math
from pathlib import Path
import re
import sqlite3
import statistics
import subprocess
import sys
import time
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import httpx
from PIL import Image, ImageDraw, ImageFont
from backend.app.model_profiles import endpoint, get_active_profile, unprotect_key

OUT = ROOT / 'artifacts' / 'vision-location'
DB = ROOT / 'backend' / 'data' / 'snapmind.sqlite3'
FONT = 'C:/Windows/Fonts/msyh.ttc'


def fixture(name, size, bg, rows, decorations=None):
    image = Image.new('RGB', size, bg)
    if decorations:
        decorations(ImageDraw.Draw(image))
    truth = []
    for text, x, y, font_size, color in rows:
        layer = Image.new('L', size, 0)
        font = ImageFont.truetype(FONT, font_size)
        ImageDraw.Draw(layer).text((x, y), text, font=font, fill=255, anchor='lt')
        bbox = list(layer.getbbox())
        if bbox[2] > size[0] or bbox[3] > size[1]:
            raise ValueError('Fixture overflow')
        image.paste(color, (0, 0, *size), layer)
        truth.append({'text': text, 'bbox': bbox})
    image.save(OUT / (name + '.png'))
    return {'id': name, 'width': size[0], 'height': size[1], 'truth': truth}


def fixtures():
    simple = [
        ('Screenshot translation', 52, 40, 32, '#272238'),
        ('文字提取与位置定位测试', 52, 105, 28, '#353044'),
        ('项目名称：紫色笔记', 52, 168, 24, '#353044'),
        ('保存之后可以复制或导出。', 52, 223, 24, '#353044'),
        ('Version 2.4.1 / build 308', 52, 280, 22, '#353044'),
        ('Total amount: $128.50', 52, 337, 22, '#353044'),
        ('快捷键 Ctrl + Shift + S', 52, 394, 22, '#353044'),
        ('识别内容必须来自图片。', 52, 451, 22, '#353044'),
        ('Cancel', 600, 530, 20, '#7650b6'),
        ('Confirm', 780, 530, 20, '#7650b6'),
    ]
    columns = [('双栏阅读 / Two columns', 55, 38, 30, '#282238')]
    left = ['目录', '第一节：截图基本操作', '框选屏幕中的文字内容。', '保留段落与换行。', 'Translate each visible line.', '项目状态：处理中', '版本号：3.2.7', '保存结果', '不要把空白输出成文字。', '快捷键：Ctrl + C']
    right = ['设置', '第二节：结果对比', '右侧面板可以自由拖动。', '列与列之间留出空隙。', 'Check the original position.', '项目状态：已完成', '版本号：3.2.8', '保存结果', '文字坐标使用原图像素。', '快捷键：Ctrl + V']
    for i, (a, b) in enumerate(zip(left, right)):
        columns.extend([(a, 55, 120 + i * 61, 22, '#393347'), (b, 685, 120 + i * 61, 22, '#393347')])
    dark = [('Application log / 应用日志', 35, 28, 24, '#eeeeef')]
    for i in range(24):
        value = f'[{i+1:02d}] task_{i+1:02d}  status=ready  count={101+i}'
        if i % 4 == 1:
            value = f'[{i+1:02d}] 文字定位测试：保留行号和原始坐标。'
        dark.append((value, 35, 94 + i * 29, 15 if i % 3 else 18, '#c8c8cc' if i % 5 else '#85858d'))
    dark.extend([('模型配置', 985, 100, 18, '#e4e0ec'), ('识别成功：24', 985, 149, 16, '#b8adc9'), ('OCR optional?', 985, 198, 16, '#b8adc9'), ('保存结果', 985, 247, 16, '#b8adc9')])
    table = [('Monthly report / 月度报表', 45, 38, 30, '#282238')]
    cells = [['Name', 'Quantity', 'Price', 'Status'], ['Notebook', '12', '$18.50', '已完成'], ['Keyboard', '4', '$69.00', '处理中'], ['Monitor', '3', '$199.00', '已完成'], ['Mouse', '8', '$24.90', '待确认'], ['合计', '27', '$1,294.20', '审核中']]
    for row, values in enumerate(cells):
        for col, value in enumerate(values):
            table.append((value, 65 + col * 285, 140 + row * 70, 23 if not row else 21, '#332d41'))
    def grid(draw):
        for y in range(118, 539, 70):
            draw.line((45, y, 1180, y), fill='#d4cedf', width=1)
        for x in range(45, 1186, 285):
            draw.line((x, 118, x, 538), fill='#d4cedf', width=1)
    return [fixture('simple', (1000, 620), '#fbf9ff', simple),
            fixture('columns', (1280, 800), '#fbf9ff', columns),
            fixture('dense-dark', (1440, 900), '#242428', dark),
            fixture('table', (1200, 650), '#fbf9ff', table, grid)]


def normalized(text):
    return re.sub(r'\s+', '', text).casefold()


def intersection(a, b):
    return max(0, min(a[2], b[2])-max(a[0], b[0])) * max(0, min(a[3], b[3])-max(a[1], b[1]))


def area(box):
    return max(0, box[2]-box[0]) * max(0, box[3]-box[1])


def evaluate(case, predicted):
    truth = case['truth']
    # Global best-first one-to-one assignment. Duplicate strings are disambiguated
    # by geometry; imperfect transcripts need >= 0.60 character similarity.
    candidates = []
    for i, t in enumerate(truth):
        for j, p in enumerate(predicted):
            similarity = SequenceMatcher(None, normalized(t['text']), normalized(p['text'])).ratio()
            if similarity < .60:
                continue
            distance = math.hypot((t['bbox'][0]+t['bbox'][2]-p['bbox'][0]-p['bbox'][2])/2,
                                  (t['bbox'][1]+t['bbox'][3]-p['bbox'][1]-p['bbox'][3])/2)
            candidates.append((similarity-distance/max(case['width'], case['height'])*.08, i, j, similarity))
    pairs, used_t, used_p = [], set(), set()
    for _, i, j, similarity in sorted(candidates, reverse=True):
        if i in used_t or j in used_p:
            continue
        used_t.add(i); used_p.add(j)
        t, p = truth[i], predicted[j]
        overlap = intersection(t['bbox'], p['bbox'])
        errors = [abs(a-b) for a, b in zip(t['bbox'], p['bbox'])]
        pairs.append({'truthIndex': i, 'predictionIndex': j, 'textSimilarity': round(similarity, 4),
                      'iou': round(overlap/max(1, area(t['bbox'])+area(p['bbox'])-overlap), 4),
                      'inkCoverage': round(overlap/max(1, area(t['bbox'])), 4),
                      'edgeErrorPx': round(statistics.mean(errors), 2), 'maxEdgeErrorPx': round(max(errors), 2),
                      'startErrorPx': round(math.hypot(t['bbox'][0]-p['bbox'][0], t['bbox'][1]-p['bbox'][1]), 2)})
    invalid = sum(any(v < 0 or v > (case['width'] if k % 2 == 0 else case['height']) for k, v in enumerate(p['bbox'])) or area(p['bbox']) <= 0 for p in predicted)
    return {'expected': len(truth), 'returned': len(predicted), 'matched': len(pairs),
            'matchedRecall': round(len(pairs)/len(truth), 4),
            'exactTextRecall': round(sum(p['textSimilarity'] == 1 for p in pairs)/len(truth), 4),
            'located5pxRecall': round(sum(p['maxEdgeErrorPx'] <= 5 for p in pairs)/len(truth), 4),
            'located10pxRecall': round(sum(p['maxEdgeErrorPx'] <= 10 for p in pairs)/len(truth), 4),
            'usable5pxRecall': round(sum(p['maxEdgeErrorPx'] <= 5 and p['textSimilarity'] == 1 for p in pairs)/len(truth), 4),
            'meanIoU': round(statistics.mean(p['iou'] for p in pairs), 4) if pairs else 0,
            'meanEdgeErrorPx': round(statistics.mean(p['edgeErrorPx'] for p in pairs), 2) if pairs else None,
            'meanStartErrorPx': round(statistics.mean(p['startErrorPx'] for p in pairs), 2) if pairs else None,
            'p95MaxEdgeErrorPx': round(sorted(p['maxEdgeErrorPx'] for p in pairs)[max(0, math.ceil(len(pairs)*.95)-1)], 2) if pairs else None,
            'incompleteCoverage': sum(p['inkCoverage'] < .95 for p in pairs), 'invalidBoxes': invalid,
            'missedTruth': [truth[i]['text'] for i in range(len(truth)) if i not in used_t],
            'unmatchedPredictions': [predicted[i]['text'] for i in range(len(predicted)) if i not in used_p], 'pairs': pairs}


def overlay(case, predicted, name):
    image = Image.open(OUT / (case['id'] + '.png')).convert('RGB')
    draw = ImageDraw.Draw(image)
    for t in case['truth']:
        draw.rectangle(t['bbox'], outline='#16a36a', width=1)
    for i, p in enumerate(predicted):
        draw.rectangle(p['bbox'], outline='#ec3e66', width=2)
        draw.text((p['bbox'][0], p['bbox'][1]-13), str(i+1), fill='#ec3e66', font=ImageFont.truetype(FONT, 12), anchor='lt')
    image.save(OUT / (name + '-boxes.png'))


def ocr_spans(document):
    spans = []
    for line in document['lines']:
        group = []
        for word in line['words']:
            # Separate visual columns/table cells, not ordinary spaces between words.
            if group and word['bbox'][0]-group[-1]['bbox'][2] > max(18, (word['bbox'][3]-word['bbox'][1])*1.5):
                spans.append(group); group = []
            group.append(word)
        if group:
            spans.append(group)
    return [{'text': ' '.join(w['text'] for w in words),
             'bbox': [min(w['bbox'][0] for w in words), min(w['bbox'][1] for w in words),
                      max(w['bbox'][2] for w in words), max(w['bbox'][3] for w in words)]} for words in spans]


async def live(profile, case, name, coordinate_mode='pixels', thinking=False):
    dimensions = f"输入图片宽 {case['width']} 像素、高 {case['height']} 像素。"
    coords = 'bbox 使用原图像素，格式 [x_min,y_min,x_max,y_max]，左上角为 (0,0)。'
    if coordinate_mode == 'normalized1000':
        coords = 'bbox 使用归一化 0~1000 整数坐标，格式 [x_min,y_min,x_max,y_max]，原图左上角为 (0,0)，右下角为 (1000,1000)。'
    prompt = dimensions + '\n' + coords + '\n' + (
        '定位图片中所有清晰可见的文字，逐行完整转录。每个视觉文字行输出一个条目；'
        '同一行中不同栏、表格不同单元格必须分别输出，不要合并。'
        '框必须紧密包住该条目的全部文字笔画，不包括行间空白、按钮背景和表格边框。'
        '不要猜测、遗漏、添加解释或输出无法辨认占位符。不要翻译。'
        '只输出 JSON 对象：{"lines":[{"text":"真实文字","bbox":[0,0,100,20]}]}。')
    encoded = base64.b64encode((OUT / (case['id']+'.png')).read_bytes()).decode('ascii')
    body = {'model': profile['model'], 'stream': False, 'temperature': 0, 'max_tokens': 6500,
            'response_format': {'type': 'json_object'},
            'messages': [{'role': 'system', 'content': '你是截图文字定位工具。严格返回有效 JSON，坐标必须对应输入图片。'},
                         {'role': 'user', 'content': [{'type': 'text', 'text': prompt},
                             {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,'+encoded, 'detail': 'original'}}]}]}
    if profile.get('vendor') == 'deepseek':
        body['thinking'] = {'type': 'enabled' if thinking else 'disabled'}
        if thinking:
            body.pop('temperature')
            body['reasoning_effort'] = 'high'
            body['max_tokens'] = 12000
    started = time.perf_counter()
    record = {'name': name, 'case': case['id'], 'engine': 'llm', 'coordinateMode': coordinate_mode,
              'thinking': thinking, 'prompt': prompt, 'maxTokens': body['max_tokens']}
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(180, connect=12), trust_env=False) as client:
            response = await client.post(endpoint(profile, 'chat/completions'),
                                         headers={'Authorization': 'Bearer '+unprotect_key(profile.get('apiKeyProtected'))}, json=body)
        record['latencySeconds'] = round(time.perf_counter()-started, 2)
        if response.status_code != 200:
            # Provider responses may contain sensitive data. Save only the status.
            record['error'] = 'HTTP '+str(response.status_code)
            return record
        data = response.json()
        record['usage'] = data.get('usage', {})
        record['returnedModel'] = data.get('model')
        choice = data['choices'][0]
        record['finishReason'] = choice.get('finish_reason')
        raw = choice['message']['content']
        record['rawResponse'] = raw
        usage = record['usage']
        with sqlite3.connect(DB) as db:
            db.execute('INSERT INTO model_usage(id,model,input_tokens,output_tokens,created_at,tokens_reported) VALUES(?,?,?,?,?,?)',
                       (str(uuid4()), profile['model'], usage.get('prompt_tokens', 0), usage.get('completion_tokens', 0), datetime.now(timezone.utc).isoformat(), 1))
        parsed = json.loads(raw.removeprefix('```json').removesuffix('```').strip())
        predictions = []
        for item in parsed['lines']:
            box = item['bbox']
            if len(box) != 4 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in box) or not isinstance(item['text'], str):
                raise ValueError('Invalid line schema')
            if coordinate_mode == 'normalized1000':
                box = [x*(case['width'] if i % 2 == 0 else case['height'])/1000 for i, x in enumerate(box)]
            predictions.append({'text': item['text'], 'bbox': box})
        record['predictions'] = predictions
        record['metrics'] = evaluate(case, predictions)
        overlay(case, predictions, name)
    except Exception as exc:
        record['latencySeconds'] = round(time.perf_counter()-started, 2)
        record['error'] = type(exc).__name__  # Never leak authentication or request contents.
    return record


def write_report(report):
    cases = json.loads((OUT / 'ground-truth.json').read_text(encoding='utf-8'))
    for run in report['runs']:
        if 'predictions' in run:
            case = next(c for c in cases if c['id'] == run['case'])
            run['metrics'] = evaluate(case, run['predictions'])
    report['totals'] = {'llmRequests': sum(r['engine'] == 'llm' for r in report['runs']),
                        'promptTokens': sum(r.get('usage', {}).get('prompt_tokens', 0) for r in report['runs']),
                        'completionTokens': sum(r.get('usage', {}).get('completion_tokens', 0) for r in report['runs'])}
    original = next((r for r in report['runs'] if r['name'] == 'columns-llm-pixels'), None)
    repeated = next((r for r in report['runs'] if r['name'] == 'columns-llm-repeat'), None)
    if original and repeated and 'predictions' in original and 'predictions' in repeated:
        repeated_boxes = {}
        for p in repeated['predictions']:
            repeated_boxes.setdefault(p['text'], []).append(p['bbox'])
        drifts = []
        for p in original['predictions']:
            candidates = repeated_boxes.get(p['text'], [])
            if candidates:
                chosen = min(candidates, key=lambda b: sum(abs(a-v) for a,v in zip(p['bbox'], b)))
                drifts.extend(abs(a-v) for a,v in zip(p['bbox'], chosen))
                candidates.remove(chosen)
        if drifts:
            report['repeatability'] = {'case': 'columns', 'maxEdgeDriftPx': max(drifts), 'meanEdgeDriftPx': statistics.mean(drifts)}
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    rows, cards = [], []
    for run in report['runs']:
        m = run.get('metrics', {})
        rows.append('<tr>'+''.join('<td>'+html.escape(str(v))+'</td>' for v in [run['name'], m.get('expected',''), m.get('returned',''),
            f"{m.get('exactTextRecall',0)*100:.1f}%", f"{m.get('located5pxRecall',0)*100:.1f}%", m.get('meanIoU',''),
            m.get('meanEdgeErrorPx',''), run.get('latencySeconds',''), run.get('error','')])+'</tr>')
        if 'metrics' in run:
            cards.append(f'<article><h2>{html.escape(run["name"])}</h2><img src="{run["name"]}-boxes.png"></article>')
    page = '''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>文字定位实测</title>
<style>body{font:15px "Segoe UI","Microsoft YaHei",sans-serif;background:#f6f3fc;color:#332944;margin:28px}table{border-collapse:collapse;background:white;width:100%}td,th{padding:10px;border-bottom:1px solid #e7dff4;text-align:left}article{background:white;border-radius:14px;padding:18px;margin-top:24px}img{max-width:100%;height:auto}h1{color:#784bd2}</style>
<h1>多模态 LLM 文字定位实测</h1><p>生成的虚构截图；绿色框 = 真实文字像素范围，红色框 = 识别坐标。没有把真实坐标提供给模型。</p>
<p>5px 定位合格率：四条边各自偏差均不超过 5 个原图像素；识别文字仅用于匹配，文字正确率单独显示。匹配忽略空白和英文大小写。表格按单元格、双栏按独立行评估。OCR 分栏依据词框间隙拆分；不把图片坐标传给 OCR。非思考模式温度为0，思考模式使用high强度。请求均限定输出长度，无自动重试。</p>
<table><thead><tr><th>测试</th><th>真实条目</th><th>返回条目</th><th>文字正确率</th><th>5px 合格率</th><th>平均 IoU</th><th>平均边界误差 px</th><th>耗时 s</th><th>错误</th></tr></thead><tbody>'''+''.join(rows)+'</tbody></table>'+''.join(cards)+'</html>'
    (OUT / 'report.html').write_text(page, encoding='utf-8')
    primary_llm = {r['case']: r for r in report['runs'] if r['name'] == r['case']+'-llm-pixels' and 'metrics' in r}
    baseline_ocr = {r['case']: r for r in report['runs'] if r['engine'] == 'windows-ocr' and 'metrics' in r}
    conclusions = []
    for label, runs in [('基础 LLM', primary_llm), ('Windows OCR', baseline_ocr)]:
        total = sum(r['metrics']['expected'] for r in runs.values())
        matched = sum(r['metrics']['matched'] for r in runs.values())
        correct = sum(sum(p['textSimilarity'] == 1 for p in r['metrics']['pairs']) for r in runs.values())
        located = sum(sum(p['maxEdgeErrorPx'] <= 5 for p in r['metrics']['pairs']) for r in runs.values())
        if total:
            conclusions.append(f'- {label}：匹配 {matched}/{total}，文字完全正确 {correct}/{total}（{correct/total*100:.1f}%），坐标合格 {located}/{total}（{located/total*100:.1f}%）。')
    summary = [
        '# 多模态 LLM 文字位置定位实测', '',
        '结论：当前 deepseek-flash 能完成本组测试图的文字识别和大致位置定位；精确原位翻译建议继续使用 OCR 获取文字框，由多模态 LLM 校正文字并翻译。', '',
        '## 测试方式', '',
        '- 4 张程序生成的虚构界面图片，合计 85 个文字行／表格单元格：普通文字、双栏、小字号深色界面、表格。',
        '- 字体为 Windows Microsoft YaHei；包含中文、英文、数字、重复文字、大小字号和低对比度文字。',
        '- 真实框来自绘制时实际非透明文字像素范围；模型只收到图片、图片尺寸和定位指令，没有收到真实框。',
        '- 真实调用当前已配置模型，要求输出逐行文字与 bbox JSON。基础测试关闭思考、temperature=0；另测 high 思考模式、归一化坐标和双栏重复调用。',
        '- 本地 OCR 对照为 Windows OCR（zh-Hans-CN）；逐词框按大间隙拆分成独立栏／单元格，再与真实文字匹配。没有调用 PaddleOCR，因此不能据此量化 PaddleOCR 的精度。',
        '- 定位合格：匹配文字框的四条边各自误差都 ≤5 原图像素，漏检计不合格。文字正确率独立统计，匹配时忽略空白和英文大小写。', '',
        '## 数据', '',
        '| 测试 | 条目数 | 文字正确率 | 定位合格率 ≤5px | 平均四边误差 px | 平均 IoU | 耗时 s |',
        '|---|---:|---:|---:|---:|---:|---:|',
    ]
    for run in report['runs']:
        if 'metrics' in run:
            m = run['metrics']
            summary.append(f"| {run['name']} | {m['expected']} | {m['exactTextRecall']*100:.1f}% | {m['located5pxRecall']*100:.1f}% | {m['meanEdgeErrorPx']} | {m['meanIoU']} | {run.get('latencySeconds', '批量')} |")
    summary.extend(['', '## 判断', '',
                    *conclusions,
                    '- 这是本组清晰合成图片的结果，不代表任意真实截图都能达到同样文字正确率。OCR 匹配受词框间隙分组和文本匹配方法影响。不能把 OCR 文字直接当作最终翻译原文。',
                    '- 表格基础模式出现逐行纵向漂移，后部文字没有完整被模型框覆盖；小字号文字框的宽度也存在明显误差。精确覆盖原文与拖选复制会受到影响。',
                    '- high 思考模式改善了表格定位，但未改善小字号深色界面；归一化坐标在本次测试中更差。不能通过这些设置简单替代 OCR。',
                    '- 建议：OCR 产出行／词框与位置，多模态 LLM 结合图片校正原文并返回带稳定ID的译文；渲染时始终使用 OCR 坐标。分栏与表格分组、译文字号、遮盖背景和文字选择应由本地布局逻辑处理。',
                    '- 本次只测试定位与识别，没有评估翻译质量、整套原位翻译体验，也没有接入或修改产品翻译功能。', '',
                    '## 可查看文件', '',
                    '- [可视化报告](report.html)：绿色为真实文字框，红色为识别框。',
                    '- [原始响应与指标](report.json)',
                    '- [文字与真实坐标](ground-truth.json)', '',
                    f"真实模型请求 {report['totals']['llmRequests']} 次；输入 {report['totals']['promptTokens']} tokens，输出 {report['totals']['completionTokens']} tokens（包括思考 tokens）。用量已计入软件的本地模型用量记录。",
                    f"Windows OCR 全部4张图批量耗时：{report.get('ocrBatchLatencySeconds')}s（包括进程启动）。", '',
                    '模型图像接口：[DeepSeek 官方图像理解文档](https://api-docs.deepseek.com/zh-cn/guides/vision/)。',
                    '思考模式参数：[DeepSeek 官方思考模式文档](https://api-docs.deepseek.com/zh-cn/guides/thinking_mode/)。', '',
                    '复现：`python scripts/benchmark-vision-location.py` 只生成图片并运行本地 OCR；添加 `--live --extended` 才发起付费模型调用。`--report-only` 只重算已有报告。',
                    ])
    (OUT / 'RESULTS.md').write_text('\n'.join(summary)+'\n', encoding='utf-8')


async def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--live', action='store_true', help='Send only generated fixtures to the configured active model (billable).')
    parser.add_argument('--skip-local', action='store_true')
    parser.add_argument('--case', choices=['simple', 'columns', 'dense-dark', 'table'])
    parser.add_argument('--extended', action='store_true', help='Add repeatability and normalized-coordinate runs.')
    parser.add_argument('--thinking', action='store_true', help='Enable the model thinking mode at high effort.')
    parser.add_argument('--append', action='store_true', help='Append measurements to the existing report.')
    parser.add_argument('--report-only', action='store_true', help='Recompute the saved report without any OCR or model calls.')
    args = parser.parse_args()
    OUT.mkdir(parents=True, exist_ok=True)
    if args.report_only:
        write_report(json.loads((OUT / 'report.json').read_text(encoding='utf-8')))
        print('Existing report refreshed; no model calls.', flush=True)
        return
    cases = fixtures()
    (OUT / 'ground-truth.json').write_text(json.dumps(cases, ensure_ascii=False, indent=2), encoding='utf-8')
    selected = [c for c in cases if not args.case or c['id'] == args.case]
    report = {'createdAt': datetime.now(timezone.utc).isoformat(), 'syntheticOnly': True, 'runs': []}
    if args.append and (OUT / 'report.json').exists():
        report = json.loads((OUT / 'report.json').read_text(encoding='utf-8'))
    if not args.skip_local:
        started = time.perf_counter()
        payload = {'locations':True,'images': [base64.b64encode((OUT / (c['id']+'.png')).read_bytes()).decode('ascii') for c in selected]}
        try:
            result = subprocess.run([sys.executable,str(ROOT / 'backend' / 'app' / 'windows_ocr.py')], input=json.dumps(payload),
                                    capture_output=True, text=True, encoding='utf-8', timeout=90, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode:
                raise RuntimeError('Local OCR process failed')
            output = json.loads(result.stdout.lstrip('\ufeff'))
            report['ocrLanguage'] = output['language']
            report['ocrBatchLatencySeconds'] = round(time.perf_counter()-started, 2)
            for case, document in zip(selected, output['documents']):
                predicted = ocr_spans(document)
                name = case['id']+'-windows-ocr'
                run = {'name': name, 'case': case['id'], 'engine': 'windows-ocr', 'predictions': predicted,
                       'metrics': evaluate(case, predicted)}
                report['runs'].append(run)
                overlay(case, predicted, name)
                print(json.dumps({'name': name, 'metrics': {k:v for k,v in run['metrics'].items() if k not in ('pairs','missedTruth','unmatchedPredictions')}}, ensure_ascii=True), flush=True)
        except Exception as exc:
            report['ocrError'] = type(exc).__name__
            print('Local OCR: '+type(exc).__name__, flush=True)
        write_report(report)
    if args.live:
        profile = get_active_profile(DB)
        if not profile or not profile.get('vision') or profile.get('provider') != 'openai-compatible':
            raise RuntimeError('An active image-capable OpenAI-compatible model is required')
        report['model'] = profile['model']
        jobs = [(c, c['id']+'-llm-pixels', 'pixels') for c in selected]
        if args.extended and not args.case:
            jobs.extend([(cases[1], 'columns-llm-repeat', 'pixels'), (cases[2], 'dense-dark-llm-normalized', 'normalized1000')])
        for case, name, mode in jobs:
            if args.thinking:
                name += '-thinking'
            print('Calling '+profile['model']+': '+name, flush=True)
            run = await live(profile, case, name, mode, args.thinking)
            report['runs'].append(run)
            write_report(report)
            print(json.dumps({k:v for k,v in run.items() if k in ('name','error','latencySeconds','usage','finishReason')} | {
                'metrics': {k:v for k,v in run.get('metrics', {}).items() if k not in ('pairs','missedTruth','unmatchedPredictions')}}, ensure_ascii=True), flush=True)
            if run.get('error', '').startswith('HTTP '):
                print('Stopping after provider rejection; no automatic retry.', flush=True)
                break
    print('Report: artifacts/vision-location/report.html', flush=True)


if __name__ == '__main__':
    asyncio.run(main())
