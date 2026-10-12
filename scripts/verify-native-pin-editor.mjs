// Synthetic native pin only; no gallery records or clipboard changes.
import {connectNative,invoke,delay} from './native-cdp.mjs'
import assert from 'node:assert/strict'
import {spawn} from 'node:child_process'
const main=await connectNative(),image=await connectNative('image'),capture=await connectNative('capture')
async function waitFor(page,fn){for(let i=0;i<100;i++){if(await page.evaluate(fn))return;await delay(100)}throw Error('Native UI did not reach expected state')}
const visible=page=>page.evaluate(async()=>{const {getCurrentWindow}=await import('/node_modules/.vite/deps/@tauri-apps_api_window.js');return getCurrentWindow().isVisible()})
async function clickClose(){const point=await capture.evaluate(()=>{const r=document.querySelector('.floating-editor-close').getBoundingClientRect();return {x:(r.x+r.width/2)*devicePixelRatio,y:(r.y+r.height/2)*devicePixelRatio}});await new Promise((resolve,reject)=>{const p=spawn('python',['scripts/native-editor-click.py'],{windowsHide:true,stdio:['pipe','pipe','pipe']});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);p.on('error',reject);p.on('exit',code=>{if(code)reject(Error(err));else{assert.equal(JSON.parse(out).captureVisible,false);resolve()}});p.stdin.end(JSON.stringify(point))})}
try{
 const asset=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=420;c.height=260;c.getContext('2d').fillRect(0,0,420,260);return {id:'synthetic-pin-editor',name:'Synthetic pin',scenario:'custom',width:420,height:260,data:c.toDataURL('image/png')}})
 // Saved images must also collapse to a pin when no pin existed before editing.
 await invoke(main,'begin_preview_capture',{asset,floatingPreview:true})
 await waitFor(capture,()=>document.querySelector('.floating-preview-editor')?.dataset.ready==='true')
 await delay(300);await clickClose()
 await waitFor(capture,()=>!document.querySelector('.capture-overlay'))
 assert.equal(await visible(image),true,'Closing a saved image editor must leave a pin')
 assert.equal((await invoke(main,'get_desktop_state')).asset.id,asset.id)
  assert.equal((await invoke(main,'get_desktop_state')).asset.data,asset.data)
 await invoke(main,'set_desktop_session',{sessionId:'synthetic-pin-editor',asset,action:null,notifyWorkspace:false})
 await waitFor(image,()=>!!document.querySelector('.native-image img'))
 await image.evaluate(async()=>{const {getCurrentWindow,LogicalSize}=await import('/node_modules/.vite/deps/@tauri-apps_api_window.js');await getCurrentWindow().setSize(new LogicalSize(420,260));await getCurrentWindow().show()})
 for(let cycle=0;cycle<2;cycle++){
  await image.evaluate(()=>document.querySelector('.native-image-window').dispatchEvent(new MouseEvent('contextmenu',{bubbles:true,cancelable:true,clientX:30,clientY:30})))
  await waitFor(capture,()=>document.querySelector('.floating-preview-editor')?.dataset.ready==='true')
  assert.equal(await image.evaluate(()=>document.querySelectorAll('.pin-context-menu').length),0)
  assert.equal(await visible(image),false)
  assert.equal(await capture.evaluate(()=>document.querySelectorAll('.capture-tools-scroll button').length),24)
  assert.equal(await capture.evaluate(()=>document.querySelectorAll('[data-capture-tool="cancel"]').length),0)
  assert.equal(await capture.evaluate(()=>document.querySelectorAll('.floating-editor-close').length),1)
  const before=await capture.evaluate(()=>{const r=document.querySelector('.capture-screen').getBoundingClientRect();return {x:r.x*devicePixelRatio,y:r.y*devicePixelRatio,width:Math.round(r.width*devicePixelRatio),height:Math.round(r.height*devicePixelRatio)}})
  await delay(300);await clickClose()
  await waitFor(capture,()=>!document.querySelector('.capture-overlay'))
  assert.equal(await visible(image),true)
  assert.equal((await invoke(main,'get_desktop_state')).asset.id,asset.id)
  assert.equal((await invoke(main,'get_desktop_state')).asset.data,asset.data)
  const after=await image.evaluate(async()=>{const {getCurrentWindow}=await import('/node_modules/.vite/deps/@tauri-apps_api_window.js');const win=getCurrentWindow();return {position:await win.innerPosition(),size:await win.innerSize()}})
  assert.equal(after.size.width,before.width);assert.equal(after.size.height,before.height)
  assert.ok(Math.abs(after.position.x-before.x)<=1);assert.ok(Math.abs(after.position.y-before.y)<=1)
 }
 console.log('PASS: Pin right-click repeatedly opens the complete editor, hides the old menu and pin, and the top-right close restores the unchanged original pin. Synthetic data only.')
}finally{
 await invoke(capture,'cancel_capture').catch(()=>{})
 await invoke(main,'set_desktop_session',{sessionId:'synthetic-pin-editor',asset:null,action:null,notifyWorkspace:false}).catch(()=>{})
 await invoke(main,'show_launcher').catch(()=>{})
 image.close();capture.close();main.close()
}
