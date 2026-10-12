# SnapMind 界面风格

字体和配色参考 [person_dashboard 的 Workbench 样式](https://github.com/oyorf/person_dashboard/blob/main/Workbench/src/styles.css)。SnapMind 的 Logo、顶部卡片和截图界面布局独立设计。

- 正文：Noto Sans SC。
- 标题：Space Grotesk，中文使用 Noto Serif SC。
- 快捷键和数字标签：JetBrains Mono。
- 主色：`#7C3AED`；悬停主色：`#6D28D9`；背景：`#FAFAFA`。

字体及各自的 OFL 许可证保存在 `public/fonts/`，无需访问外部字体服务。字体按字符范围分片，界面仅加载实际显示文字需要的文件。刷新官方字体资源：

```shell
node scripts/sync-brand-fonts.mjs --refresh
```

上述命令从项目根目录运行。省略 `--refresh` 可续传中断的下载。

Logo 源文件是 `public/snapmind-logo.svg`：“S”字形与取景框组合。Windows 窗口和托盘共用 `src-tauri/icons/` 中由这个 SVG 生成的图标。

Windows EXE 图标使用 `icon.ico`，窗口和托盘使用同款 `icon.png`。`src-tauri/build.rs` 监听这两个文件，更新图标后桌面开发模式会重新编译资源，无需制作安装包。

主页图片支持网格和列表展示，选择保存在本地。缩略图保留原始比例，每张卡片显示编号、名称、尺寸和格式。Logo 仅作品牌展示；透明背景的齿轮设置按钮位于右上角最小化按钮左侧，设置与窗口按钮之间用竖线分隔，三个按钮无气泡提示。设置界面覆盖标题栏下方的整个内容区域，包含快捷键录制和常用操作，底部不显示收起窗口按钮；点击其他位置或切换应用保持设置页打开，通过页内关闭按钮、齿轮按钮或 Esc 返回主页。

主页为普通窗口，标题栏可拖动，切换应用后允许其他窗口覆盖。截图和贴图等独立窗口保留各自的窗口行为。底部固定快捷键提示和剪刀按钮已移除，开始截图使用顶部卡片。所有气泡使用浅紫色背景。

主页默认尺寸为 800 × 700，最小尺寸为 560 × 480，支持拖动四边和四角缩放。主页始终两列展示截图，缩略图随窗口宽度放大，图片保留完整比例；列表模式保持单列。设置页宽窗口按三列排列，窄窗口调整为两列，并在高度不足时滚动。快捷键为横向配置卡片，模型弹窗的类型与模型名称在宽窗口并排，窄窗口单列。

设置顶部导航分为通用、使用统计、模型配置、截图工具。通用页支持浅色、深色、跟随系统主题，以及简体中文、繁體中文和 English，选择立即生效并保存在本地，其他应用窗口同步偏好。Token 统计仅汇总本地 `model_usage` 中真实调用记录，显示输入、输出、总量、请求次数和各模型用量；演示模式无真实调用时显示零值和空状态。截图工具页保留导入、相册、历史和帮助入口。

快捷键可在设置中录制并保存：网页模式保存在本地缓存；桌面模式注册为系统快捷键，并保存到应用配置目录的 `preferences.json`。注册失败时保留原快捷键，录制期间暂停快捷键触发，避免误启动截图。

快捷键和截图设置通过弹窗配置。模型配置使用页内展开式列表：DeepSeek、Kimi、Qwen、豆包、GLM 和自定义接口可分别配置，也可添加多个自定义模型。Ollama 不再显示，历史配置保留在后端档案中。配置字段按地址、API Key、模型名称排列，不再显示接口类型选择。行末开关只有在配置已保存后可用，后端以单一 `activeId` 原子更新启用项。

SQLite 中的 Windows API Key 缓存使用 DPAPI 保护，常规模型列表接口仅返回是否已保存，留空保留原密钥，也可主动清除。修改已启用配置的地址、模型、密钥或图片权限后，保存会停用该配置，需要再次主动启用；只保存相同内容不影响启用状态。旧版单模型配置迁移为独立列表项，迁移不会自动启用。

模型配置现以项目 `backend/.snapmind` JSON 文件为准；SQLite 保留加密缓存，截图和 Token 历史仍保存在数据库。按用户要求，配置文件写入真实 API Key，并已加入 `.gitignore`。表单修改立即更新下方带行号、语法配色的 JSON 预览，并在短暂防抖后自动落盘；输入过程中不清空 API Key。配置未完成时也保存，但不允许启用。

文件结构使用 `schemaVersion`、`activeModelId` 和 `models`。每个模型包含 `id`、`name`、`provider`、`baseUrl`、`apiKey`、`model`、`enabled`、`vision`；每次启用都会只将一个模型的 `enabled` 设为 `true`。文件使用原子替换写入，失败时保留旧文件；手动编辑后，后台后续读取使用文件的新值。预览默认隐藏密钥，可切换显示、格式化及复制预览。

地址与 API Key 齐备后可点击“获取模型列表”，后端请求实际列表并处理分页，不截断为固定的 500 项。成功返回列表后，模型名称切换成下拉选择；未获取、返回空列表或接口不支持时保留手动输入。地址或 Key 改变后清除旧列表，防止选择上一服务的模型。测速单独测量真实请求耗时，以毫秒显示，测速不会切换输入框类型，也不会自动保存或启用。

API Key 输入框下方提供官方入口： [DeepSeek](https://platform.deepseek.com/api_keys)、[Kimi](https://platform.kimi.com/console/api-keys)、[阿里百炼](https://bailian.console.aliyun.com/cn-beijing/model/settings/api-key)、[火山方舟](https://console.volcengine.com/ark/region:ark+cn-beijing/apiKey)、[智谱](https://bigmodel.cn/usercenter/proj-mgmt/apikeys)。桌面模式点击后通过系统默认浏览器打开，后台只允许上述固定官方地址。

启用后，后续 AI 请求使用该模型；未启用时使用内置演示回复。图片处理要求勾选“支持图片输入，允许发送截图”，否则不发送图片。实际调用仅统计服务返回的 Token，未上报用量的请求单独提示；真实回复不标为示例，也不会编造表格或公式结果。

预设 API 地址参考 [DeepSeek](https://api-docs.deepseek.com/api/list-models/)、[Kimi](https://moonshotai.github.io/kimi-cli/zh/configuration/env-vars.html) 和 [Qwen](https://help.aliyun.com/en/model-studio/compatibility-of-openai-with-dashscope) 的官方文档。地址和模型 ID 均可修改，Qwen 支持替换为对应工作区和区域地址。

托盘左键恢复主界面，右键打开独立的快捷工具面板。面板与主页共用 `ToolMenu.vue`，点击外部或按 Esc 收起；首次打开时才创建窗口。

`src/theme.css` 管理公共字体、配色与气泡，`src/launcher.css` 管理主页，`TooltipLayer.vue` 为主页、截图工具栏和工作区统一提供悬停与键盘焦点提示。
