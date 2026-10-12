// Synthetic capture with mocked APIs, no desktop windows or provider calls.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[],requests=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{if(['/api/capture/process','/api/capture/locate'].includes(new URL(route.request().url()).pathname)){requests.push(route);return}return route.fulfill({json:{}})})
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=800;c.height=500;c.getContext('2d').fillRect(0,0,800,500)
  const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:{id:'idle-fixture',name:'Synthetic',data:c.toDataURL(),width:800,height:500,scenario:'custom'}})}).mount(node)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const screen=await page.locator('.capture-screen').boundingBox(),p=(x,y)=>({x:screen.x+x*screen.width/800,y:screen.y+y*screen.height/500}),root=page.locator('.capture-overlay'),crop=page.locator('.capture-selection'),tools=page.locator('.capture-tools-scroll')
 const button=name=>tools.getByRole('button',{name,exact:true}),cursor=()=>root.evaluate(e=>getComputedStyle(e).cursor)
 async function mouse(x,y){const a=p(x,y);await page.mouse.move(a.x,a.y);await page.evaluate(()=>new Promise(requestAnimationFrame))}
 async function drag(x,y,x2,y2){await mouse(x,y);await page.mouse.down();await mouse(x2,y2);await page.mouse.up()}
 await mouse(100,100);assert.equal(await cursor(),'crosshair');await drag(50,50,650,350)
 assert.equal(await tools.locator('button.active').count(),0)
 await mouse(730,430);assert.equal(await cursor(),'default');assert.equal(await page.locator('.capture-loupe').count(),0)
 await mouse(200,200);assert.equal(await cursor(),'grab');assert.equal(await page.locator('.capture-loupe').count(),0)
 const original=await crop.boundingBox();await page.mouse.down();await mouse(240,230);assert.equal(await cursor(),'grabbing');await page.mouse.up();const moved=await crop.boundingBox();assert.ok(moved.x>original.x&&moved.y>original.y)
 const edge=page.locator('.crop-edge-e'),r=await edge.boundingBox();assert.equal(await edge.evaluate(e=>getComputedStyle(e).cursor),'ew-resize');await page.mouse.move(r.x+r.width/2,r.y+r.height/3);await page.mouse.down();await page.mouse.move(r.x+25,r.y+r.height/3);await page.mouse.up();assert.ok((await crop.boundingBox()).width>moved.width)
 for(const name of ['截图矩形','截图圆形','截图箭头','截图画笔','截图马赛克','截图文字','截图模糊遮罩','截图序号','截图移动标注','截图取色']){
  await button(name).click();assert.equal(await tools.locator('button.active').count(),1,name+' activates only the chosen tool')
  await mouse(760,450);assert.equal(await cursor(),'default',name+' must not use a capture cursor outside the crop')
  assert.equal(await page.locator('.mosaic-brush-cursor').count(),0)
  await button(name).click();assert.equal(await tools.locator('button.active').count(),0,name+' toggles back to no tool');assert.equal(await page.locator('.capture-tool-options').count(),0)
  await mouse(240,200);assert.equal(await cursor(),'grab')
 }
 for(const name of ['提取文字','翻译']){
  await button(name).click();await page.locator(name==='翻译'?'.capture-inline-translation-progress':'.capture-process-result').waitFor();assert.equal(await tools.locator('button.active').count(),1)
  await button(name).click();assert.equal(await page.locator('.capture-process-result').count(),0);assert.equal(await tools.locator('button.active').count(),0)
 }
 for(const route of requests)await route.fulfill({json:{text:'obsolete',mode:'model'}}).catch(()=>{})
 await mouse(730,430);assert.equal(await cursor(),'default');assert.deepEqual(errors,[])
 console.log('PASS: initial no-tool state, arrow/grab/grabbing cursors, edge resizing, no idle loupe, toggle off all tools, and cancellation of processing tools. Mocked APIs only.')
}finally{await browser.close()}
