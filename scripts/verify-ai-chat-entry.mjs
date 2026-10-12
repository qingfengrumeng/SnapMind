// Generated image only: grouped scroll/pin/AI controls, tooltip and slash tools.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir,readFile} from 'node:fs/promises'
const catalog=await(await fetch('http://127.0.0.1:8776/api/tools')).json()
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1000}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',r=>{const path=new URL(r.request().url()).pathname;return r.fulfill({json:path==='/api/tools'?catalog:path==='/api/sessions'?[]:path==='/api/settings/models'?{activeId:null,profiles:[]}:{mode:'test',items:[]}})})
 await page.goto('http://127.0.0.1:5174');await page.locator('.launcher-titlebar').waitFor()
 assert.equal(await page.locator('.launcher-titlebar').getByRole('button',{name:'图片对话',exact:true}).count(),0)
 assert.equal(await page.locator('.standalone-image-chat').count(),0)
 // Verify both home settings and tray menu can no longer open a homepage dialogue.
 const menuActions=await page.evaluate(async()=>{const [{default:Menu},{createApp}]=await Promise.all([import('/src/components/ToolMenu.vue'),import('/node_modules/.vite/deps/vue.js')]);const result=[];for(const tray of [false,true]){const root=document.createElement('div');document.body.append(root);const app=createApp(Menu,{tray});app.mount(root);result.push([...root.querySelectorAll('button')].map(b=>b.getAttribute('aria-label')));app.unmount();root.remove()}return result})
 for(const actions of menuActions)assert.ok(!actions.includes('图片对话'))
 await page.evaluate(async()=>{const [{default:Overlay},{createApp}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const root=document.createElement('div');document.body.append(root);const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#fbf9ff';g.fillRect(0,0,800,500);g.fillStyle='#493368';g.font='24px Segoe UI';g.fillText('AI image conversation',40,65);g.fillStyle='#d9c2f8';g.fillRect(70,130,190,120);createApp(Overlay,{source:{id:'entry-fixture',name:'Generated',data:c.toDataURL(),width:800,height:500,scenario:'custom'},initialSelection:true}).mount(root)})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const bar=page.locator('.capture-toolbar>.capture-tools-scroll'),ai=bar.getByRole('button',{name:'AI对话',exact:true})
 assert.equal(await bar.getByRole('button',{name:'全部图片工具',exact:true}).count(),0);assert.equal(await page.locator('.capture-function-menu').count(),0)
 const secondGroup=await bar.getByRole('button',{name:'滚动截图',exact:true}).evaluate(el=>[el,el.nextElementSibling,...el.parentElement.querySelector('.capture-ai-tools').querySelectorAll('button')].map(b=>b?.getAttribute('aria-label')))
 assert.deepEqual(secondGroup,['滚动截图','截图贴图','AI对话','语音通话'])
 assert.equal(await ai.evaluate(el=>el.parentElement.nextElementSibling?.classList.contains('capture-separator')),true)
 assert.equal(await bar.locator('button').last().getAttribute('aria-label'),'完成并复制截图')
 assert.deepEqual(await ai.evaluate(el=>{const css=getComputedStyle(el);return [css.backgroundImage,css.backgroundColor,css.borderTopWidth]}),['none','rgba(0, 0, 0, 0)','0px'])
 assert.equal(await ai.getAttribute('data-tooltip'),'AI对话');assert.equal(await ai.locator('svg.ai-chat-bubble-icon').count(),1)
 await ai.hover();await page.getByRole('dialog',{name:'AI对话快捷键配置',exact:true}).waitFor()
 await mkdir('artifacts/image-tools',{recursive:true});await page.screenshot({path:'artifacts/image-tools/ai-chat-entry.png'})
 for(const width of [1480,850,520]){
  await page.setViewportSize({width,height:1000});await page.waitForTimeout(100)
  for(const scrollToEnd of [false,true]){
   await bar.evaluate((el,end)=>el.scrollLeft=end?el.scrollWidth:0,scrollToEnd)
   const bounds=await ai.boundingBox(),strip=await bar.boundingBox(),done=await bar.getByRole('button',{name:'完成并复制截图',exact:true}).boundingBox(),cancel=await bar.getByRole('button',{name:'取消截图',exact:true}).boundingBox(),save=await bar.getByRole('button',{name:'保存截图',exact:true}).boundingBox()
   assert.ok(Math.abs(done.x+done.width-strip.x-strip.width)<12,'complete action must stay on right edge')
   assert.ok(save.x+save.width<=cancel.x&&cancel.x+cancel.width<=done.x,'sticky controls must not overlap')
   if(scrollToEnd)assert.ok(bounds.x>=0&&bounds.x+bounds.width<=save.x,'AI action must be reachable without overlapping export controls')
  }
 }
 await page.screenshot({path:'artifacts/image-tools/ai-chat-entry-narrow.png'})
 await ai.click();await page.getByLabel('图片对话面板',{exact:true}).waitFor();assert.equal(await bar.count(),0)
 const input=page.getByRole('textbox',{name:'图片对话输入'});await input.fill('/');await page.waitForFunction(()=>document.querySelectorAll('.image-tool-menu [role=option]').length===14)
 assert.equal(await page.locator('.capture-toolbar').count(),0);await input.press('Escape');assert.equal(await page.getByLabel('图片对话面板',{exact:true}).count(),1)
 await page.getByRole('button',{name:'关闭截图对话',exact:true}).click();assert.equal(await page.getByLabel('图片对话面板',{exact:true}).count(),0)
 const download=page.waitForEvent('download');await bar.getByRole('button',{name:'保存截图',exact:true}).click()
 await (await download).saveAs('artifacts/image-tools/direct-download.png')
 const png=await readFile('artifacts/image-tools/direct-download.png');assert.equal(png.readUInt32BE(16),800);assert.equal(png.readUInt32BE(20),500)
 assert.equal(await page.locator('.capture-tool-options').count(),0,'Save directly downloads without opening options')
 assert.equal(await bar.getByRole('button',{name:'保存截图',exact:true}).getAttribute('class'),null,'Download is an action, not a selected tool')
 assert.deepEqual(errors,[])
 console.log('PASS: scroll/pin/AI group, light icon styling, responsive export controls, tooltip, dialogue and all slash tools; direct PNG download.')
}finally{await browser.close()}
