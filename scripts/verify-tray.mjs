// Native tray layout and navigation. No capture, model inference, saved settings or quit action.
import {connectNative,invoke,delay} from './native-cdp.mjs'
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
const main=await connectNative()
let tray
async function waitFor(fn){for(let n=0;n<80;n++){if(await fn())return;await delay(100)}throw Error('Native tray state timeout')}
const status=()=>invoke(main,'native_status')
const show=async()=>{await invoke(main,'show_tray_tools');await waitFor(async()=>!!(await status()).windows.tray?.visible)}
const screenshot=async path=>{const result=await tray.send('Page.captureScreenshot',{format:'png'});await writeFile(path,Buffer.from(result.data,'base64'))}
try{
 if((await status()).captureActive)throw Error('Capture active; tray verification skipped')
 const original=await main.evaluate(()=>({settings:!!document.querySelector('#home-settings'),tab:document.querySelector('.settings-tabs [aria-selected="true"]')?.id}))
 assert.equal(await main.evaluate(async()=>Object.hasOwn(await import('/src/capture.ts'),'captureDemo')),false,'The removed capture experience must not remain exported')
 await show();tray=await connectNative('tray')
 await waitFor(()=>tray.evaluate(()=>document.querySelectorAll('.tool-menu-group button').length===2))
 const layout=await tray.evaluate(()=>{
  const quit=document.querySelector('.tray-menu-exit button').getBoundingClientRect()
  return {width:innerWidth,height:innerHeight,buttons:[...document.querySelectorAll('.tool-menu-group button')].map(b=>b.getAttribute('aria-label')),chrome:document.querySelectorAll('.tool-menu-brand,.tool-menu-footer,.tool-menu-group small,.tool-menu-group kbd').length,tag:!!document.querySelector('.tool-menu-tag'),robot:!!document.querySelector('[aria-label="模型配置"] .lucide-bot-message-square-icon'),quit:{width:quit.width,y:quit.y,bottom:quit.bottom},overflow:document.documentElement.scrollWidth>innerWidth||document.querySelector('.tool-menu-groups').scrollHeight>document.querySelector('.tool-menu-groups').clientHeight}
 })
 assert.equal(layout.width,140);assert.equal(layout.height,136)
 assert.deepEqual(layout.buttons,['截图','模型配置']);assert.equal(layout.chrome,0);assert.equal(layout.tag,false);assert.equal(layout.robot,true);assert.equal(layout.overflow,false)
 assert.ok(layout.quit.width>=layout.width-18&&layout.quit.bottom<=layout.height)
 await mkdir('artifacts',{recursive:true});await screenshot('artifacts/tray-tools-native.png')
 await invoke(main,'show_launcher');await waitFor(async()=>!(await status()).windows.tray.visible)
 await show();await tray.send('Input.dispatchKeyEvent',{type:'keyDown',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await tray.send('Input.dispatchKeyEvent',{type:'keyUp',key:'Escape',code:'Escape',windowsVirtualKeyCode:27});await waitFor(async()=>!(await status()).windows.tray.visible)
 await show();await tray.evaluate(()=>document.querySelector('[aria-label="模型配置"]').click());await waitFor(()=>main.evaluate(()=>document.querySelector('#settings-tab-models')?.getAttribute('aria-selected')==='true'));await waitFor(async()=>!(await status()).windows.tray.visible)
 assert.equal(await main.evaluate(()=>!!document.querySelector('#model-category-llm .lucide-bot-message-square-icon')),true,'Tray and settings must use the same model icon')
 if(original.settings&&original.tab)await main.evaluate(id=>document.getElementById(id)?.click(),original.tab)
 else await main.evaluate(()=>document.querySelector('#home-settings .settings-return-home')?.click())
 console.log('PASS: Native tray is 140 x 136, contains only capture/model/quit icon rows, has no descriptions/header/footer/shortcut, shares the model icon and supports blur/Escape/model navigation. No capture or quit performed.')
}finally{if(tray){await tray.evaluate(()=>window.__TAURI_INTERNALS__.invoke('hide_desktop_window')).catch(()=>{});tray.close()}main.close()}
