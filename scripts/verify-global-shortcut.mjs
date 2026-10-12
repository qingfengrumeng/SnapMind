// Native shortcut integration test. Restores the user's shortcut and cancels capture.
import {chromium} from 'playwright'
import {execFileSync} from 'node:child_process'
import assert from 'node:assert/strict'
import {resolve} from 'node:path'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const main=browser.contexts()[0].pages().find(p=>p.url().includes('5174')&&!p.url().includes('desktop='))
const invoke=(command,args)=>main.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})
const original=(await invoke('get_desktop_state')).captureShortcut
function keys(){execFileSync('python',['-c',"import ctypes,time; u=ctypes.windll.user32; keys=[0x11,0x12,0x10,0x4B]; [(u.keybd_event(k,0,0,0),time.sleep(0.05)) for k in keys]; time.sleep(0.1); [u.keybd_event(k,0,2,0) for k in reversed(keys)]"],{windowsHide:true})}
try{
 await invoke('set_capture_shortcut',{shortcut:'Ctrl+Alt+Shift+K'})
 await invoke('set_shortcut_recording',{recording:true})
 keys();await new Promise(r=>setTimeout(r,500))
 assert.equal((await invoke('get_desktop_state')).captureActive,false,'Recording must suppress capture')
 await invoke('set_shortcut_recording',{recording:false})
 const windowModule='/@fs/'+resolve('node_modules/@tauri-apps/api/window.js').replaceAll('\\','/')
 await main.evaluate(async path=>{const {getCurrentWindow}=await import(path);await getCurrentWindow().hide()},windowModule)
 keys()
 let state
 for(let n=0;n<60;n++){state=await invoke('native_status');if(state.captureActive&&state.windows.capture.visible)break;await new Promise(r=>setTimeout(r,100))}
 assert.equal(state.captureActive,true);assert.equal(state.windows.capture.visible,true)
 assert.equal(state.windows.main.visible,false)
 console.log('PASS: custom system shortcut captures while main window is hidden; shortcut recording suppresses capture.')
}finally{
 await invoke('cancel_capture').catch(()=>{})
 await invoke('set_shortcut_recording',{recording:false}).catch(()=>{})
 await invoke('set_capture_shortcut',{shortcut:original}).catch(()=>{})
 await invoke('show_launcher').catch(()=>{})
 await browser.close()
}
