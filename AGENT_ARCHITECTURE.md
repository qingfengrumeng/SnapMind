# SnapMind 单 Agent 架构

自然语言入口与语音通话共用 `POST /api/capture/conversation?stream=true`。只有一个 Agent：采样下一步决策 → Harness 校验 → 执行工具 → 读取真实观测 → 再次决策 → 流式回复。显式工具按钮通过 `/api/tools/call` 进入相同的校验与执行层，省去需求分析。

## 项目目录

```text
backend/app/agent/
  workflow.py     单 Agent ReAct 循环、取消、总超时与步数上限
  schemas.py      决策、工具参数、结果及执行上限的严格 Schema
  harness.py      参数与结果校验、坐标来源检查、有限重试与执行记录
  tools.py        工具白名单与现有业务服务适配器
  state.py        本轮工作图片、标注、多步结果与撤销快照
  rendering.py    生成下一步工具实际读取的工作图片
  memory.py       复用已有记忆上下文，分配观测预算
backend/app/
  conversation_runtime.py  会话锁、幂等请求、记忆计划与结果落盘
  session_memory.py        最近对话、历史摘要、跨会话记忆检索及提取
frontend/src/
  agent-results.ts          统一多步结果解析与工具进度名称
  components/ImageConversation.vue  文字请求、进度、按序应用多步结果
  components/CaptureOverlay.vue     语音请求及截图操作
```

## 工具

19 个工具：`ocr`、`offline`、`translate`、`table`、`detect`、`annotate`、`qr`、`entities`、`crop`、`highlight`、`mosaic`、`heal`、`lift`、`region`、`answer`、`draw`、`blur`、`undo`、`clear_annotations`。

例如“请将截图内容原位翻译成中文”：Agent 选择 `translate`，工具 OCR 定位并翻译真实文字，校验每行坐标和结果尺寸，前端应用译文。决策通过 `done=true` 表示该工具满足本轮全部需求，成功后直接返回工具真实结果，省去再次规划和总结；多步要求保持 ReAct 循环，直到全部完成。规划传输精简后的工具 Schema，并使用 JSON 输出模式；完整参数与结果约束仍由 Harness 校验。

`GET /api/tools` 返回实际注册工具与 JSON Schema。新增工具需要注册名称、参数 Schema、适配器及结果校验；无需增加 Agent。保存、复制、贴图等桌面生命周期操作仍由已有工具栏触发；当前 Agent 工具范围为截图分析与编辑，不执行任意 Shell 或操作系统命令。

## Harness

- JSON 决策只允许 `kind=tool`（名称和参数）或 `kind=final`。工具名必须在白名单内。
- Pydantic 严格模式拒绝未知字段、类型转换、非法枚举、缺失参数和不合法范围。
- 裁剪和绘制坐标必须来自用户明确提供的像素范围、真实工具观测或已有控件位置，禁止猜测；文字操作通过 OCR 唯一匹配原文。
- 工具结果再次校验，包括图片尺寸、标注 ID、行框和结构化表格；大图数据与密钥不进入规划观测。
- 默认最多 8 步，每步最多 3 次决策修复；暂时性服务错误最多执行 2 次，鉴权或参数错误不会盲目重试同一工具。
- 单个工具最多 120 秒，整轮最多 240 秒。取消流式连接会取消工作任务；未得到最终成功结果时，不向截图界面提交本轮编辑。
- 成功调用去重，避免同一决策反复修改图片。`undo` 支持本轮编辑和当前截图窗口内跨查询撤销：前端传入 `undoSnapshot`，后端校验其图片 ID、尺寸和标注，前端恢复实际图像及图层。快照只保留在活动窗口中，重新打开历史会话不恢复撤销栈。原始截图保留，操作应用于当前截图工作副本与图层，导出时才生成结果图片。
- 流式事件为 `agent_status`、`tool_result`、`chunk`、`result` 或 `error`，只展示执行进度，不展示模型隐藏推理。

## 记忆

不新增第二套记忆数据库。每个请求使用当前 `sessionId`、`turnId` 和用户消息 ID：服务器读取完整会话，生成上下文计划并注入每一次模型调用，包括决策、工具中的模型调用和最终回复。没有会话 ID 的临时请求使用传入历史，也会检索跨会话记忆，但无法自动压缩完整历史。

短期记忆保留最近至少 10 轮用户对话；历史超出预算时由 LLM 生成累计摘要，原始记录仍保留。工具 Schema、图片、观测和回复均计入预算；超限会明确返回错误。策略在 `.snapmind/config.toml` 的 `[memory]` 中配置。

长期记忆默认在会话闲置 6 小时后由后台 LLM 提取，并非关闭窗口立即提取。仅接受有用户原文证据和消息 ID 的可复用偏好、事实或方法，过滤凭证、暂时状态与未经确认的助手建议。每次查询按相关性检索；当前用户要求优先于长期偏好。编辑、删除会话后派生记忆会按会话版本失效。

会话、上下文计划、决策校验、工具参数、真实结果和完成事件继续写入 `.snapmind` 现有本地存储，可回查执行轨迹；不写入演示对话、模拟识别结果或模型编造的工具结果。

## 验证

连续语音通过一个 ASR 连接传输 PCM、展示中间文本；VAD 结束后的片段合并等待为 450 毫秒，期间继续说话会延迟提交，避免半句话先触发工具。Agent 回复按句进入流式 TTS 播放，取消和挂断清理待提交片段。

真实服务性能及语音测试结果见 `artifacts/agent-query-optimized/REPORT.md`。`scripts/benchmark-agent-queries.py` 测量模型规划、工具和首字/总耗时；`scripts/benchmark-voice-queries.mjs` 使用合成语音与图片调用真实 ASR、Agent、TTS，验证跨轮撤销及首段音频流式播放，不替代物理麦克风测试。

高亮匹配及翻译覆盖修复结果见 `artifacts/ocr-quality/REPORT.md`。`ocr_recovery.py` 用像素检测得到固定文字条带，Windows OCR 同进程批量补识别；`text_target.py` 只允许视觉模型复核已有 OCR 行 ID 的原文，不生成坐标。翻译将未覆盖的文字区域加入同一次逐行请求并校验原文与译文，活动 Agent 状态缓存同图的 OCR 定位结果。

`python -m pytest backend/tests -q`、`npm run typecheck`；Agent 专项测试在 `backend/tests/test_agent.py`，覆盖参数校验、坐标证据、决策修复、多步编辑、撤销、调用去重和暂时性服务错误重试。测试用合成图片和受控模型响应，生产流程使用实际配置的 LLM/OCR。
