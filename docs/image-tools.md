# 图片工具接口

应用快照已删除。增加截图区域、图片笔记、检查作答、论文注释、理解代码、二维码／条码、邮箱链接、公式与表格提取、解释、AI 标注、物体识别保留为工具，截图工具栏和对话快捷操作中不再提供这些功能的独立按钮。文字提取、原位翻译、AI对话和手工绘图编辑仍保留按钮。

主页及托盘不提供对话入口或独立对话窗口。截图工具栏不提供三个点菜单；第二组依次提供文字提取、原位翻译、滚动截图、贴图、AI对话，再与撤销等编辑操作分隔。“AI对话”采用与其他工具一致的浅色样式，使用圆润的气泡轮廓和柔和尾角，内部三条圆头文本横线由长到短、等距排列，从当前截图进入对话。对话中的 `/` 工具列表仍包含全部保留功能。

## 工具快捷键

悬停或聚焦截图工具按钮，会显示“功能名称、键盘图标、快捷键”配置面板。点击快捷键框，直接按下字母、数字、功能键或组合键即可自动保存；录制时显示已按下的修饰键。Esc、再次点击快捷键框或点击其他位置取消录制（“取消截图”功能可直接录制 Esc）。在设置的“通用”页“快捷键”区域也可以统一录制或恢复默认值，开始截图的组合键同样按下后自动保存。配置自动保存到 `snapmind.capture.shortcuts`，并在设置和截图窗口之间同步；已有文字提取、翻译、保存配置会保留。重复按键及与开始截图快捷键的冲突会被拒绝，保留旧值并允许重新按键。

默认绘图键为移动标注 V、矩形 R、圆形 O、箭头 A、画笔 P、马赛克 M、文字 T、模糊遮罩 B、序号 N、取色 I、荧光笔 H、橡皮擦 E、涂抹消除 W、无痕提取 U；文字提取 L、翻译 F、滚动截图 G、贴图 D、AI对话 C。操作键为撤销 Ctrl+Z、重做 Ctrl+Y、清空标注 Ctrl+Backspace、保存 S、取消 Esc、完成并复制 Enter。长截图编辑 J；译文复制 Ctrl+Shift+C、原文切换 K、重新翻译 Ctrl+Alt+R。

工具快捷键执行与点击按钮相同的操作，再次按下绘图工具键会退出该工具。输入文字、输入法组合输入、对话输入和快捷键配置时不会触发截图工具。Backspace 仍用于删除所选标注，取色工具的 Q 仍用于复制颜色。滚动截图原生控制也使用相同的配置。

## 发现和调用

本地服务默认地址 `http://127.0.0.1:8776`。

- `GET /api/tools`：返回函数名称、说明及 JSON Schema，可直接作为后续 agent 的函数工具定义。
- `POST /api/tools/call`：明确调用指定工具，不经过意图分类；返回 `{action, assetId, answer, payload}`。
- `POST /api/capture/conversation`：保留自然语言意图路由，使用同一组工具实现；支持连续提问。

```json
{
  "name": "region",
  "arguments": {"imageId": "image-1", "bbox": [20, 40, 320, 180]},
  "context": {
    "assets": [{"id": "image-1", "name": "截图", "data": "data:image/png;base64,...", "width": 800, "height": 600, "scenario": "custom"}],
    "selectedId": "image-1",
    "history": [],
    "existing": [],
    "controls": []
  }
}
```

`arguments.imageId` 省略时使用 `context.selectedId`。`prompt` 可指定本轮要求；`history` 是此前 user／assistant 文字对话，`existing` 是可编辑标注，`controls` 是桌面客户端验证后的 Windows UI Automation 控件边界。上传图片不提供 UIA 边界。调用方应保存工具返回的结果，再把必要的历史和已有标注传给下一次调用；工具 API 不自行创建会话。

## 工具及结果

| 名称 | 能力 | 主要 payload |
| --- | --- | --- |
| `region` | 增加截图区域 | 新区域 PNG、width、height；不替换原图 |
| `note` | 图片笔记 | markdown 与 attachments（文件名、PNG data、assetId） |
| `code` | 理解代码 | answer、关联代码行的 notes |
| `paper` | 论文注释／多页比较 | answer、按 pageId 关联的 notes |
| `exam` | 检查作答 | answer、题目定位和说明 notes |
| `qr` | 二维码／条码 | codes，含文字及像素位置 |
| `entities` | 邮箱、链接、电话 | entities，含文字、链接及位置 |
| `formula` | 公式提取 | text，包含 LaTeX |
| `table` | 表格提取 | tables（title、rows），客户端可复制到 Excel |
| `explain` | 内容解释 | text，解释用途与作用，不要求按原文排版 |
| `annotate` | AI 标注及连续修改 | annotations，含 add／update／remove 和位置来源 |
| `detect` | 物体识别 | objects、coordinateSpace、approximate |
| `ocr`／`offline` | 多模态／本地文字识别 | text／regions |
| `translate` | 原位翻译 | lines、原文 bbox、译文；language 可设 zh-CN／zh-TW／en |
| `crop` | 裁剪当前图片 | PNG、width、height |
| `highlight`／`mosaic` | 指定原文高亮／遮盖 | OCR 唯一匹配的 bbox |
| `heal`／`lift` | 内容消除／透明图层提取 | 修补 PNG；lift 还返回透明 layer |
| `chat` | 连续图片问答 | text |

`region`、`crop` 必须传 `bbox: [左,上,右,下]`，坐标相对于引用图片的真实像素，越界或缺失返回错误，禁止模型猜测位置。`highlight`、`mosaic`、`heal`、`lift` 必须传 `targetText`，通过 OCR 唯一匹配。文字目标仍使用 OCR 行框，部分桌面控件使用 UIA；物体定位可能有误差，保留 approximate 标志。

图片对话中可以输入“增加截图区域 [20,40,320,180]”，新区域会成为额外引用图片；输入“整理图片笔记”，会得到可复制文本及笔记保存操作。笔记保存为包含图片的单文件 HTML。API 的 note 工具返回可移植 Markdown 与图片附件，不自动写文件。

前端集成：`api.imageTools()` 获取目录，`api.callImageTool(call, context, signal)` 调用 API。`ImageConversation` 暴露 `callTool({name, arguments})`，自动使用当前图片、历史及已有标注，将结果应用到图片对话并保存；失败会抛出错误。未来 agent 可用此桥接显示工具结果。

图片对话输入框支持 `/` 功能选择，也可点击输入框下方的“/ 功能”。列表实时读取 `/api/tools`，包含所有保留工具，按识别与提取、理解与标注、图片编辑、对话与整理分组；可按名称、英文工具名或说明搜索。用 ↑／↓ 选择，Enter 或 Tab 确认，Esc 仅收起列表。选中后可以补充要求，发送时直接调用工具，不经过意图分类；需要原文或区域坐标时显示对应输入项。执行成功后清除功能标签，继续普通对话；失败保留选择以便重试。空输入时 Backspace 可取消功能。

所有调用沿用现有模型配置和用量统计。工具校验未知名称、多余参数、图片总量、历史长度和图片尺寸。二维码、区域裁剪、笔记生成无需 LLM；其他工具所需的 LLM／OCR 未配置或不可用时返回实际错误，不返回伪造结果。
