// Native completion regression: session requests stay in memory, automatic clipboard copy, no AI calls.
import { chromium } from 'playwright'
import assert from 'node:assert/strict'
import { resolve } from 'node:path'
import {execFileSync,spawn} from 'node:child_process'
const browser = await chromium.connectOverCDP('http://127.0.0.1:9223')
const context = browser.contexts()[0], pages = context.pages()
const main = pages.find(p => p.url().includes('5174') && !p.url().includes('desktop='))
const capture = pages.find(p => p.url().includes('desktop=capture'))
const image = pages.find(p => p.url().includes('desktop=image'))
const workspace = pages.find(p => p.url().includes('desktop=workspace'))
const invoke = (command, args) => main.evaluate(({command,args}) => window.__TAURI_INTERNALS__.invoke(command,args), {command,args})
const original = await invoke('get_desktop_state')
assert.equal(original.captureActive, false, 'Finish the current user capture before running this test')
const windows = (await invoke('native_status')).windows
const storage = await Promise.all(pages.map(p => p.evaluate(() => ({...localStorage}))))
let sessions = await (await context.request.get('http://127.0.0.1:8776/api/sessions')).json()
const errors = []; for (const p of [main,capture,image]) p.on('pageerror', e => errors.push(e.message))
const routePattern = '**/api/sessions**'
await context.route(routePattern, async route => {
  const request = route.request()
  // Force an observable gap to catch revealing the desktop before content is ready.
  await new Promise(r => setTimeout(r, 220))
  if (request.method() === 'PUT') {
    const s = request.postDataJSON(); sessions = [...sessions.filter(x => x.id !== s.id), s]
    await route.fulfill({json:s})
  } else await route.fulfill({json:sessions})
})
try {
  const data = await main.evaluate(() => {const c=document.createElement('canvas');c.width=120;c.height=80;const g=c.getContext('2d');g.fillStyle='#7538ee';g.fillRect(0,0,120,80);return c.toDataURL('image/png')})
  await invoke('begin_capture')
  const copyId=(await invoke('get_desktop_state')).frame.asset.id
  await capture.waitForFunction(id=>{const e=document.querySelector('.capture-overlay');return e?.dataset.sourceId===id&&e.dataset.ready==='true'},copyId)
  const box=await capture.locator('.capture-screen').boundingBox()
  await capture.mouse.move(box.x+100,box.y+100);await capture.mouse.down();await capture.mouse.move(box.x+Math.min(box.width-100,600),box.y+Math.min(box.height-100,400),{steps:5});await capture.mouse.up()
  if(!process.env.SNAPMIND_SCREEN_TRACE){
    const lock=spawn('python',['-u','-c',"import ctypes,sys; u=ctypes.windll.user32; assert u.OpenClipboard(None); print('locked',flush=True); sys.stdin.readline(); u.CloseClipboard()"],{windowsHide:true,stdio:['pipe','pipe','pipe']})
    try{
      await new Promise((resolve,reject)=>{lock.stdout.once('data',resolve);lock.once('error',reject);lock.once('exit',code=>reject(new Error('Clipboard lock exited '+code)))})
      await capture.locator('.capture-done').click()
      await capture.locator('.native-toast').waitFor()
      assert.equal((await invoke('native_status')).captureActive,true,'Clipboard failure must keep the screenshot open')
      assert.ok((await capture.locator('.native-toast').innerText()).includes('复制截图失败'))
    }finally{
      const exited=new Promise(resolve=>lock.once('exit',resolve));lock.stdin.end('\n');await exited
    }
    await capture.locator('.native-toast button').click()
    console.log('PASS: clipboard busy keeps the crop open with an explicit error; retry remains available.')
  }
  await capture.locator('.capture-done').click()
  await capture.waitForFunction(()=>!document.querySelector('.capture-overlay'))
  const copied=await invoke('native_status')
  assert.equal(copied.captureActive,false)
  assert.deepEqual(copied.windows.image,windows.image,'Checkmark must not open an image window')
  assert.deepEqual(copied.windows.workspace,windows.workspace,'Checkmark must not open a conversation window')
  assert.equal(await capture.locator('.capture-ai-trigger').count(),0)
  if(!process.env.SNAPMIND_SCREEN_TRACE){
    const expected=await main.evaluate(async()=>{const a=(await window.__TAURI_INTERNALS__.invoke('get_desktop_state')).asset;const img=new Image();img.src=a.data;await img.decode();const c=document.createElement('canvas');c.width=a.width;c.height=a.height;c.getContext('2d').drawImage(img,0,0);return {width:a.width,height:a.height,pixel:Array.from(c.getContext('2d').getImageData(0,0,1,1).data)}})
    execFileSync(process.execPath,['scripts/verify-clipboard-paste.mjs',JSON.stringify(expected)],{windowsHide:true,stdio:'pipe'})
    console.log('PASS: checkmark result pastes directly with Ctrl+V before any pin action.')
  }
  await main.waitForTimeout(1000)
  await invoke('begin_capture')
  const id = (await invoke('get_desktop_state')).frame.asset.id
  await capture.waitForFunction(id => {const e=document.querySelector('.capture-overlay');return e?.dataset.sourceId===id&&e.dataset.ready==='true'},id)
  await invoke('finish_capture',{result:{data,width:120,height:80,action:'pin'}})
  let status = await invoke('native_status')
  assert.equal(status.windows.capture.visible,true,'Overlay must cover session preparation')
  assert.equal(status.captureActive,true,'Capture remains active until both content windows are ready')
  await capture.waitForFunction(() => !document.querySelector('.capture-overlay'),{}, {timeout:10000})
  status = await invoke('native_status')
  assert.equal(status.windows.capture.visible,false)
  assert.equal(status.captureActive,false)
  assert.equal(status.windows.image.visible,true)
  assert.equal(status.windows.workspace.visible,false,'Pin must not open a conversation window')
  assert.deepEqual(status.windows.main,windows.main,'Launcher geometry/visibility must not change')
  assert.deepEqual(await image.locator('.native-image img').evaluate(e => [e.complete,e.naturalWidth,e.naturalHeight]),[true,120,80])
  assert.equal(await image.locator('.native-image-window>header,.native-image-window>footer').count(),0)
  const fills=await image.locator('.native-image img').evaluate(e=>{const r=e.getBoundingClientRect();return Math.abs(r.x)<1&&Math.abs(r.y)<1&&Math.abs(r.width-innerWidth)<1&&Math.abs(r.height-innerHeight)<1})
  assert.equal(fills,true,'Pinned image must fill the window without white bars')
  await image.locator('.pin-image-only').click({position:{x:60,y:60}})
  const beforeZoom=(await invoke('native_status')).windows.image.size
  await image.locator('.pin-image-only').dispatchEvent('wheel',{deltaY:-120,bubbles:true,cancelable:true})
  for(let n=0;n<50&&(await invoke('native_status')).windows.image.size.width<=beforeZoom.width;n++)await main.waitForTimeout(20)
  const enlarged=(await invoke('native_status')).windows.image.size
  assert.ok(enlarged.width>beforeZoom.width,'Wheel up must enlarge the selected image')
  assert.ok(Math.abs(enlarged.width/enlarged.height-1.5)<.01,'Zoom preserves aspect ratio')
  await image.locator('.pin-image-only').dispatchEvent('wheel',{deltaY:120,ctrlKey:true,bubbles:true,cancelable:true})
  for(let n=0;n<50&&(await invoke('native_status')).windows.image.size.width>=enlarged.width;n++)await main.waitForTimeout(20)
  assert.ok((await invoke('native_status')).windows.image.size.width<enlarged.width,'Ctrl+wheel down must shrink the selected image')
  await image.locator('.pin-image-only').click({button:'right',position:{x:60,y:60}})
  await image.getByRole('menu',{name:'贴图菜单'}).waitFor()
  assert.equal(await image.getByRole('menuitem',{name:'下载截图'}).count(),1)
  assert.ok((await image.locator('.pin-image-details').innerText()).includes('120 × 80 px'))
  await image.getByRole('menuitem',{name:'关闭浮动截图',exact:true}).click()
  for(let n=0;n<50&&(await invoke('native_status')).windows.image.visible;n++)await main.waitForTimeout(20)
  assert.equal((await invoke('native_status')).windows.image.visible,false,'Image close button must hide the native window')
  assert.deepEqual(errors,[])
  console.log('PASS: checkmark copies with no popup; pin has no white bars; wheel/Ctrl+wheel preserve aspect ratio; right-click provides download/dimensions/close; no history writes or model calls.')
} finally {
  await invoke('cancel_capture').catch(() => {})
  await invoke('set_desktop_session',{sessionId:original.sessionId||'',asset:original.asset||null,notifyWorkspace:false}).catch(() => {})
  const path='/@fs/'+resolve('node_modules/@tauri-apps/api/window.js').replaceAll('\\','/')
  await main.evaluate(async ({path,windows}) => {
    const {Window,PhysicalSize,PhysicalPosition}=await import(path)
    for(const label of ['main','image','workspace']) {
      const w=await Window.getByLabel(label), previous=windows[label]
      await w.setSize(new PhysicalSize(previous.size.width,previous.size.height))
      await w.setPosition(new PhysicalPosition(previous.position.x,previous.position.y))
      if(previous.visible) await w.show(); else await w.hide()
    }
  },{path,windows}).catch(() => {})
  await main.reload(); await main.waitForTimeout(700)
  for(let i=0;i<pages.length;i++) await pages[i].evaluate(saved => {localStorage.clear();for(const [key,value] of Object.entries(saved))localStorage.setItem(key,value)},storage[i]).catch(() => {})
  await context.unroute(routePattern)
  await main.reload()
  await browser.close()
}
