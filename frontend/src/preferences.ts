import {ref,watch} from 'vue'
export type Theme='light'|'dark'|'system'
export type Language='zh-CN'|'zh-TW'|'en'
const themeKey='snapmind-theme',languageKey='snapmind-language'
export const theme=ref<Theme>(['light','dark','system'].includes(localStorage.getItem(themeKey)||'')?localStorage.getItem(themeKey) as Theme:'light')
export const language=ref<Language>(['zh-CN','zh-TW','en'].includes(localStorage.getItem(languageKey)||'')?localStorage.getItem(languageKey) as Language:'zh-CN')
export function tr(zh:string,tw:string,en:string){return language.value==='en'?en:language.value==='zh-TW'?tw:zh}
const words:Record<string,[string,string]>={
 '模型配置':['模型設定','Model configuration'],'设置接口地址与模型，配置保存在本机。':['設定介面位址與模型，設定儲存在本機。','Configure an endpoint and model. Settings stay on this device.'],'接口类型':['介面類型','Provider'],'OpenAI 兼容接口':['OpenAI 相容介面','OpenAI-compatible'],'Ollama 本地接口':['Ollama 本機介面','Local Ollama'],'接口地址':['介面位址','Endpoint URL'],'填写完整地址；本地服务也可使用 HTTP。':['填寫完整位址；本機服務也可使用 HTTP。','Enter the full URL. Local services may use HTTP.'],'模型名称':['模型名稱','Model name'],'填写服务提供的模型 ID':['填寫服務提供的模型 ID','Model ID from your provider'],'已保存':['已儲存','Saved'],'可选':['選填','Optional'],'留空保留已保存的密钥':['留空保留已儲存的金鑰','Leave blank to keep the saved key'],'输入 API Key，本地无鉴权服务可留空':['輸入 API Key，本機無驗證服務可留空','API key; optional for local services'],'清除已保存的 API Key':['清除已儲存的 API Key','Remove the saved API key'],'取消':['取消','Cancel'],'保存配置':['儲存設定','Save configuration'],'保存中…':['儲存中…','Saving…'],'正在加载配置…':['正在載入設定…','Loading configuration…'],'重新加载':['重新載入','Reload'],'当前 AI 处理仍为演示模式；此处先保存模型配置。':['目前 AI 處理仍為示範模式；此處先儲存模型設定。','AI processing is still in demo mode. This saves your configuration.'],
 '截图快捷键':['擷取快捷鍵','Capture shortcut'],'自定义':['自訂','Custom'],'保存中':['儲存中','Saving'],'点击下方，按下你习惯的组合键。':['點擊下方，按下你習慣的組合鍵。','Click below, then press your preferred shortcut.'],'按下组合键…':['按下組合鍵…','Press a shortcut…'],'保存':['儲存','Save'],'快捷键设置':['快捷鍵設定','Shortcut settings'],'设置你习惯的截图组合键。':['設定你習慣的擷取組合鍵。','Choose your preferred capture shortcut.'],'截图工具设置':['擷取工具設定','Capture settings'],
 '开始截图':['開始擷取','Start capture'],'我的图片':['我的圖片','My images'],'网格展示':['網格顯示','Grid view'],'列表展示':['清單顯示','List view'],'设置与工具':['設定與工具','Settings & tools'],'最小化工具':['最小化工具','Minimize'],'关闭工具窗口':['關閉工具視窗','Hide window'],'导入第一张图片':['匯入第一張圖片','Import your first image'],'先截一张，开启新思路':['先擷取一張，開啟新思路','Capture something. Start an idea.'],'每一次捕捉，都在这里好好收纳。':['每一次擷取，都在這裡妥善收納。','Keep every capture together, right here.'],'关闭弹窗':['關閉視窗','Close dialog'],'设置':['設定','Settings']}
export function tx(value:string){const pair=words[value];return pair?tr(value,pair[0],pair[1]):value}
const media=matchMedia('(prefers-color-scheme: dark)')
function apply(){document.documentElement.dataset.theme=theme.value==='system'?(media.matches?'dark':'light'):theme.value;document.documentElement.lang=language.value}
watch(theme,()=>{localStorage.setItem(themeKey,theme.value);apply()})
watch(language,()=>{localStorage.setItem(languageKey,language.value);apply()})
media.addEventListener('change',apply)
window.addEventListener('storage',event=>{if(event.key===themeKey&&['light','dark','system'].includes(event.newValue||''))theme.value=event.newValue as Theme;if(event.key===languageKey&&['zh-CN','zh-TW','en'].includes(event.newValue||''))language.value=event.newValue as Language})
apply()
