import {ref} from 'vue'
import {desktop,native} from './desktop'
const storageKey='snapmind-capture-shortcut'
export const captureShortcut=ref(localStorage.getItem(storageKey)||'Alt+Z')
function receive(value:string){if(value){captureShortcut.value=value;localStorage.setItem(storageKey,value)}}
if(native){desktop.state().then(state=>receive(state.captureShortcut)).catch(()=>{});desktop.listen<string>('desktop:shortcut-changed',receive).catch(()=>{})}
else window.addEventListener('storage',event=>{if(event.key===storageKey&&event.newValue)receive(event.newValue)})
export async function saveCaptureShortcut(value:string){if(native)await desktop.setShortcut(value);receive(value)}
export function captureShortcutErrorMessage(error:unknown,fallback='快捷键设置失败，请重试。'){
 const message=(error instanceof Error?error.message:String(error)).replace(/^Error:\s*/,'').trim()
 if(message.startsWith('无法注册该快捷键')||/hotkey already registered/i.test(message))return '无法注册该快捷键，可能已被其他软件占用。'
 if(message.startsWith('保存快捷键失败'))return '保存快捷键失败，请检查设置目录是否可写。'
 if(['快捷键格式不正确','请使用 Ctrl、Alt 或 Win 搭配字母、数字或功能键','快捷键需要包含 Ctrl、Alt 或 Win','设置目录不存在'].includes(message))return message
 if(/^这个组合键已用于“[^”]+”，请先修改该功能的快捷键。$/.test(message))return message
 return fallback
}
export function shortcutFromEvent(event:KeyboardEvent){
 const key=event.code.startsWith('Key')?event.code.slice(3):event.code.startsWith('Digit')?event.code.slice(5):/^F\d{1,2}$/.test(event.code)?event.code:''
 if(!key||!(event.ctrlKey||event.altKey||event.metaKey))return ''
 return [event.ctrlKey?'Ctrl':'',event.altKey?'Alt':'',event.shiftKey?'Shift':'',event.metaKey?'Super':'',key].filter(Boolean).join('+')
}
