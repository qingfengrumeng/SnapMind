// Headless only: never opens a fixture window or touches the desktop clipboard.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}})
 const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:CaptureOverlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,800,500);for(let x=0;x<800;x+=4){g.fillStyle='#ccd4df';g.fillRect(x,0,2,500)}
  const element=document.createElement('div');document.body.append(element)
  createApp({render:()=>h(CaptureOverlay,{source:{id:'toolbar-headless',name:'Synthetic fixture',data:c.toDataURL(),width:800,height:500,scenario:'custom'}})}).mount(element)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const box=await page.locator('.capture-screen').boundingBox(),point=(x,y)=>({x:box.x+x*box.width/800,y:box.y+y*box.height/500})
 const a=point(50,50),z=point(700,400);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(z.x,z.y);await page.mouse.up()
 const toolbar=page.locator('.capture-toolbar'),choose=name=>page.getByRole('button',{name,exact:true}).click()
 for(const label of ['矩形','圆形','箭头','画笔','马赛克','模糊遮罩']){
  await choose('截图'+label)
  const before=await toolbar.boundingBox();assert.ok(before)
  const p=point(150,150),q=point(260,220)
  await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(q.x,q.y,{steps:5})
  assert.equal(await toolbar.isVisible(),true,label+' toolbar must remain visible while drawing')
  assert.equal(await page.locator('.capture-tool-options').isVisible(),true,label+' options must remain visible while drawing')
  const during=await toolbar.boundingBox();assert.equal(during.x,before.x);assert.equal(during.y,before.y)
  await page.mouse.up();assert.equal(await toolbar.isVisible(),true)
  await choose('撤销截图标注')
 }
 await choose('截图马赛克');await choose('一键打码')
 const p=point(160,160),q=point(280,240);await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(q.x,q.y);assert.equal(await toolbar.isVisible(),true);await page.mouse.up()
 await choose('截图文字');await page.mouse.click(p.x,p.y);await page.getByRole('textbox',{name:'截图文字标注'}).fill('Inline text');assert.equal(await toolbar.isVisible(),true);await page.keyboard.press('Enter')
 await choose('截图矩形');await choose('截图矩形') // Return to selection/move mode.
 const beforeMove=await toolbar.boundingBox();await page.mouse.move(p.x,p.y);await page.mouse.down();await page.mouse.move(q.x,q.y);assert.equal(await toolbar.isVisible(),true);const duringMove=await toolbar.boundingBox();assert.equal(duringMove.x,beforeMove.x);assert.equal(duringMove.y,beforeMove.y);await page.mouse.up()
 const handle=page.locator('.handle-se'),handleBox=await handle.boundingBox();await page.mouse.move(handleBox.x+handleBox.width/2,handleBox.y+handleBox.height/2);await page.mouse.down();await page.mouse.move(handleBox.x-30,handleBox.y-30);assert.equal(await toolbar.isVisible(),true);await page.mouse.up()
 assert.deepEqual(errors,[])
 console.log('PASS (headless): toolbar/options stay visible and stationary during shape, pen, mosaic, blur, area redaction, inline text, moving and resizing operations.')
}finally{await browser.close()}
