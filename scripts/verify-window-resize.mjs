import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {resolve} from 'node:path'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const main=browser.contexts()[0].pages().find(p=>p.url().includes('5174')&&!p.url().includes('desktop='))
const modulePath='/@fs/'+resolve('node_modules/@tauri-apps/api/window.js').replaceAll('\\','/')
const original=await main.evaluate(async path=>{const {getCurrentWindow}=await import(path);const w=getCurrentWindow();return {size:await w.innerSize(),position:await w.outerPosition(),gallery:localStorage.getItem('snapmind-gallery-view')}},modulePath)
const errors=[];main.on('pageerror',e=>errors.push(e.message))
try{
 await main.evaluate(()=>window.__TAURI_INTERNALS__.invoke('show_launcher'))
 for(const [width,height] of [[800,700],[560,480],[1000,780]]){
  await main.evaluate(async ({path,width,height})=>{const {getCurrentWindow,LogicalSize}=await import(path);await getCurrentWindow().setSize(new LogicalSize(width,height))},{path:modulePath,width,height})
  await main.waitForFunction(({width,height})=>Math.abs(innerWidth-width)<=2&&Math.abs(innerHeight-height)<=2,{width,height})
  const settings=main.getByRole('button',{name:'设置与工具',exact:true})
  if(await settings.getAttribute('aria-expanded')==='true')await settings.evaluate(e=>e.click())
  await main.getByRole('button',{name:'网格展示',exact:true}).evaluate(e=>e.click())
  assert.equal(await main.locator('.launcher-resize-edge').count(),8)
  assert.equal(await main.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true)
  if(await main.locator('.launcher-recent-grid').count()){
   assert.equal(await main.locator('.launcher-recent-grid').evaluate(e=>getComputedStyle(e).gridTemplateColumns.split(' ').length),2)
   const gallery=await main.locator('.launcher-gallery-body').boundingBox();assert.ok(gallery.height>80&&gallery.y+gallery.height<=height+2)
   await main.waitForFunction(()=>[...document.querySelectorAll('.shot-thumbnail img')].slice(0,2).every(img=>img.complete&&img.naturalWidth>0))
   if(width===800){const thumb=await main.locator('.shot-thumbnail').first().boundingBox();assert.ok(thumb.width>300&&thumb.height>=150);await main.screenshot({path:'artifacts/native-gallery-large.png'})}
  }
  await settings.evaluate(e=>e.click())
  const panel=main.getByRole('navigation',{name:'设置与工具面板'})
  const box=await panel.boundingBox();assert.ok(Math.abs(box.width-width)<=2&&Math.abs(box.y+box.height-height)<=2)
  assert.equal(await main.getByRole('tab').count(),4)
  await main.getByRole('tab',{name:'模型配置',exact:true}).evaluate(e=>e.click())
  const model=main.getByRole('button',{name:'配置 DeepSeek',exact:true});await model.scrollIntoViewIfNeeded();await model.evaluate(e=>e.click());await main.locator('[data-profile-id="deepseek"] form').waitFor();assert.equal(await main.getByRole('dialog').count(),0)
  assert.equal(await main.locator('.settings-tab-content').evaluate(e=>e.scrollWidth<=e.clientWidth),true);await settings.evaluate(e=>e.click())
 }
 assert.deepEqual(errors,[]);console.log('PASS: native 800x700, 560x480 and 1000x780; two-column gallery, adaptive settings, eight resize handles, inline models, no overflow or errors.')
}finally{
 await main.evaluate(async ({path,original})=>{const {getCurrentWindow,PhysicalSize,PhysicalPosition}=await import(path);const w=getCurrentWindow();await w.setSize(new PhysicalSize(original.size.width,original.size.height));await w.setPosition(new PhysicalPosition(original.position.x,original.position.y))},{path:modulePath,original})
 const settings=main.getByRole('button',{name:'设置与工具',exact:true});if(await settings.getAttribute('aria-expanded')==='true')await settings.evaluate(e=>e.click())
 if(original.gallery==='list')await main.getByRole('button',{name:'列表展示',exact:true}).evaluate(e=>e.click())
 await browser.close()
}
