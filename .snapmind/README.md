# SnapMind 本地数据与记忆

本目录是 SnapMind 的运行数据根目录。实现参考项目根目录的 `SESSION_MEMORY_DESIGN.md`，采用可追溯会话事件、上下文压缩和长期记忆的设计；不声称与 Codex 内部文件格式完全相同。

## 目录与职责

```text
./.snapmind/
  config.toml                    记忆及上下文策略（启动时创建）
  models.json                    LLM / OCR / ASR&TTS 模型配置
  preferences.json               原生截图快捷键
  ui-preferences.json            主题、语言、工具快捷键等界面设置
  state_1.sqlite                 会话查询投影、待写队列、运行、摘要、记忆及任务状态
  session_index.jsonl             可重建的会话索引
  sessions/YYYY/MM/DD/
    rollout-时间-会话ID.jsonl      原始消息、工具事件、上下文与每版摘要
  memories/local/
    memory_summary.md            可读记忆索引
    MEMORY.md                    有来源的有效长期记忆
    raw_memories.md               通过来源校验的候选记忆
    rollout_summaries/会话ID.md   会话来源索引
    projects/snapmind.md          当前本地项目的记忆视图
  data/
    snapmind.sqlite3             模型用量、OCR 用量及业务配置
    images/local/内容哈希.扩展名  原图和工具生成的图像，按内容去重
    artifacts/local/             预留：笔记、报表及其他产物
    uploads/local/               预留：非图片资料
  backups/
    legacy/                     旧数据库和配置的迁移备份与清单
    business/                   分离会话前的业务库备份
    state/                      删除标记和修复前的残缺 JSONL 尾行
  cache/browser/                 桌面 WebView 的本地缓存和 localStorage
  thread-writer-locks/           跨线程、跨进程文件锁
  logs/                         运行日志
  tmp/                          临时文件
```

代码、依赖、构建产物和测试截图仍在项目原有目录；本目录收纳应用运行时信息。用户点击导出、保存图片时仍可自行选择输出位置。

## 会话与恢复

- 会话文件路径由首次创建的 UTC 时间和稳定 ID 决定，改标题或跨天续聊不会换文件。
- 每个事件包含 `seq`、`event_id`、`timestamp`、`type`、`payload`。同一消息编辑后追加新版本，删除则追加删除事件。会话状态记录消息顺序与图片文件引用，不反复复制全部正文和图片 base64。
- SQLite 投影和待写事件在同一事务提交。JSONL 追加、落盘后才将队列标记为已投递；重启及后台任务重试，按事件 ID 去重。已投递队列不再保留正文。
- JSONL 已完成行损坏会明确报错；只有没有换行结束的残缺尾部可以修复，原始尾部留在备份中。缺失的会话投影可以从日志重建。
- 对话模型调用前保存请求，完成后保存回复和工具结果。失败请求也保留原始输入。同一个 `sessionId + turnId` 的完成请求直接返回原结果，不重复调用工具。
- 普通工作区对话也记录运行与回复；回复先落盘，再进行流式展示，同一用户消息 ID 的重复请求返回已保存结果。
- 删除会话时清除投影、队列、运行、摘要和相关记忆，并删除该会话日志。图片按内容共享，删除会话不会立即删除图片或迁移备份。备份可能包含历史内容，需要彻底清理时应同时处理备份。

## 短期记忆

短期记忆是每次请求构建的上下文，不维护独立的 `short_memory.md`。

低于阈值时使用有效历史。超过阈值时，通过已启用的模型合并较旧的内容，保留最近 **十轮用户对话及其完整回复**。摘要存储覆盖消息 ID、内容指纹、保留窗口、上版摘要 ID；后续新轮次继续累计。编辑或删除来源后，旧摘要不再使用。原始日志不会因压缩被删除。

默认上下文 32,000、压缩阈值 24,000、回复预留 4,096。当前使用 UTF-8 字节数作保守文本估计，每张图额外预留 2,048；这不是供应商精确计费 token 数。模型实际窗口不同，应调整 `config.toml`。最近十轮、当前工具请求或图片仍超预算时返回明确错误，不悄悄丢弃消息。摘要需要已启用的模型，会产生模型调用及用量。

## 长期记忆

后台默认每 60 秒检查，选择至少两轮用户消息、闲置至少 6 小时、最近 30 天活跃且没有正在运行请求的会话，每批最多 16 个。未启用模型时保留历史，暂不生成模型提取的记忆。失败任务 5 分钟后可重试。

模型候选必须包含原始用户消息 ID 和逐字证据。不存在的来源、助手建议、无证据候选及检测到的凭证被排除。原始提取事件保留在该会话日志，有效记忆保存到 SQLite 并发布为 Markdown。历史变化立即使旧记忆失效；读取只允许当前来源版本。跨会话按关键词相关度、用户偏好及预算选取，作为历史参考发送给模型，当前用户要求优先。

当前应用没有账号系统，所有记录属于本地 `local` 用户和 `snapmind` 项目。未来接入多用户或多个知识项目时，需要增加明确的权限、项目范围及检索过滤，不能直接将当前单用户目录作为权限隔离。

## 语音合成

模型配置页的 `ASR&TTS` 区域独立保存语音配置，ASR 与 TTS 各选择一个启用模型。启动时导入 `backend/.env` 中的 `MINDPILOT_ASR_*`、`MINDPILOT_TTS_*`；使用摘要标识导入版本，未改变环境配置时不会覆盖页面中保存的修改。测试或自定义数据目录不会自动导入真实凭证。

Qwen TTS 使用 WebSocket 的 `run-task → task-started → continue-task → finish-task` 流程接收 MP3；聊天朗读和音色试听均由后端调用，浏览器不接收 API Key。每次发送文本最多 20,000 字符、单任务最多 200,000 字符。当前先合成完整音频再播放，暂停/继续复用音频；切换消息、离开页面或取消准备中的朗读会释放播放器并取消请求。

- `GET /api/settings/speech`：语音配置列表，仅返回密钥是否存在。
- `PUT /api/settings/speech/{id}`：保存配置；修改已启用配置后需重新启用。
- `PUT /api/settings/speech/active`：独立选择 ASR 或 TTS 模型。
- `POST /api/settings/speech/{id}/test`：测试 WebSocket 连接及鉴权，不检查音色是否可用。
- `POST /api/settings/speech/{id}/preview`：使用当前表单配置试听短句。
- `POST /api/speech/synthesize`：使用已启用 TTS 生成音频。
- `WS /api/speech/recognize`：使用已启用 ASR 实时转写。浏览器发送单声道 PCM16 小端二进制帧，服务端先回复 `ready`（包含采样率），再回复 `transcript`（实时文字及已确认文字）；发送 `{"type":"finish"}` 后等待 `done`（最终文字）。取消可发送 `{"type":"cancel"}` 或关闭连接。
- `POST /api/settings/speech/{id}/voices`：使用表单中的 TTS 模型获取官方系统音色目录，返回模型、音色 ID、显示名称、描述、试听语言和来源。支持 Qwen-Audio 3.1 Flash、3.0 Flash / Plus，按模型隔离；无需启用或保存配置，不发送密钥到文档站点。Qwen 的 `list_voice` 接口仅查询账号复刻音色，系统音色以[官方音色目录](https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list)为准；目录结构或网络异常时明确报错，可手动输入音色 ID。

模型配置导航分别为 LLM、OCR、ASR、TTS。ASR 使用通用麦克风图标，TTS 使用通用声波图标；各导航只显示对应配置，去掉重复的小标题，各自添加和启用配置。切换 ASR/TTS 保留未保存的表单修改。音色、语言、采样率共用模型列表下拉组件；音色选项右侧可独立试听，试听不会修改所选音色，英文音色使用英文试听文本。更换音色、配置参数、折叠卡片、切换导航或离开页面时停止试听并释放音频。当前后端适配 DashScope；其他供应商需要后续添加协议适配。

麦克风权限失败仅在精灵的错误面板标红，不改变介绍/回复颜色。Windows 返回 `Permission denied by system` 时明确提示系统层拒绝实际开麦，浏览器权限的 `granted` 不代表 Windows 一定允许设备访问。桌面精灵提供“打开麦克风设置”，通过 `POST /api/settings/microphone/open` 打开固定的 `ms-settings:privacy-microphone` 页面；不修改系统隐私开关。用户检查麦克风访问和桌面应用访问权限后可重新连接。

ASR 使用 Qwen-ASR-Realtime 的 `session.update`、VAD 和 `session.finish` 事件；支持 16,000 / 8,000 Hz，默认中文，可配置自动识别及其他语言。普通录音连接最长两分钟。麦克风按钮实时填入输入框，停止后可修改再发送；按住说话在松开并完成识别后发送文字给 AI。不会自动保存原始录音。普通录音取消、页面关闭或失去焦点会关闭麦克风；识别失败不自动发送。

截图工具栏的“语音通话”（默认快捷键 X）显示前端 SVG/CSS 精灵“小洁”，可拖动、点击跳动，首先合成并朗读固定自我介绍。通话复用已启用的 ASR、LLM 与 TTS：实时 PCM 转写，VAD 完成一句话后自动交给现有截图 Agent，执行识字、翻译、标注等工具，把可视结果应用到截图并加入撤销栈，再合成回答。识别的 `speech-started` 事件立即打断未完成回答或朗读；生成和播放期间继续监听，后续语句带此前对话上下文。通话使用 `WS /api/speech/recognize?continuous=true` 的持续连接，实时返回 `transcript`，断句后返回 `utterance`，不等待 `session.finish`、不重新开麦；单条持续连接最长 30 分钟。

通话与普通录音的焦点行为不同：通话允许切换到其他应用时继续监听，精灵中明确显示麦克风已开启。暂停、挂断、完成截图、切换到文字对话、选区变化和组件销毁会释放麦克风、关闭识别连接、取消请求和音频播放，忽略过期回复。通话文字和截图保存为正常图片对话会话，自动生成截图标题，沿用 `.snapmind` 会话及长期记忆规则；不保存原始录音。页面权限、模型配置或网络错误在精灵中显示，可显式重新连接。

朗读和音色试听使用 `POST /api/speech/synthesize?stream=true` 或 `POST /api/settings/speech/{id}/preview?stream=true`，后端逐块转发上游 MP3，不拼接完整音频；首块到达前验证供应商错误，队列限制为 8 块。前端用 MediaSource 的 `audio/mpeg` SourceBuffer 边追加边播放，暂停与继续使用同一条音频流，取消会关闭 fetch、上游任务和播放器。目标 Windows Edge/WebView2 支持该播放格式，不支持 MediaSource 的浏览器才兼容回退到整段播放。无 `stream=true` 的原有二进制接口仍保留。

实时通话使用 `POST /api/capture/conversation?stream=true` 的 SSE 增量回复。问答和 OCR 使用供应商的真实流式生成，依次返回 `chunk`，最终返回 `result`；支持 OpenAI 兼容 SSE 和 Ollama NDJSON，并保留 token 计费、工具路由和会话运行规则。结构化工具结果完整验证后再应用截图，不向用户播报内部路由 JSON。精灵在句末或累积 80 字时分段合成并依次播放，后续文本继续生成；最终结果不重复朗读。打断会清空尚未播放的分句并取消模型、音频请求。流式读到断开的连接会明确报错，不把不完整结果当作完成。

## 存储与记忆 API

- `GET /api/storage`：运行目录与数据库位置。
- `GET /api/memories`：策略、任务状态、有效记忆数及待写事件数。
- `POST /api/memories/generate`，请求 `{}` 或 `{"sessionId":"..."}`：手动提取；跳过闲置限制，仍验证来源、消息轮数和运行状态。
- `GET /api/settings/preferences` / `PUT /api/settings/preferences`：本地界面设置，PUT 合并修改。
- 图片对话及工具接口新增可选 `sessionId`、`turnId`。新的 UI 自动传入；旧接口不传 ID 时保留原来的无状态行为。

## 迁移、备份与测试

首次正常启动自动备份 `backend/data/snapmind.sqlite3` 和 `backend/.snapmind`，检查数据库完整性、表分类以及目标冲突，再发布新路径。会话分离到状态库后逐条验证完整往返，业务用量保留。旧文件保留，后续不会继续写入；不要删除迁移清单后再次用旧文件覆盖新数据。

迁移备份和 `models.json` 可能包含模型凭证。本地 DPAPI 的数据库凭证仍沿用原有保护方式；JSON 模型配置仍是现有的可读配置格式。运行数据已加入忽略规则，只有本说明和策略示例适合随源码分享。SQLite 备份使用 SQLite backup API，不复制正在写入的单个数据库文件作为一致性备份。

`SNAPMIND_HOME` 可覆盖整个运行根目录。兼容已有 `SNAPMIND_DATA_DIR` 和 `SNAPMIND_CONFIG_FILE` 的开发测试覆盖；显式隔离环境不会扫描、导入真实旧数据。测试使用临时目录、合成图片和模拟模型，不调用真实 API。

验证命令：

```powershell
python -m pytest backend/tests -q
npm.cmd run typecheck
npm.cmd exec --workspace frontend -- vite build --configLoader runner
```

## AI 截图对话历史

应用不再自动生成示例会话、示例截图、预填公式/销售数据或固定演示回复。LLM 未配置时返回明确配置错误，不生成模拟答案；新会话图片、正文、公式和表格均为空。加载旧缓存时排除明确标记的演示消息，保留用户真实内容。测试脚本的合成素材和模拟服务仅用于独立验证，不在生产应用中导入。

ASR 使用 0.2 的云端 VAD 阈值，并检查真实上传 PCM：至少 120 ms 的有效音频信号（RMS ≥ 0.004）及对应 VAD 语句，才显示/提交文字。静音、低幅噪声和短促点击声不能仅凭云端生成文本触发对话。每轮完成清空本轮信号依据；开场介绍播放完再监听，避免将精灵自己的介绍作为用户输入。没有硬编码“嗯”等转写文本，也不按某个词强行过滤真实语音。用户指定的开场介绍保留。

- 项目根目录下的 `./.snapmind` 是存储根目录，与写作 `.snapmind/` 指向同一目录。
- 发送时保存原始提问，回复、失败或暂停时追加记录。图片保存为内容哈希文件，会话保留引用。
- 历史列表只查询标题、日期和置顶状态，打开会话时才读取消息和图片。
- 标题通过截图 OCR 内容总结，自动标题最多 18 字；无法识别时使用“截图对话”占位。手动重命名最多 40 字。
- 置顶和重命名更新会话元数据，不改变日期文件路径。删除会话需要确认，使用既有删除标记防止恢复时复活。
