"""Build the optimization report from recorded real-service measurements."""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'artifacts/agent-query-optimized'

def read(relative):
    return json.loads((ROOT / relative).read_text(encoding='utf-8'))

before = read('artifacts/agent-query-tests/repeated/results.json')
after = read('artifacts/agent-query-optimized/json-repeated/results.json')
regression = read('artifacts/agent-query-optimized/regression/results.json')
voice = read('artifacts/agent-query-optimized/voice-results.json')
names = {'ocr': '文字提取', 'translate': '原位翻译', 'crop': '坐标裁剪'}
summary = []
for key, name in names.items():
    old = [r['timing'] for r in before['cases'] if r['id'] == key]
    new = [r['timing'] for r in after['cases'] if r['id'] == key]
    old_total = median(r['totalSeconds'] for r in old)
    new_total = median(r['totalSeconds'] for r in new)
    summary.append(dict(id=key, name=name, count=len(new),
        beforeTotalMedian=old_total, afterTotalMedian=new_total,
        beforeFirstTextMedian=median(r['firstTextSeconds'] for r in old),
        afterFirstTextMedian=median(r['firstTextSeconds'] for r in new),
        afterTotalRange=[min(r['totalSeconds'] for r in new), max(r['totalSeconds'] for r in new)],
        reductionPercent=100 * (1 - new_total / old_total)))
report = dict(text=summary, textPassed=after['passed'], textTotal=after['total'],
    regressionPassed=regression['passed'], regressionTotal=regression['total'],
    voicePassed=sum(r['passed'] for r in voice['rows']), voiceTotal=len(voice['rows']),
    asrConnections=voice['asrConnections'], microphoneUsed=voice['microphoneUsed'],
    voiceTiming=[dict(case=r['case'], **r['timing']) for r in voice['rows']])
(OUT / 'summary.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
lines = ['# Agent 耗时优化与语音链路复测', '',
    '2026-10-11；使用已配置的真实 LLM、ASR、TTS 和工具。测试图片与输入语音为合成素材，不读取用户截图，不写入测试会话。', '',
    '## 文字查询', '',
    '每项前后各测 3 次。下表为中位数；首字指第一个用户可见文本片段，总耗时包含规划、工具、最终回复。云端负载和模型决策存在波动，小样本不能代表 P95。', '',
    '| 操作 | 首字：之前 → 之后 | 总耗时：之前 → 之后 | 总耗时降低 | 之后总耗时范围 |',
    '|---|---:|---:|---:|---:|']
for row in summary:
    low, high = row['afterTotalRange']
    lines.append(f"| {row['name']} | {row['beforeFirstTextMedian']:.2f} → {row['afterFirstTextMedian']:.2f} 秒 | {row['beforeTotalMedian']:.2f} → {row['afterTotalMedian']:.2f} 秒 | {row['reductionPercent']:.0f}% | {low:.2f}–{high:.2f} 秒 |")
lines += ['', f"最终重复测试 {after['passed']}/{after['total']}；多步骤、撤销、短期记忆、长期偏好覆盖、模糊需求和缺图回归 {regression['passed']}/{regression['total']}。", '',
    '优化包括精简规划工具目录、规划 JSON 输出约束、单工具完成后直接返回实际结果，避免再次规划和总结；参数与结果校验保持不变，多步骤仍继续执行。一次 OCR 仍花费约 10 秒，因为模型没有声明工具已完成任务，额外生成了总结。这不是保证所有请求都在中位数以内。', '',
    '## 语音查询', '',
    f"链路检查 {report['voicePassed']}/{report['voiceTotal']}：识别真实输入、调用相应工具、输出回复和播放首段音频。8 轮共用 1 个连续 ASR 连接；撤销高亮和裁剪另校验前后图像数据完全一致。", '',
    '说完后等待 = 首次开始播放时间减去输入音频长度；包含 ASR 结束判定、450 毫秒片段合并、模型规划、工具、TTS。下表 ASR 首段从开始说话计时，TTS 首包从发起该段合成计时。只测量首个朗读片段，不是整段回复合成完成时间。', '',
    '| Query | ASR 首段 | Agent 完成 | TTS 首包 | 说完后首次播放 |',
    '|---|---:|---:|---:|---:|']
voice_names = dict(ocr='文字提取', highlight='高亮标题', undo_highlight='撤销高亮',
    translate='原位翻译', table='表格提取', crop='裁剪标题行', undo_crop='撤销裁剪', ambiguous='模糊请求澄清')
for row in voice['rows']:
    t = row['timing']
    lines.append(f"| {voice_names[row['case']]} | {t['asrFirstPartialSeconds']:.2f} 秒 | {t['agentSeconds']:.2f} 秒 | {t['ttsFirstPacketSeconds']:.2f} 秒 | {t['afterSpeechEndsToAudibleSeconds']:.2f} 秒 |")
lines += ['',
    '独立真实 TTS 流式测试：首包 1.096 秒，接收完成 4.806 秒，46 个音频包；实际播放器在接收完成前开始播放，暂停/继续通过。', '',
    '发现并修复：较长的翻译请求在停顿处被 ASR 拆分，前半句提前触发文字提取。当前共享语音输入层先合并相邻片段，再提交整句；中间文本仍即时显示。', '',
    '质量与性能限制：高亮标题发生 OCR 唯一匹配失败，Agent 根据真实 OCR 结果重试后完成，因此说完后等待约 15 秒；本次翻译遗漏了“数量”表头，Agent 已明确报告漏译。8/8 表示链路和意图检查通过，不表示全部像素文字识别、翻译质量达到 100%。OCR 匹配和覆盖率仍需进一步改善。', '',
    '此次使用合成 PCM 以实时速度送入真实 ASR，不使用物理麦克风；不能据此确认本机麦克风权限、设备采集、扬声器音量或外放回声消除。', '',
    '## 截图操作与撤销', '',
    '操作应用于当前截图画布的工作副本与图层，保留原始截图数据，不自动覆盖磁盘文件。裁剪、翻译和标注的结果进入画布，保存/导出生成最终图像。文字与语音均可使用“撤销刚才的操作”，恢复活动截图窗口内上一份快照。重新打开历史会话不会恢复窗口内撤销栈。', '',
    '后端跨查询撤销验证图片字节一致；语音界面回归验证请求携带上一次真实快照、撤销后标注从 1 个恢复为 0 个，且操作更新实际截图状态。', '',
    '## 本地回归', '',
    '后端全量 315 项通过（226.25 秒）；新增规划 JSON 模式和记忆专项合计 44 项通过（33.16 秒）。前端类型检查和生产构建通过。语音界面、分句流式播放、ASR 片段合并、聊天消息回归通过；这些界面回归使用受控服务，与上面的真实云端测试分开。构建仍有既有大体积 chunk 提示。', '',
    '## 原始记录与复测', '',
    '- [最终文字记录](json-repeated/results.json)',
    '- [多步骤和记忆回归](regression/results.json)',
    '- [真实语音原始结果](voice-results.json)',
    '- [修复片段合并前的语音记录](voice-before-turn-join.json)',
    '- [此前 JSON 修复失败记录](final-repeated/results.json)', '',
    '```powershell',
    'python scripts/benchmark-agent-queries.py --cloud --cases ocr,translate,crop --repeat 3 --output artifacts/agent-query-optimized/retest',
    'node scripts/benchmark-voice-queries.mjs --cloud',
    'node scripts/verify-voice-call.mjs',
    'node scripts/verify-voice-call-stream.mjs',
    'node scripts/verify-speech-turns.mjs',
    'python scripts/summarize-agent-optimization.py',
    '```', '',
    '浏览器测试需要前端 5174 已启动并连接测试后端。复测语音脚本会更新 voice-results.json。', '',
    '规划 JSON 模式依据 [DeepSeek 官方接口文档](https://api-docs.deepseek.com/api/create-chat-completion/) 与 [Ollama 结构化输出文档](https://github.com/ollama/ollama/blob/main/docs/capabilities/structured-outputs.mdx) 实现；业务工具完整 Schema 仍在本地 Harness 校验。', '']
(OUT / 'REPORT.md').write_text('\n'.join(lines), encoding='utf-8')
print(json.dumps(report, ensure_ascii=True))
