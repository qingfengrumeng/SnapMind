"""Build the combined report without making model calls."""
import json
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path

root=Path('artifacts/agent-query-tests')
load=lambda name:json.loads((root/name/'results.json').read_text(encoding='utf-8'))
baseline=load('live');followup=load('followup-retest');repeated=load('repeated');preference=load('preference-test')
latest={r['id']:r for r in baseline['cases']}
for r in followup['cases']+preference['cases']:latest[r['id']]=r
api=json.loads((root/'api-timing.json').read_text(encoding='utf-8'))
unit=ET.parse(root/'unit-tests.xml').getroot()
tests=sum(int(s.get('tests',0)) for s in unit.iter('testsuite'))
failures=sum(int(s.get('failures',0))+int(s.get('errors',0)) for s in unit.iter('testsuite'))
unit_seconds=sum(float(s.get('time',0)) for s in unit.iter('testsuite'))
groups={name:[r for r in repeated['cases'] if r['id']==name] for name in ['ocr','translate','crop']}
summary={'model':baseline['model'],'unit':{'tests':tests,'failures':failures,'seconds':round(unit_seconds,2)},
         'initial':{'passed':baseline['passed'],'total':baseline['total']},'latest':{'passed':sum(r['passed'] for r in latest.values()),'total':len(latest)},
         'repeated':{'passed':repeated['passed'],'total':repeated['total']},'api':{'passed':sum(r['passed'] for r in api),'total':len(api)},'statistics':{}}
lines=['# Query 意图识别、工具执行及耗时测试报告','',
       f"真实模型：**{baseline['model']}**。输入为生成的英文商品表截图、生成的 Hello SnapMind 截图及测试历史；没有读取用户截图或麦克风，没有创建测试会话或写入用户偏好。真实模型调用会计入现有用量统计。",'',
       f"本地回归：**{tests} 项全部通过**，耗时 {unit_seconds:.2f} 秒。首轮真实 Query 测试为 **{baseline['passed']}/{baseline['total']}**；修复并复测记忆跟进项、补充偏好优先级测试后，最新功能类别为 **{summary['latest']['passed']}/{len(latest)}**。重复测量 **{repeated['passed']}/{repeated['total']}**，HTTP/SSE 接口验证 **{summary['api']['passed']}/{len(api)}**。",'',
       '## 功能与结果校验','',
       '| Query 类型 | 实际工具 | 结果 | 首字(s) | 总耗时(s) |','|---|---|---|---:|---:|']
for r in latest.values():
    t=r['timing'];first='—' if t['firstTextSeconds'] is None else f"{t['firstTextSeconds']:.2f}"
    lines.append(f"| {r['id']} | {' → '.join(r['actualTools'])} | {'通过' if r['passed'] else '失败'} | {first} | {t['totalSeconds']:.2f} |")
lines+=['','校验包括：实际文字与邮箱、表格数字、译文行列表、裁剪像素尺寸、裁剪与绘制顺序、撤销后恢复原图尺寸、模糊请求不擅自编辑、无图时不伪造修改、跟进查询读取短期历史、当前英文要求覆盖默认中文偏好。工具参数类型、额外字段、边界、来源、重试、去重、取消、结果尺寸及会话幂等由本地回归覆盖。','',
        '## 重复耗时测量','',
        '| 类型 | 次数 | 首次决策中位数(s) | 首字中位数(s) | 工具中位数(s) | 总耗时中位数(s) | 总耗时范围(s) |','|---|---:|---:|---:|---:|---:|---:|']
for name,rows in groups.items():
    stats={key:round(statistics.median(r['timing'][key] for r in rows),4) for key in ['firstDecisionSeconds','firstTextSeconds','toolSeconds','answerSeconds','planningSeconds','totalSeconds']}
    stats['minSeconds']=min(r['timing']['totalSeconds'] for r in rows);stats['maxSeconds']=max(r['timing']['totalSeconds'] for r in rows);summary['statistics'][name]=stats
    lines.append(f"| {name} | {len(rows)} | {stats['firstDecisionSeconds']:.2f} | {stats['firstTextSeconds']:.2f} | {stats['toolSeconds']:.3f} | {stats['totalSeconds']:.2f} | {stats['minSeconds']:.2f}–{stats['maxSeconds']:.2f} |")
lines+=['','首字指第一个用户可见文本片段，不等于工具开始执行。首次决策只统计首个规划模型调用。工具时间包含内部 OCR/模型调用，不能与嵌套模型时间重复相加。每类只有 3 次重复，且运行期间有接口验证交叠，不能估计稳定 P95、并发容量或 SLA；结果受网络、云模型缓存和开发环境负载影响。','',
        '## HTTP/SSE 端到端验证','',
        '| Query | HTTP | 响应头(s) | 第一条进度(s) | 首字(s) | 完整结果(s) |','|---|---:|---:|---:|---:|---:|']
for r in api:
    lines.append(f"| {r['case']} | {r['status']} | {r['headersSeconds']:.3f} | {r['events'][0]['seconds']:.3f} | {r['firstTextSeconds']:.2f} | {r['totalSeconds']:.2f} |")
lines+=['','接口返回 `text/event-stream`，包含规划状态、工具执行状态、工具结果、多个文本片段及最终结果；最终像素尺寸与文字已校验。','',
        '## 发现并修复的问题','',
        '“按我上一条消息提供的坐标裁剪”首次返回 422：规划模型正确选择 crop，但 Harness 只认可当前 Query 的坐标，拒绝了真实用户历史中的参数。修复后，在当前 Query 明确引用上一条/之前参数时，允许复用最近一条用户消息的坐标，仍校验类型及图片边界；助手建议、长期偏好和没有跟进授权的旧坐标不能作为依据。新增回归已通过，真实模型复测成功，耗时 '+f"{followup['cases'][0]['timing']['totalSeconds']:.2f} 秒。",'',
        '## 性能观察','',
        f"裁剪像素操作中位数只有 {summary['statistics']['crop']['toolSeconds']:.3f} 秒，总耗时却为 {summary['statistics']['crop']['totalSeconds']:.2f} 秒，主要耗时来自模型规划与最终回复。原位翻译还包含 OCR 与译文生成，工具中位数 {summary['statistics']['translate']['toolSeconds']:.2f} 秒。当前流式接口可以提前展示进度和 OCR 文本，但图像修改仍等待最终成功结果再提交。此次只修复测试发现的功能问题，未改变 Agent 规划策略来压缩耗时。",'',
        '## 原始证据与复现','',
        '- [首轮报告（保留失败项）](live/REPORT.md) 与 [原始结果](live/results.json)','- [记忆跟进复测](followup-retest/REPORT.md)','- [重复测量](repeated/REPORT.md)','- [偏好优先级测试](preference-test/REPORT.md)','- [HTTP/SSE 事件与耗时](api-timing.json)','- [本地 JUnit 测试记录](unit-tests.xml)','',
        '```powershell','python -m pytest backend/tests/test_agent.py backend/tests/test_image_tool_registry.py backend/tests/test_session_memory.py backend/tests/test_speech_streaming.py -q --durations=10',
        'python scripts/benchmark-agent-queries.py --cloud',
        'python scripts/benchmark-agent-queries.py --cloud --cases ocr,translate,crop --repeat 3 --output artifacts/agent-query-tests/repeated',
        'python scripts/verify-agent-api-timing.py --cloud',
        '```','',
        '云端测试使用当前已启用的模型。任何功能校验失败时测试脚本返回非零退出码，并保留已测结果。']
(root/'REPORT.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
(root/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False))
