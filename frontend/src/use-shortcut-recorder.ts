import {onBeforeUnmount,onMounted,ref} from 'vue'
import {desktop,native} from './desktop'
import {captureShortcutErrorMessage} from './shortcut'

let activeRecorder:(()=>void)|undefined
let nativeUpdates=Promise.resolve<void>(undefined)
function suspendCapture(recording:boolean){
 const update=nativeUpdates.catch(()=>{}).then(async()=>{if(native)await desktop.shortcutRecording(recording)})
 nativeUpdates=update
 return update
}
export function useShortcutRecorder(options:{parse:(event:KeyboardEvent)=>string;save:(value:string)=>void|Promise<void>;invalidMessage:string;allowEscape?:boolean;errorMessage?:(error:unknown)=>string}){
 const recording=ref(false),starting=ref(false),saving=ref(false),error=ref(''),saved=ref(false),preview=ref('')
 let generation=0,disposed=false
 function stop(){
  generation++;recording.value=false;starting.value=false;preview.value=''
  if(activeRecorder===stop){activeRecorder=undefined;void suspendCapture(false).catch(()=>{})}
 }
 async function start(){
  if(saving.value||starting.value)return
  if(recording.value){stop();return}
  activeRecorder?.();activeRecorder=stop
  error.value='';saved.value=false;starting.value=true
  const version=++generation
  try{await suspendCapture(true);if(!disposed&&generation===version)recording.value=true}
  catch(e){if(!disposed&&generation===version){error.value=captureShortcutErrorMessage(e,'无法开始录制快捷键，请重试。');stop()}}
  finally{if(generation===version)starting.value=false}
 }
 async function save(value:string){
  if(saving.value)return
  saving.value=true;error.value='';saved.value=false
  try{await options.save(value);if(!disposed){saved.value=true;stop()}}
  catch(e){if(!disposed){error.value=options.errorMessage?.(e)||captureShortcutErrorMessage(e);preview.value=''}}
  finally{saving.value=false}
 }
 function modifiers(e:KeyboardEvent){return [e.ctrlKey?'Ctrl':'',e.altKey?'Alt':'',e.shiftKey?'Shift':'',e.metaKey?'Win':''].filter(Boolean).join(' + ')}
 function record(e:KeyboardEvent){
  if(!recording.value&&!starting.value&&!saving.value)return
  e.stopPropagation()
  if(e.key==='Tab'){stop();return}
  e.preventDefault()
  if(e.isComposing||e.keyCode===229||e.repeat||starting.value||saving.value)return
  if(e.key==='Escape'&&!options.allowEscape){stop();return}
  if(['Control','Alt','Shift','Meta'].includes(e.key)){preview.value=modifiers(e);return}
  const value=options.parse(e)
  if(value){preview.value=value;void save(value)}else error.value=options.invalidMessage
 }
 function release(e:KeyboardEvent){if(recording.value&&!saving.value)preview.value=modifiers(e)}
 onMounted(()=>window.addEventListener('blur',stop))
 onBeforeUnmount(()=>{disposed=true;stop();window.removeEventListener('blur',stop)})
 return {recording,starting,saving,error,saved,preview,start,stop,save,record,release}
}
