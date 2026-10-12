// Real system shortcut; no saved screenshots, AI requests or session changes.
import assert from 'node:assert/strict'
import {execFileSync} from 'node:child_process'
import {mkdir,writeFile} from 'node:fs/promises'
import {connectNative,invoke,delay} from './native-cdp.mjs'
const output=process.argv[2]||'artifacts/capture-latency/results.json'
const main=await connectNative(),capture=await connectNative('capture'),timings=[]
let original,changed=false,started=false
try{
 assert.equal((await invoke(main,'native_status')).captureActive,false,'Finish the current capture before benchmarking')
 original=(await invoke(main,'get_desktop_state')).captureShortcut
 await invoke(main,'set_capture_shortcut',{shortcut:'Ctrl+Alt+Shift+K'});changed=true
 for(let i=0;i<5;i++){
  const windows=(await invoke(main,'native_status')).windows
  started=true
  const pressedAt=Number(execFileSync('python',['-c',"import ctypes,time; u=ctypes.windll.user32; mods=[0x11,0x12,0x10]; [u.keybd_event(k,0,0,0) for k in mods]; print(time.time()*1000,flush=True); u.keybd_event(0x4B,0,0,0); u.keybd_event(0x4B,0,2,0); [u.keybd_event(k,0,2,0) for k in reversed(mods)]"],{windowsHide:true,encoding:'utf8'}).trim())
  let sample
  for(let n=0;n<200;n++){
   sample=await capture.evaluate(()=>{const root=document.querySelector('.capture-overlay');if(root?.dataset.ready!=='true')return null;const mark=performance.getEntriesByName('snapmind-capture-ready').at(-1),c=document.querySelector('.capture-screen'),r=c.getBoundingClientRect();return {id:root.dataset.sourceId,pixelsAt:performance.timeOrigin+mark.startTime,width:c.width,height:c.height,aligned:Math.abs(r.x)<1&&Math.abs(r.y)<1&&Math.abs(r.width-innerWidth)<1&&Math.abs(r.height-innerHeight)<1,opaque:c.getContext('2d').getImageData(0,0,1,1).data[3]===255}})
   if(sample&&sample.pixelsAt>=pressedAt)break
   await delay(10)
  }
  assert.ok(sample?.pixelsAt>=pressedAt,'The system shortcut must produce a fresh frame')
  assert.equal(sample.aligned,true);assert.equal(sample.opaque,true)
  let status
  for(let n=0;n<100;n++){status=await invoke(main,'native_status');if(status.windows.capture.visible)break;await delay(10)}
  assert.equal(status.windows.capture.visible,true)
  for(const label of ['main','image','workspace'])assert.deepEqual(status.windows[label],windows[label])
  const exported=await capture.evaluate(async()=>{const c=document.createElement('canvas');c.width=120;c.height=80;c.getContext('2d').drawImage(document.querySelector('.capture-screen'),20,20,120,80,0,0,120,80);const img=new Image();img.src=c.toDataURL('image/png');await img.decode();return [img.width,img.height]})
  assert.deepEqual(exported,[120,80])
  timings.push({pixelsReadyMs:Math.round(sample.pixelsAt-pressedAt),width:sample.width,height:sample.height})
  await invoke(main,'cancel_capture');started=false;assert.equal((await invoke(main,'native_status')).captureActive,false)
  await delay(300)
 }
 const median=key=>[...timings.map(t=>t[key])].sort((a,b)=>a-b)[2]
 const result={timings,medianPixelsReadyMs:median('pixelsReadyMs'),shortcut:'PASS',pixelAlignment:'PASS',canvasExport:'PASS',originalWindowsUnchanged:'PASS',cancel:'PASS',savedImages:0}
 const {dirname}=await import('node:path');await mkdir(dirname(output),{recursive:true});await writeFile(output,JSON.stringify(result,null,2));console.log(JSON.stringify(result))
}finally{
 if(started)await invoke(main,'cancel_capture').catch(()=>{})
 if(changed)await invoke(main,'set_capture_shortcut',{shortcut:original}).catch(()=>{})
 main.close();capture.close()
}
