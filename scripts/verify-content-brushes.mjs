// Generated image only. Repair calls the local Python engine; no LLM/OCR calls.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),errors=[],repairs=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/brush-fixture',route=>route.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/src/styles.css"><link rel="stylesheet" href="/src/screenshot.css"><link rel="stylesheet" href="/src/image-conversation.css"><div id="fixture"></div>'}))
 await page.route('**/api/capture/repair',async route=>{repairs.push(route.request().postDataJSON());const response=await route.fetch();assert.equal(response.status(),200);await route.fulfill({response})})
 await page.goto('http://127.0.0.1:5174/brush-fixture')
 await page.evaluate(async()=>{const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,800,500);g.fillStyle='#000';g.fillRect(180,100,60,20);g.font='20px Segoe UI';g.fillText('Highlight this text',160,65);createApp({render:()=>h(Overlay,{source:{id:'brush-test',name:'Generated brush test',data:c.toDataURL(),width:800,height:500,scenario:'custom'},initialSelection:true,onToast:text=>{window.fixtureToast=text}})}).mount('#fixture')})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const overlay=page.locator('.capture-overlay'),screen=page.locator('.capture-screen'),box=await screen.boundingBox(),scale=box.width/800
 const point=(x,y)=>({x:box.x+x*scale,y:box.y+y*scale})
 const button=name=>overlay.getByRole('button',{name,exact:true}),original=await screen.evaluate(c=>c.toDataURL())
 const pixel=(x,y)=>screen.evaluate((c,{x,y})=>Array.from(c.getContext('2d').getImageData(x,y,1,1).data),{x,y})
 const click=async(x,y)=>{const p=point(x,y);await page.mouse.click(p.x,p.y)}
 const drag=async(x,y,x2,y2)=>{const a=point(x,y),b=point(x2,y2);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y);await page.mouse.up()}
 const reset=async()=>{await button('清空截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),original)}
 // The new menu exposes off-screen tools and closes without cancelling capture.
 for(const name of ['离线文字识别','窗口截图','本机记忆填充','应用快照','增加截图区域','图片笔记','理解代码','注释论文','检查作答','提取公式','表格提取','解释','AI 标注','物体识别','二维码／条码','链接与邮箱'])assert.equal(await button(name).count(),0,'Removed toolbar button: '+name)
 assert.ok((await button('提取文字').locator('svg').getAttribute('class')).includes('lucide-scan-text'),'Text extraction must use the former offline OCR icon')
 assert.equal(await button('全部图片工具').count(),0)
 await button('截图荧光笔').click();await button('荧光笔画刷 40').click()
 assert.equal(await button('荧光笔方形画刷').getAttribute('class'),'mosaic-shape-choice chosen')
 await drag(160,110,260,110)
 assert.deepEqual(await pixel(200,110),[0,0,0,255],'Multiply highlight must preserve black text')
 const light=await pixel(170,110);assert.ok(light.slice(0,3).every(v=>v>=160),'White background must use a light tint')
 await reset()
 // Retracing a single stroke does not accumulate opacity.
 const a=point(330,180),b=point(430,180);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y);const once=await pixel(380,180);await page.mouse.move(a.x,a.y);await page.mouse.move(b.x,b.y);assert.deepEqual(await pixel(380,180),once);await page.mouse.up();await reset()
 await button('荧光笔圆形画刷').click();await click(350,180);assert.deepEqual(await pixel(360,190),[255,255,255,255],'Circle must leave square corners untouched at current zoom');assert.notDeepEqual(await pixel(350,180),[255,255,255,255]);await reset()
 await button('荧光笔方形画刷').click();await click(350,180);assert.notDeepEqual(await pixel(360,190),[255,255,255,255]);await reset()
 await drag(330,180,430,240);assert.notDeepEqual(await pixel(380,210),[255,255,255,255],'Fast diagonal square brush must be continuous');assert.deepEqual(await pixel(380,250),[255,255,255,255]);await reset()
 // Eraser selects; only Backspace removes the mark, with undo/redo available.
 await button('截图矩形').click();await drag(90,200,200,300);const rectangle=await screen.evaluate(c=>c.toDataURL())
 await button('截图橡皮擦').click();await click(90,250);assert.equal(await screen.evaluate(c=>c.toDataURL()),rectangle,'Selecting must not delete');await page.getByLabel('已选中的标注',{exact:true}).waitFor();assert.equal(await page.getByLabel('缩放标注',{exact:true}).count(),0)
 await page.keyboard.press('Delete');assert.equal(await screen.evaluate(c=>c.toDataURL()),rectangle,'Delete must not erase in eraser mode');await page.keyboard.press('Backspace');assert.equal(await screen.evaluate(c=>c.toDataURL()),original);await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),rectangle);await button('重做截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),original)
 // Real Python inpainting, brush masks, no preview pixels in the request.
 await button('截图涂抹消除').click();await button('涂抹消除画刷 40').click();await button('涂抹消除圆形画刷').click();await click(400,240)
 await page.waitForFunction(()=>window.fixtureToast==='已修补涂抹区域，可撤销')
 const maskPixel=(mask,x,y)=>page.evaluate(async({mask,x,y})=>{const i=new Image();i.src=mask;await i.decode();const c=document.createElement('canvas');c.width=i.width;c.height=i.height;const g=c.getContext('2d');g.drawImage(i,0,0);return g.getImageData(x,y,1,1).data[0]},{mask,x,y})
 assert.equal(await maskPixel(repairs[0].mask,410,250),0);assert.equal(await maskPixel(repairs[0].mask,400,240),255)
 await button('撤销截图标注').click();await button('涂抹消除方形画刷').click();await click(400,240);await page.waitForFunction(()=>document.querySelector('[aria-label="撤销截图标注"]')?.disabled===false);await page.waitForTimeout(200);assert.equal(await maskPixel(repairs[1].mask,410,250),255)
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),original)
 await page.getByLabel('涂抹消除画刷大小',{exact:true}).fill('80');await drag(180,110,240,110);await page.waitForFunction(()=>document.querySelector('[aria-label="撤销截图标注"]')?.disabled===false);await page.waitForTimeout(250)
 assert.ok((await pixel(200,110)).slice(0,3).every(v=>v>245),'Masked black content must be replaced by the white background');assert.deepEqual(await pixel(170,65),[255,255,255,255])
 assert.equal(await maskPixel(repairs.at(-1).asset.data,200,110),0,'Repair source must contain original black pixels without purple preview')
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),original)
 // Cursor footprint matches the selected shape, disappears over controls/outside.
 const p=point(400,200);await page.mouse.move(p.x,p.y);assert.equal(await overlay.evaluate(e=>e.style.cursor),'none');const cursor=page.locator('.capture-content-brush-cursor');assert.equal(await cursor.isVisible(),true);assert.equal(await cursor.evaluate(e=>getComputedStyle(e).borderRadius),'1px')
 await button('涂抹消除圆形画刷').click();await page.mouse.move(p.x,p.y);assert.equal(await cursor.evaluate(e=>getComputedStyle(e).borderRadius),'50%');await page.mouse.move(1,1);assert.equal(await overlay.evaluate(e=>e.style.cursor),'default');assert.equal(await cursor.count(),0)
 await button('截图涂抹消除').click();assert.notEqual(await button('截图涂抹消除').getAttribute('class'),'active')
 assert.deepEqual(errors,[]);await mkdir('artifacts/image-tools',{recursive:true});await button('截图荧光笔').click();await drag(150,60,360,60);await page.screenshot({path:'artifacts/image-tools/content-brushes.png'})
 for(const name of ['保存截图','取消截图','AI对话','完成并复制截图'])assert.equal(await button(name).evaluate(e=>{const r=e.getBoundingClientRect();return document.elementFromPoint(r.x+r.width/2,r.y+r.height/2)?.closest('button')===e}),true,'Persistent toolbar action must be clickable: '+name)
 console.log('PASS: light multiply highlight preserves text; circular/square continuous brushes; stable opacity; select/Backspace eraser and undo/redo; actual Python inpainting; mask-only repairs; shape cursors and idle state; toolbar without extra menu.')
}finally{await browser.close()}
