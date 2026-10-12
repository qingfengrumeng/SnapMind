// Use the existing desktop WebViews and generated pixels; restore user shortcut choices afterwards.
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
import {connectNative,invoke,delay} from './native-cdp.mjs'
const main=await connectNative(),capture=await connectNative('capture')
const waitFor=async test=>{for(let i=0;i<100;i++){if(await test())return;await delay(100)}throw Error('Native shortcut check timed out')}
const press=async(key,code,virtual,modifiers=0,target=capture)=>{await target.send('Input.dispatchKeyEvent',{type:'rawKeyDown',key,code,windowsVirtualKeyCode:virtual,modifiers});await target.send('Input.dispatchKeyEvent',{type:'keyUp',key,code,windowsVirtualKeyCode:virtual,modifiers})}
let started=false,changed=false,original
try{
 assert.equal((await invoke(main,'native_status')).captureActive,false,'Finish the user capture before this check')
 original=await main.evaluate(()=>localStorage.getItem('snapmind.capture.shortcuts'))
 await main.send('Page.reload',{ignoreCache:true});await capture.send('Page.reload',{ignoreCache:true});await delay(1200)
 await main.evaluate(async()=>{const m=await import('/src/tool-shortcuts.ts');m.resetToolShortcuts()});changed=true
 await main.evaluate(()=>document.querySelector('[aria-label="设置与工具"]').click());await waitFor(()=>main.evaluate(()=>!!document.querySelector('#settings-tab-general')));await main.evaluate(()=>document.querySelector('#settings-tab-general').click())
 assert.equal(await main.evaluate(()=>document.querySelectorAll('.tool-shortcut-row').length),29)
 const layout=await main.evaluate(()=>{const h=document.querySelector('.tool-shortcut-settings header');return {text:h.querySelector('p').getBoundingClientRect().width,button:h.querySelector('button').getBoundingClientRect().width,width:h.getBoundingClientRect().width}});assert.ok(layout.text>layout.width*.5&&layout.button<layout.width*.3,'Settings help and restore button fit side by side')
 const settingsClip=await main.evaluate(()=>{const r=document.querySelector('.snapmind-home').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,scale:1}}),settingsImage=await main.send('Page.captureScreenshot',{format:'png',clip:settingsClip});await mkdir('artifacts/image-tools',{recursive:true});await writeFile('artifacts/image-tools/native-tool-shortcut-settings.png',Buffer.from(settingsImage.data,'base64'))
 await main.evaluate(()=>{const b=document.querySelector('[aria-label="矩形快捷键"]');b.focus();b.click()});await waitFor(()=>main.evaluate(()=>document.querySelector('[aria-label="矩形快捷键"]').getAttribute('aria-pressed')==='true'))
 await press('6','Digit6',54,0,main);await waitFor(()=>main.evaluate(()=>document.querySelector('[aria-label="矩形快捷键"]').getAttribute('aria-pressed')==='false'))
 assert.equal(await main.evaluate(()=>document.querySelector('[aria-label="矩形快捷键"]').textContent.trim()),'6')
 const fixture=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=1600;c.height=900;const g=c.getContext('2d');g.fillStyle='#faf7ff';g.fillRect(0,0,c.width,c.height);g.fillStyle='#c7afe9';g.fillRect(90,100,300,180);return {id:'native-shortcuts-generated-'+Date.now(),name:'Generated shortcut check',data:c.toDataURL(),width:c.width,height:c.height,scenario:'custom'}})
 await invoke(main,'begin_preview_capture',{asset:fixture});started=true
 await waitFor(()=>capture.evaluate(id=>document.querySelector('.capture-overlay')?.dataset.sourceId===id&&document.querySelector('.capture-overlay')?.dataset.ready==='true',fixture.id))
 const box=await capture.evaluate(()=>{const r=document.querySelector('.capture-screen').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}}),start={x:box.x+box.w*.04,y:box.y+box.h*.06},end={x:box.x+box.w*.96,y:box.y+box.h*.83}
 await capture.send('Input.dispatchMouseEvent',{type:'mouseMoved',...start});await capture.send('Input.dispatchMouseEvent',{type:'mousePressed',...start,button:'left',buttons:1,clickCount:1});await capture.send('Input.dispatchMouseEvent',{type:'mouseMoved',...end,button:'left',buttons:1});await capture.send('Input.dispatchMouseEvent',{type:'mouseReleased',...end,button:'left',clickCount:1})
 await waitFor(()=>capture.evaluate(()=>document.querySelector('[data-capture-tool="rect"]')?.dataset.shortcut==='6'))
 assert.equal(await capture.evaluate(()=>document.querySelectorAll('.capture-tools-scroll button[data-capture-tool]').length),26)
 await press('6','Digit6',54);await waitFor(()=>capture.evaluate(()=>document.querySelector('[data-capture-tool="rect"]').classList.contains('active')))
 await press('6','Digit6',54);assert.equal(await capture.evaluate(()=>document.querySelector('[data-capture-tool="rect"]').classList.contains('active')),false)
 await capture.evaluate(()=>document.querySelector('[data-capture-tool="rect"]').focus({preventScroll:true}))
 await waitFor(()=>capture.evaluate(()=>document.querySelector('.tool-shortcut-popup')?.getAttribute('aria-label')==='矩形快捷键配置'))
 await capture.evaluate(()=>{const b=document.querySelector('.tool-shortcut-popup [aria-label="矩形快捷键"]');b.focus();b.click()});await waitFor(()=>capture.evaluate(()=>!!document.querySelector('.tool-shortcut-popup .recording')))
 await press('5','Digit5',53)
 await waitFor(()=>main.evaluate(()=>document.querySelector('[aria-label="矩形快捷键"]')?.textContent.trim()==='5'))
 await capture.evaluate(()=>{const b=document.querySelector('.tool-shortcut-popup [aria-label="矩形快捷键"]');b.focus();b.click()});await waitFor(()=>capture.evaluate(()=>!!document.querySelector('.tool-shortcut-popup .recording')))
 await press('m','KeyM',77);await waitFor(()=>capture.evaluate(()=>document.querySelector('.tool-shortcut-popup [role="alert"]')?.textContent.includes('马赛克')))
 assert.equal(await capture.evaluate(()=>document.querySelector('[data-capture-tool="rect"]').dataset.shortcut),'5')
 await press('4','Digit4',52,3);await waitFor(()=>main.evaluate(()=>document.querySelector('[aria-label="矩形快捷键"]')?.textContent.trim()==='Ctrl+Alt+4'))
 await capture.evaluate(()=>document.querySelector('.capture-overlay').focus());await press('4','Digit4',52,3);await waitFor(()=>capture.evaluate(()=>document.querySelector('[data-capture-tool="rect"]').classList.contains('active')))
 await press('4','Digit4',52,3)
 await press('c','KeyC',67);await waitFor(()=>capture.evaluate(()=>!!document.querySelector('.capture-conversation-panel')))
 await capture.evaluate(()=>document.querySelector('[aria-label="图片对话输入"]').focus());await press('p','KeyP',80)
 assert.equal(await capture.evaluate(()=>document.querySelector('[data-capture-tool="pen"]').classList.contains('active')),false)
 await capture.evaluate(()=>document.querySelector('.capture-overlay').focus());await press('c','KeyC',67);await waitFor(()=>capture.evaluate(()=>!document.querySelector('.capture-conversation-panel')))
 await capture.evaluate(async()=>{const m=await import('/src/tool-shortcuts.ts');m.setToolShortcut('save','0')});await waitFor(()=>main.evaluate(()=>document.querySelector('[aria-label="保存快捷键"]')?.textContent.trim()==='0'))
 const keys=await capture.evaluate(async()=>{const m=await import('/src/tool-shortcuts.ts');return m.liveScrollKeys()});assert.equal(keys.find(k=>k.action===1).keyCode,48)
 await capture.evaluate(()=>document.querySelector('[data-capture-tool="translate"]').focus({preventScroll:true}));await waitFor(()=>capture.evaluate(()=>document.querySelector('.tool-shortcut-popup')?.getAttribute('aria-label')==='翻译快捷键配置'));await delay(600);assert.equal(await capture.evaluate(()=>document.querySelector('.tool-shortcut-popup')?.getAttribute('aria-label')),'翻译快捷键配置')
 const clip=await capture.evaluate(()=>{const a=document.querySelector('.tool-shortcut-popup').getBoundingClientRect(),b=document.querySelector('.capture-toolbar').getBoundingClientRect(),x=Math.min(a.x,b.x),y=Math.min(a.y,b.y);return {x,y,width:Math.max(a.right,b.right)-x,height:Math.max(a.bottom,b.bottom)-y,scale:1}})
 const image=await capture.send('Page.captureScreenshot',{format:'png',clip});await mkdir('artifacts/image-tools',{recursive:true});await writeFile('artifacts/image-tools/native-tool-shortcuts.png',Buffer.from(image.data,'base64'))
 console.log('PASS: actual desktop toolbar and settings, direct key recording, conflict rejection, recorded combinations, keyboard toggles, input protection, native-key serialization and cross-WebView synchronization.')
}finally{
 if(started)await invoke(main,'cancel_capture')
 if(changed){await main.evaluate(raw=>{const key='snapmind.capture.shortcuts';if(raw===null)localStorage.removeItem(key);else localStorage.setItem(key,raw);window.dispatchEvent(new StorageEvent('storage',{key,newValue:raw}))},original);await capture.evaluate(raw=>window.dispatchEvent(new StorageEvent('storage',{key:'snapmind.capture.shortcuts',newValue:raw})),original);await main.evaluate(()=>document.querySelector('[aria-label="关闭设置面板"]')?.click())}
 main.close();capture.close()
}
