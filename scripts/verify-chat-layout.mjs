// Synthetic images and mocked API responses; no model requests or saved records.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1000}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',r=>r.fulfill({json:new URL(r.request().url()).pathname==='/api/sessions'?[]:{tools:[],items:[]}}))
 await page.goto('http://127.0.0.1:5174')
 async function mount(floating){await page.evaluate(async floating=>{const [{default:Overlay},{createApp}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const c=document.createElement('canvas');c.width=420;c.height=260;c.getContext('2d').fillRect(0,0,420,260);const host=document.createElement('div');document.body.append(host);window.chatTestHost=host;window.chatTestApp=createApp(Overlay,{source:{id:'synthetic-chat-layout',name:'Synthetic',data:c.toDataURL(),width:420,height:260,scenario:'custom'},initialSelection:true,floatingPreview:floating});window.chatTestApp.mount(host)},floating);await page.locator('.capture-overlay[data-ready="true"]').waitFor()}
 async function unmount(){await page.evaluate(()=>{window.chatTestApp.unmount();window.chatTestHost.remove()})}
 const panel=page.locator('.capture-conversation-panel'),bar=page.locator('.capture-toolbar'),picture=page.locator('.capture-screen')
 await mount(true)
 for(const side of ['right','left']){
  if(side==='left'){const r=await picture.boundingBox();await page.mouse.move(r.x+70,r.y+70);await page.mouse.down();await page.mouse.move(r.x+400,r.y+70,{steps:4});await page.mouse.up()}
  const crop=await picture.boundingBox()
  await page.locator('[data-capture-tool="chat"]').click();await panel.waitFor()
  assert.equal(await bar.count(),0,'Conversation must hide the complete screenshot toolbar')
  let r=await panel.boundingBox();assert.equal(r.y,120);assert.equal(r.height,760)
  assert.ok(side==='right'?r.x>=crop.x+crop.width:r.x+r.width<=crop.x,'Conversation must appear beside the image on the available side')
  assert.deepEqual(await picture.boundingBox(),crop,'Opening conversation must not move or resize the image')
  assert.ok(await panel.locator('textarea').last().isVisible(),'Composer must remain visible at the bottom')
  await panel.locator('.chat-image-chip>button:first-child').click();await page.getByRole('button',{name:'关闭图片预览'}).press('Escape')
  assert.equal(await page.locator('.image-chat-lightbox').count(),0);assert.equal(await panel.count(),1,'Preview Escape must keep the floating conversation open')
  await mkdir('artifacts/chat-layout',{recursive:true});await page.screenshot({path:`artifacts/chat-layout/${side}.png`})
  await panel.getByRole('button',{name:'关闭截图对话',exact:true}).click();assert.equal(await bar.count(),1)
 }
 await page.locator('[data-capture-tool="chat"]').click();await page.setViewportSize({width:390,height:844});let r=await panel.boundingBox();assert.equal(r.height,760);assert.equal(r.y,42);assert.ok(r.x>=0&&r.x+r.width<=390)
 await page.setViewportSize({width:390,height:600});r=await panel.boundingBox();assert.equal(r.height,576);assert.equal(r.y,12)
 const composer=await panel.locator('.image-chat-input-box').boundingBox();assert.ok(composer.y>=r.y&&composer.y+composer.height<=r.y+r.height,'Composer must fit a short screen')
 await panel.getByRole('button',{name:'关闭截图对话',exact:true}).click();assert.equal(await bar.count(),1)
 await unmount();await page.setViewportSize({width:1480,height:1000});await mount(false)
 await page.locator('[data-capture-tool="chat"]').click();assert.equal(await bar.count(),0);r=await panel.boundingBox();assert.equal(r.height,760)
 await panel.getByRole('button',{name:'关闭截图对话',exact:true}).click();assert.equal(await bar.count(),1)
 await unmount();assert.deepEqual(errors,[])
 console.log('PASS: Conversation uses a centered, capped height, hides/restores the toolbar, docks left/right, keeps the image intact and fits narrow and short screens in both capture and image editing.')
}finally{await browser.close()}
