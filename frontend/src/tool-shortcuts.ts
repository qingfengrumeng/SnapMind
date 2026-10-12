import {ref} from 'vue'
import {captureShortcut} from './shortcut'

export const toolShortcutCatalog=[
 {id:'objects',label:'移动标注',key:'V',group:'绘图与编辑'},
 {id:'rect',label:'矩形',key:'R',group:'绘图与编辑'},
 {id:'ellipse',label:'圆形',key:'O',group:'绘图与编辑'},
 {id:'arrow',label:'箭头',key:'A',group:'绘图与编辑'},
 {id:'pen',label:'画笔',key:'P',group:'绘图与编辑'},
 {id:'mosaic',label:'马赛克',key:'M',group:'绘图与编辑'},
 {id:'text',label:'文字',key:'T',group:'绘图与编辑'},
 {id:'blur',label:'模糊遮罩',key:'B',group:'绘图与编辑'},
 {id:'number',label:'序号',key:'N',group:'绘图与编辑'},
 {id:'eyedropper',label:'取色',key:'I',group:'绘图与编辑'},
 {id:'highlight',label:'荧光笔',key:'H',group:'绘图与编辑'},
 {id:'eraser',label:'橡皮擦',key:'E',group:'绘图与编辑'},
 {id:'heal',label:'涂抹消除',key:'W',group:'绘图与编辑'},
 {id:'lift',label:'无痕提取',key:'U',group:'绘图与编辑'},
 {id:'ocr',label:'提取文字',key:'L',group:'识别与截图'},
 {id:'translate',label:'翻译',key:'F',group:'识别与截图'},
 {id:'scroll',label:'滚动截图',key:'G',group:'识别与截图'},
 {id:'pin',label:'贴图',key:'D',group:'识别与截图'},
 {id:'chat',label:'AI对话',key:'C',group:'AI 交互'},
 {id:'voiceCall',label:'语音通话',key:'X',group:'AI 交互'},
 {id:'undo',label:'撤销',key:'Ctrl+Z',group:'操作'},
 {id:'redo',label:'重做',key:'Ctrl+Y',group:'操作'},
 {id:'clear',label:'清空标注',key:'Ctrl+Backspace',group:'操作'},
 {id:'save',label:'保存',key:'S',group:'操作'},
 {id:'cancel',label:'取消截图',key:'Escape',group:'操作'},
 {id:'copy',label:'完成并复制',key:'Enter',group:'操作'},
 {id:'longEdit',label:'编辑长截图',key:'J',group:'翻译与长截图'},
 {id:'copyTranslation',label:'复制全部译文',key:'Ctrl+Shift+C',group:'翻译与长截图'},
 {id:'toggleOriginal',label:'切换原文／译文',key:'K',group:'翻译与长截图'},
 {id:'retryTranslation',label:'重新翻译',key:'Ctrl+Alt+R',group:'翻译与长截图'},
] as const
export type CaptureToolId=typeof toolShortcutCatalog[number]['id']
export const toolShortcutStorageKey='snapmind.capture.shortcuts'
export function normalizeToolShortcut(value:string){
 const parts=value.split('+').map(p=>p.trim()).filter(Boolean),raw=parts.pop()||''
 const aliases:Record<string,string>={esc:'Escape',escape:'Escape',enter:'Enter',backspace:'Backspace'}
 const key=aliases[raw.toLowerCase()]||(/^[a-z0-9]$/i.test(raw)||/^F(?:[1-9]|1\d|2[0-4])$/i.test(raw)?raw.toUpperCase():'')
 if(!key||parts.some(p=>!['Ctrl','Alt','Shift','Meta'].includes(p)))return ''
 return [...['Ctrl','Alt','Shift','Meta'].filter(p=>parts.includes(p)),key].join('+')
}
export function toolShortcutFromEvent(e:KeyboardEvent){
 if(e.isComposing||e.keyCode===229)return ''
 const key=e.code.startsWith('Key')?e.code.slice(3):e.code.startsWith('Digit')?e.code.slice(5):e.key
 return normalizeToolShortcut([e.ctrlKey?'Ctrl':'',e.altKey?'Alt':'',e.shiftKey?'Shift':'',e.metaKey?'Meta':'',key].filter(Boolean).join('+'))
}
export function toolShortcutProblem(id:CaptureToolId,value:string){
 if(!value)return ''
 const normalized=normalizeToolShortcut(value)
 if(!normalized)return '请使用字母、数字或功能键，可搭配 Ctrl、Alt、Shift 或 Win。'
 if(['Backspace','Q','Ctrl+C','Ctrl+V','Ctrl+A','Ctrl+X'].includes(normalized))return '这个按键用于删除标注、取色复制或文本编辑，请换一个。'
 if(normalized==='Escape'&&id!=='cancel'||normalized==='Enter'&&id!=='copy')return 'Esc 和 Enter 分别用于取消、完成，请换一个。'
 if(normalized===normalizeToolShortcut(captureShortcut.value.replace('Super','Meta')))return '这个组合键已用于开始截图，请换一个。'
 if(normalized.endsWith('Backspace')&&normalized!=='Ctrl+Backspace')return 'Backspace 保留用于删除所选标注。'
 return ''
}
function decode(raw:string|null):Record<CaptureToolId,string>{
 let saved:Record<string,unknown>={};try{const value=JSON.parse(raw||'{}');if(value&&typeof value==='object'&&!Array.isArray(value))saved=value}catch{}
 const result={} as Record<CaptureToolId,string>,used=new Set<string>()
 // Preserve legacy choices first; disable conflicting defaults instead of assigning a key twice.
 for(const item of toolShortcutCatalog)if(Object.hasOwn(saved,item.id)){
  const value=typeof saved[item.id]==='string'?normalizeToolShortcut(saved[item.id] as string):''
  result[item.id]=!toolShortcutProblem(item.id,value)&&!used.has(value)?value:'';if(result[item.id])used.add(result[item.id])
 }
 for(const item of toolShortcutCatalog)if(!Object.hasOwn(result,item.id)){
  result[item.id]=used.has(item.key)||toolShortcutProblem(item.id,item.key)?'':item.key;if(result[item.id])used.add(result[item.id])
 }
 return result
}
export const toolShortcuts=ref(decode(localStorage.getItem(toolShortcutStorageKey)))
export function setToolShortcut(id:CaptureToolId,value:string){
 const problem=toolShortcutProblem(id,value);if(problem)throw Error(problem)
 const normalized=normalizeToolShortcut(value),owner=toolShortcutCatalog.find(t=>t.id!==id&&normalized&&toolShortcuts.value[t.id]===normalized)
 if(owner)throw Error(`${normalized} 已用于“${owner.label}”，请先修改该功能的快捷键。`)
 const next={...toolShortcuts.value,[id]:normalized};localStorage.setItem(toolShortcutStorageKey,JSON.stringify(next));toolShortcuts.value=next
}
export function resetToolShortcuts(){const next=decode(null);localStorage.setItem(toolShortcutStorageKey,JSON.stringify(next));toolShortcuts.value=next}
export function shortcutTool(e:KeyboardEvent){const key=toolShortcutFromEvent(e);return key?toolShortcutCatalog.find(t=>toolShortcuts.value[t.id]===key)?.id:undefined}
export interface LiveScrollKey{keyCode:number;ctrl:boolean;alt:boolean;shift:boolean;meta:boolean;action:number}
export function liveScrollKeys():LiveScrollKey[]{
 return (['longEdit','save','cancel','copy'] as const).flatMap((id,action)=>{
  const value=toolShortcuts.value[id];if(!value)return []
  const parts=value.split('+'),key=parts.pop()!,special:Record<string,number>={Backspace:8,Enter:13,Escape:27}
  const keyCode=special[key]||(/^F\d+$/.test(key)?111+Number(key.slice(1)):key.charCodeAt(0))
  return [{keyCode,ctrl:parts.includes('Ctrl'),alt:parts.includes('Alt'),shift:parts.includes('Shift'),meta:parts.includes('Meta'),action}]
 })
}
window.addEventListener('storage',e=>{if(e.key===toolShortcutStorageKey||e.key===null)toolShortcuts.value=decode(e.newValue)})
