// Object detection is invoked through conversation and stays editable on the screenshot.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1050}}),pending=[],errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/detection-fixture',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/src/styles.css"><link rel="stylesheet" href="/src/screenshot.css"><link rel="stylesheet" href="/src/image-conversation.css"><div id="fixture"></div>'}))
 await page.route('**/api/**',r=>{if(new URL(r.request().url()).pathname==='/api/capture/conversation'){pending.push({route:r,body:r.request().postDataJSON()});return}return r.fulfill({json:{}})})
 await page.goto('http://127.0.0.1:5174/detection-fixture')
 await page.evaluate(async()=>{const [{default:Overlay},{createApp}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const c=document.createElement('canvas');c.width=960;c.height=620;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,960,620);g.fillStyle='#f5bd42';g.fillRect(100,370,180,95);window.exports=[];createApp(Overlay,{source:{id:'generated-screen',name:'Generated',data:c.toDataURL(),width:960,height:620,scenario:'custom'},initialSelection:true,onFinish:r=>window.exports.push(r)}).mount('#fixture')})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const overlay=page.locator('.capture-overlay'),screen=page.locator('.capture-screen'),button=name=>overlay.getByRole('button',{name,exact:true}),original=await screen.evaluate(c=>c.toDataURL())
 for(const name of ['物体识别','AI 标注','解释','二维码／条码','链接与邮箱'])assert.equal(await button(name).count(),0)
 await button('AI对话').click()
 const ask=async text=>{await page.getByRole('textbox',{name:'图片对话输入'}).fill(text);await page.getByRole('button',{name:'发送图片对话',exact:true}).click();await page.getByRole('button',{name:'暂停输出',exact:true}).waitFor();while(!pending.at(-1)||pending.at(-1).body.prompt!==text)await page.waitForTimeout(10)}
 await ask('识别并标记截图中的物体');assert.equal(pending[0].body.action,undefined)
 await pending[0].route.fulfill({json:{action:'detect',assetId:pending[0].body.selectedId,answer:'已标记一个物体',payload:{objects:[{id:'object-1',label:'测试色块',bbox:[100,370,280,465]}],width:960,height:620,coordinateSpace:'image-pixels',approximate:true}}})
 await page.getByText('已标记一个物体',{exact:true}).waitFor();await page.waitForFunction(data=>document.querySelector('.capture-screen').toDataURL()!==data,original)
 const marked=await screen.evaluate(c=>c.toDataURL());assert.equal(await page.locator('.capture-toolbar').count(),0,'Toolbar is replaced by the open conversation panel')
 await ask('继续识别');await pending[1].route.fulfill({status:502,json:{detail:'模型位置不完整'}});await page.getByRole('alert').filter({hasText:'模型位置不完整'}).waitFor();assert.equal(await screen.evaluate(c=>c.toDataURL()),marked)
 await ask('再识别物体');await page.getByRole('button',{name:'暂停输出',exact:true}).click();await pending[2].route.abort().catch(()=>{});assert.equal(await screen.evaluate(c=>c.toDataURL()),marked)
 await button('关闭截图对话').click();await button('截图移动标注').click()
 const box=await screen.boundingBox(),scale=box.width/960,point=(x,y)=>({x:box.x+x*scale,y:box.y+y*scale}),a=point(100,410),b=point(175,420)
 await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:8});await page.mouse.up();assert.notEqual(await screen.evaluate(c=>c.toDataURL()),marked)
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),marked)
 await page.mouse.click(a.x,a.y);await page.getByLabel('已选中的标注').waitFor();assert.match(await button('截图移动标注').getAttribute('title'),/Backspace/)
 await page.keyboard.press('Delete');assert.equal(await screen.evaluate(c=>c.toDataURL()),marked,'Delete no longer removes a selected mark')
 await page.keyboard.press('Backspace');assert.equal(await screen.evaluate(c=>c.toDataURL()),original)
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),marked)
 await button('完成并复制截图').click();await page.waitForFunction(()=>window.exports.length===1);assert.equal(await page.evaluate(()=>window.exports[0].data),marked)
 assert.deepEqual(errors,[])
 console.log('PASS: object detection via conversation, persistent toolbar, editable screenshot marks, move/Backspace/undo, failure/cancellation and exported pixels.')
}finally{await browser.close()}
