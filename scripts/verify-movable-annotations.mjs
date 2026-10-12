// Headless synthetic capture only. No desktop windows, user settings or provider calls.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>route.fulfill({json:{}}))
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#252429';g.fillRect(0,0,800,500);for(let x=600;x<680;x+=2){g.fillStyle='#ffffff';g.fillRect(x,0,1,500)}
  window.annotationResult=null;const node=document.createElement('div');document.body.append(node)
  createApp({render:()=>h(Overlay,{source:{id:'move-fixture',name:'Synthetic',data:c.toDataURL(),width:800,height:500,scenario:'custom'},initialSelection:true,onFinish:result=>window.annotationResult=result})}).mount(node)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const box=await page.locator('.capture-screen').boundingBox(),scale=box.width/800,point=(x,y)=>({x:box.x+x*scale,y:box.y+y*scale})
 const button=name=>page.getByRole('button',{name,exact:true})
 const pixels=(x,y,w=1,h=1)=>page.locator('.capture-screen').evaluate((c,r)=>Array.from(c.getContext('2d').getImageData(r.x,r.y,r.w,r.h).data),{x,y,w,h})
 const pixel=(x,y)=>pixels(x,y)
 async function drag(x,y,x2,y2){const a=point(x,y),z=point(x2,y2);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(z.x,z.y,{steps:5});assert.equal(await page.locator('.capture-toolbar').isVisible(),true);await page.mouse.up()}
 async function click(x,y){const p=point(x,y);await page.mouse.click(p.x,p.y)}
 const background=await pixel(100,100)
 await button('截图矩形').click();await drag(100,100,220,180);const red=await pixel(100,120);assert.notDeepEqual(red,background)
 await button('截图移动标注').click();await drag(100,120,160,160)
 assert.deepEqual(await pixel(100,120),background,'Moving a frame restores source pixels')
 assert.deepEqual(await pixel(160,160),red,'Frame appears at its new position')
 assert.equal(await page.locator('.capture-mark-selection').count(),1)
 await button('撤销截图标注').click();assert.deepEqual(await pixel(100,120),red);assert.deepEqual(await pixel(160,160),background)
 // New overlapping object must move first, without removing the older frame.
 await button('截图序号').click();await click(100,120);const numbered=await pixels(96,116,8,8)
 await button('截图移动标注').click();await drag(100,120,350,120)
 assert.deepEqual(await pixel(100,120),red,'Older frame is preserved below the moved number')
 assert.deepEqual(await pixels(346,116,8,8),numbered)
 await button('截图箭头').click();await drag(300,220,420,250);const arrow=await pixels(294,214,134,45)
 await button('截图移动标注').click();await drag(350,232,390,312);assert.deepEqual(await pixels(334,294,134,45),arrow)
 await button('截图圆形').click();await drag(450,100,550,160);const ellipse=await pixels(446,96,108,68)
 await button('截图移动标注').click();await drag(500,100,500,210);assert.deepEqual(await pixels(446,206,108,68),ellipse)
 await button('截图画笔').click();await drag(50,280,130,300);const pen=await pixels(46,276,88,28)
 await button('截图移动标注').click();await drag(90,290,130,370);assert.deepEqual(await pixels(86,356,88,28),pen)
 await button('截图文字').click();await click(200,320);await page.getByRole('textbox',{name:'截图文字标注'}).fill('Move text');await page.keyboard.press('Enter');const text=await pixels(200,320,90,40)
 await button('截图移动标注').click();await drag(210,330,240,410);assert.deepEqual(await pixels(230,400,90,40),text)
 // Region redaction and blurred masks stay fixed in move mode.
 await button('截图马赛克').click();await button('一键打码').click();await drag(600,100,680,180);const mosaic=await pixels(610,110,20,20)
 await button('截图移动标注').click();await drag(620,140,700,250);assert.deepEqual(await pixels(610,110,20,20),mosaic);assert.equal(await page.locator('.capture-mark-selection').count(),0)
 await button('截图模糊遮罩').click();await drag(600,250,670,320);const blurred=await pixels(610,260,20,20)
 await button('截图移动标注').click();await drag(620,280,700,350);assert.deepEqual(await pixels(610,260,20,20),blurred)
 // Deletion is independent and can be undone.
 await click(350,120);await page.keyboard.press('Backspace');assert.deepEqual(await pixel(350,120),background);await page.keyboard.press('Control+z');assert.deepEqual(await pixels(346,116,8,8),numbered)
 // Clamp a moved frame to the crop instead of losing it outside the image.
 await drag(100,160,-200,160);const bounds=await page.locator('.capture-mark-selection').boundingBox();assert.ok(bounds.x>=box.x-4)
 await page.screenshot({path:'artifacts/movable-annotations.png'})
 const final=await pixels(0,0,800,500);await button('完成并复制截图').click();await page.waitForFunction(()=>window.annotationResult)
 const exported=await page.evaluate(async()=>{const result=window.annotationResult,img=new Image();img.src=result.data;await img.decode();const c=document.createElement('canvas');c.width=img.width;c.height=img.height;c.getContext('2d').drawImage(img,0,0);return Array.from(c.getContext('2d').getImageData(0,0,img.width,img.height).data)})
 assert.deepEqual(exported,final,'Export uses the edited image without selection decorations')
 assert.deepEqual(errors,[])
 console.log('PASS: frames, ellipse, arrow, pen, sequence and text move; overlapping objects, fixed redaction/blur, crop bounds, delete/undo, fixed toolbar and exported pixels. Synthetic image only.')
}finally{await browser.close()}
