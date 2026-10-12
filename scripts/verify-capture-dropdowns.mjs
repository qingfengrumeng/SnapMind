// Headless synthetic image only. Never opens a desktop window or calls a model.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>route.fulfill({json:{text:'Synthetic translation',mode:'model',model:'Fixture'}}))
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#252429';g.fillRect(0,0,800,500);g.fillStyle='#d7d0df';g.font='24px Arial';g.fillText('Screenshot annotation preview',60,80)
  window.dropdownActions={finish:0,cancel:0};const node=document.createElement('div');document.body.append(node)
  createApp({render:()=>h(Overlay,{source:{id:'dropdown-fixture',name:'Synthetic',data:c.toDataURL(),width:800,height:500,scenario:'custom'},onFinish:()=>window.dropdownActions.finish++,onCancel:()=>window.dropdownActions.cancel++})}).mount(node)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const box=await page.locator('.capture-screen').boundingBox(),point=(x,y)=>({x:box.x+x*box.width/800,y:box.y+y*box.height/500})
 const a=point(50,50),z=point(700,260);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(z.x,z.y);await page.mouse.up()
 const button=name=>page.getByRole('button',{name,exact:true}),menu=page.getByRole('listbox')
 await button('截图箭头').click();await button('箭头样式').click()
 assert.equal(await menu.getByRole('option').count(),4);assert.equal(await menu.getByRole('option',{selected:true}).innerText(),'空心')
 await page.keyboard.press('ArrowDown');await page.keyboard.press('Enter');assert.equal(await menu.count(),0);assert.equal(await button('箭头样式').innerText(),'实心')
 assert.equal((await page.evaluate(()=>window.dropdownActions)).finish,0,'Choosing a menu item must not finish capture')
 await button('线条样式').click();await menu.getByRole('option',{name:'虚线',exact:true}).click();assert.equal(await button('线条样式').innerText(),'虚线')
 await button('箭头样式').click();await page.screenshot({path:'artifacts/capture-dropdown-preview.png'})
 const bounds=await menu.boundingBox(),trigger=await button('箭头样式').boundingBox();assert.ok(bounds.y>=trigger.y+trigger.height,'Menu should open below options when space permits')
 await page.keyboard.press('Escape');assert.equal(await menu.count(),0);assert.equal((await page.evaluate(()=>window.dropdownActions)).cancel,0,'Escape closes the menu before cancelling capture')
 await button('箭头样式').click();await button('截图矩形').click();assert.equal(await menu.count(),0,'Clicking outside closes the menu')
 await button('翻译').click();await button('翻译语言').click();await menu.getByRole('option',{name:'繁体中文',exact:true}).click();assert.equal(await button('翻译语言').innerText(),'繁体中文')
 await page.setViewportSize({width:1280,height:620});await button('截图箭头').click();await button('箭头样式').click();const edge=await menu.boundingBox();assert.ok(edge.y>=0&&edge.y+edge.height<=620)
 await page.keyboard.press('Escape');await page.keyboard.press('Escape');assert.equal((await page.evaluate(()=>window.dropdownActions)).cancel,1)
 assert.deepEqual(errors,[])
 console.log('PASS: menu previews, selected states, keyboard and pointer selection, language settings, outside dismissal, Escape priority and viewport bounds.')
}finally{await browser.close()}
