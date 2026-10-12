// Native WebView2 integration check. Start desktop dev with a local CDP port first.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
import {randomUUID} from 'node:crypto'
import {resolve} from 'node:path'
const windowModule='/@fs/'+resolve('node_modules/@tauri-apps/api/window.js').replaceAll('\\','/')
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const context=browser.contexts()[0]
const pages=()=>context.pages()
const role=p=>{const url=new URL(p.url());return url.searchParams.get('desktop')||'main'}
async function find(wanted){for(let i=0;i<60;i++){const p=pages().find(p=>{try{return role(p)===wanted}catch{return false}});if(p){p.setDefaultTimeout(30000);return p}await new Promise(r=>setTimeout(r,500))}throw Error('Missing native window: '+wanted)}
async function invoke(page,command,args){return page.evaluate(async({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})}
const main=await find('main'),capture=await find('capture'),image=await find('image'),work=await find('workspace')
await mkdir('artifacts',{recursive:true})
const errors=[];for(const p of [main,capture,image,work])p.on('pageerror',e=>errors.push(role(p)+': '+e.message))
const initial=await(await context.request.get('http://127.0.0.1:5174/api/sessions')).json()
const baseline=new Set(initial.map(s=>s.id)),created=new Set()
const fixtureId=randomUUID(),template=initial[0]
const fixture={...template,id:fixtureId,title:'Native UI · isolated test',scenario:'custom',assets:[],messages:[],pinned:false}
created.add(fixtureId)
assert.equal((await context.request.put('http://127.0.0.1:5174/api/sessions/'+fixtureId,{data:fixture})).ok(),true)
await invoke(main,'set_desktop_session',{sessionId:fixtureId,asset:null,action:null,notifyWorkspace:false})
try {
 await main.locator('.screenshot-window').waitFor()
 assert.equal(await main.evaluate(()=>!!window.__TAURI_INTERNALS__),true)
 const before=await invoke(main,'native_status')
 for(const label of ['main','capture','image','workspace'])assert.ok(before.windows[label])
 // Actual monitor capture, without touching the system clipboard or saving the screen.
 await invoke(main,'begin_capture')
 await capture.locator('.capture-overlay').waitFor()
 const state=await invoke(main,'get_desktop_state')
 assert.ok(state.frame.asset.width>=640&&state.frame.asset.height>=480)
 assert.equal((await invoke(main,'native_status')).windows.main.visible,false)
 await invoke(main,'cancel_capture')
 assert.equal((await invoke(main,'native_status')).windows.main.visible,before.windows.main.visible)
 // Generated test pixels for window, storage and clipboard validation.
 const generated=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=1600;c.height=1000;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,1600,1000);return {id:crypto.randomUUID(),name:'Generated test image',data:c.toDataURL(),width:1600,height:1000,scenario:'custom'}})
 await invoke(main,'begin_preview_capture',{asset:generated,floatingPreview:false})
 let sampleFrame;for(let i=0;i<60;i++){const runtime=await invoke(main,'get_desktop_state');if(runtime.frame?.asset.width===1600){sampleFrame=runtime.frame;break}await new Promise(r=>setTimeout(r,100))}
 assert.ok(sampleFrame,'Sample frame should be delivered')
 await capture.waitForFunction(id=>document.querySelector('.capture-overlay')?.getAttribute('data-source-id')===id,sampleFrame.asset.id)
 await capture.waitForFunction(()=>document.querySelector('canvas')?.width===1600)
 await capture.waitForTimeout(500)
 const box=await capture.locator('.capture-screen').boundingBox()
 const x1=box.x+box.width*.2,y1=box.y+box.height*.4,x2=box.x+box.width*.76,y2=box.y+box.height*.73
 await capture.mouse.move(x1,y1);await capture.mouse.down();await capture.mouse.move(x2,y2,{steps:8});await capture.mouse.up()
 const selected=(await capture.locator('.capture-size').innerText()).split(' × ').map(Number)
 assert.ok(Math.abs(selected[0]-Math.round(1600*.56))<=1)
 assert.ok(Math.abs(selected[1]-Math.round(1000*.33))<=1)
 const previousAsset=(await invoke(main,'get_desktop_state')).asset?.id
 await capture.getByRole('button',{name:'完成并复制截图'}).click()
 await image.locator('.native-image img').waitFor()
 await work.locator('.floating-workspace').waitFor()
 let status;for(let i=0;i<60;i++){status=await invoke(main,'native_status');const state=await invoke(main,'get_desktop_state');if(status.windows.image.visible&&status.windows.workspace.visible&&status.sessionId&&state.asset?.id!==previousAsset&&state.asset?.width===selected[0])break;await new Promise(r=>setTimeout(r,100))}
 assert.equal(status.windows.capture.visible,false)
 assert.equal(status.windows.image.visible,true);assert.equal(status.windows.workspace.visible,true)
 assert.ok(status.windows.workspace.position.x>status.windows.image.position.x)
 if(!baseline.has(status.sessionId))created.add(status.sessionId)
 const current=await invoke(main,'get_desktop_state')
 assert.ok(Math.abs(current.asset.width-Math.round(1600*.56))<=1)
 assert.ok(Math.abs(current.asset.height-Math.round(1000*.33))<=1)
 await image.screenshot({path:'artifacts/native-floating-image.png'})
 await work.screenshot({path:'artifacts/native-content-workspace.png'})
 // Separate HWNDs: moving the image window does not move the content window.
 const oldPosition=status.windows.image.position,oldWork=status.windows.workspace.position
 await image.evaluate(async modulePath=>{const {getCurrentWindow,PhysicalPosition}=await import(modulePath);const w=getCurrentWindow();const p=await w.outerPosition();await w.setPosition(new PhysicalPosition(p.x+25,p.y+20))},windowModule)
 status=await invoke(main,'native_status');assert.equal(status.windows.image.position.x,oldPosition.x+25);assert.equal(status.windows.workspace.position.x,oldWork.x)
 await work.getByRole('button',{name:'收起内容工作区'}).click()
 status=await invoke(main,'native_status');assert.equal(status.windows.workspace.visible,false);assert.equal(status.windows.image.visible,true)
 await image.getByRole('button',{name:'内容工作区',exact:true}).click()
 assert.equal((await invoke(main,'native_status')).windows.workspace.visible,true)
 await invoke(main,'desktop_copy')
 await work.getByRole('textbox',{name:'对话消息'}).fill('解释这张截图')
 await work.getByRole('button',{name:'发送消息',exact:true}).click()
 await work.locator('.message.assistant .message-text').filter({hasText:'尚未接入多模态模型'}).last().waitFor()
 await work.locator('.generating').waitFor({state:'detached'})
 assert.deepEqual(errors,[])
 console.log(JSON.stringify({result:'PASS',nativeWindows:Object.keys(status.windows),screen:{width:state.frame.asset.width,height:state.frame.asset.height},clipboard:'native command succeeded',shortcutRegistered:status.shortcutAvailable,checks:'real screen capture + restore, crop dimensions, independent native windows, auto right workspace, hide/reopen, backend conversation'},null,2))
}finally{
 const restoreSession=initial.find(s=>s.scenario==='table'&&s.assets.length)||initial.find(s=>s.id==='snapmind-floating-preview'&&s.assets.length)||initial.find(s=>s.assets.length)
 if(restoreSession){await invoke(main,'set_desktop_session',{sessionId:restoreSession.id,asset:restoreSession.assets[0],action:null,notifyWorkspace:true});await work.waitForTimeout(800)}
 for(const id of created)await context.request.delete('http://127.0.0.1:5174/api/sessions/'+id)
 await invoke(main,'show_launcher');await image.evaluate(()=>window.__TAURI_INTERNALS__.invoke('cancel_capture')).catch(()=>{})
 await browser.close()
}
