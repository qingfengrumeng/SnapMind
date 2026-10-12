// Headless synthetic screenshots and mocked LLM responses only.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[],requests=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{
  if(new URL(route.request().url()).pathname==='/api/capture/process'){requests.push({route,body:route.request().postDataJSON()});return}
  return route.fulfill({json:{}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=1000;c.height=600;const g=c.getContext('2d');g.fillStyle='#252429';g.fillRect(0,0,c.width,c.height);g.fillStyle='#ddd';g.font='24px Arial';g.fillText('Title',70,90);g.fillText('Item    Quantity',70,150);g.fillText('A       2',70,190)
  window.copiedText='';Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copiedText=text}},configurable:true})
  const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:{id:'result-panel-fixture',name:'Synthetic',data:c.toDataURL(),width:1000,height:600,scenario:'custom'}})}).mount(node)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const button=name=>page.getByRole('button',{name,exact:true}),panel=page.locator('.capture-process-result')
 async function drag(x,y,x2,y2){const box=await page.locator('.capture-screen').boundingBox(),p=(x,y)=>({x:box.x+x*box.width/1000,y:box.y+y*box.height/600}),a=p(x,y),z=p(x2,y2);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(z.x,z.y,{steps:4});await page.mouse.up()}
 async function requestAfter(click){const count=requests.length;await click();await page.waitForFunction(()=>document.querySelector('.capture-process-result')?.getAttribute('aria-busy')==='true');for(let n=0;n<100&&requests.length===count;n++)await page.waitForTimeout(10);assert.equal(requests.length,count+1);assert.equal(requests.at(-1).body.engine,'multimodal');return requests.at(-1)}
 async function reply(request,text){await request.route.fulfill({json:{text,mode:'model',model:'DeepSeek fixture'}});await page.waitForFunction(()=>document.querySelector('.capture-process-result')?.getAttribute('aria-busy')==='false')}
 const original='Title\n\n  Indented line\nItem\tQuantity\nA\t2\n'
 await drag(50,60,450,340)
 let request=await requestAfter(()=>button('提取文字').click());assert.equal(request.body.action,'ocr');assert.equal(request.body.asset.width,400)
 assert.equal(await page.locator('.capture-tool-options').count(),0,'No extra action options below the toolbar')
 assert.equal(await page.locator('.capture-wait-dots i').count(),3)
 assert.ok(await page.locator('.capture-wait-dots i').first().evaluate(e=>getComputedStyle(e).animationName.includes('capture-wait-bounce')))
 let crop=await page.locator('.capture-selection').boundingBox(),bounds=await panel.boundingBox(),bar=await page.locator('.capture-toolbar').boundingBox()
 assert.ok(bounds.x>=crop.x+crop.width,'Panel uses the right side when there is room');assert.ok(bounds.y+bounds.height<=bar.y,'Panel avoids the fixed toolbar')
 const cropBefore={...crop},header=panel.locator('header'),headerBounds=await header.boundingBox()
 await page.mouse.move(headerBounds.x+80,headerBounds.y+20);await page.mouse.down();await page.mouse.move(crop.x+110,crop.y+40,{steps:5});await page.mouse.up()
 let moved=await panel.boundingBox();assert.ok(moved.x<crop.x+crop.width&&moved.x+moved.width>crop.x,'Panel can be dragged over the screenshot')
 assert.deepEqual(await page.locator('.capture-selection').boundingBox(),cropBefore,'Dragging the panel must not move the crop')
 assert.equal(await page.locator('.capture-toolbar').isVisible(),true)
 await page.screenshot({path:'artifacts/capture-result-loading.png'})
 await reply(request,original);assert.equal(await page.getByRole('textbox',{name:'处理结果'}).inputValue(),original)
 assert.deepEqual(await panel.boundingBox(),moved,'Completion must preserve the user-adjusted position')
 assert.equal(await page.getByRole('textbox',{name:'处理结果'}).getAttribute('wrap'),'soft')
 async function resize(edge,dx,dy){const handle=panel.locator('.resize-'+edge),r=await handle.boundingBox();await page.mouse.move(r.x+r.width/2,r.y+r.height/2);await page.mouse.down();await page.mouse.move(r.x+r.width/2+dx,r.y+r.height/2+dy,{steps:4});await page.mouse.up();return panel.boundingBox()}
 const textArea=page.getByRole('textbox',{name:'处理结果'}),textBefore=await textArea.boundingBox()
 let resized=await resize('e',100,0);assert.ok(Math.abs(resized.width-moved.width-100)<1&&resized.x===moved.x)
 resized=await resize('s',0,60);assert.ok(Math.abs(resized.height-moved.height-60)<1&&resized.y===moved.y)
 assert.ok((await textArea.boundingBox()).width>textBefore.width&&(await textArea.boundingBox()).height>textBefore.height,'Content grows with the panel')
 const beforeWest={...resized};resized=await resize('w',-30,0);assert.ok(Math.abs(resized.x-beforeWest.x+30)<1&&Math.abs(resized.width-beforeWest.width-30)<1)
 const beforeNorth={...resized};resized=await resize('n',0,-30);assert.ok(Math.abs(resized.y-beforeNorth.y+30)<1&&Math.abs(resized.height-beforeNorth.height-30)<1)
 const beforeCorner={...resized};resized=await resize('se',-80,-40);assert.ok(Math.abs(resized.width-beforeCorner.width+80)<1&&Math.abs(resized.height-beforeCorner.height+40)<1)
 assert.equal(await textArea.inputValue(),original,'Adaptive wrapping must not change the original text')
 assert.deepEqual(await page.locator('.capture-selection').boundingBox(),cropBefore,'Panel resizing must not affect the screenshot')
 // Enforce a usable minimum, then restore a comfortable size for subsequent actions.
 resized=await resize('se',-1500,-1500);assert.ok(resized.width>=280&&resized.height>=220)
 moved=await resize('se',100,100)
 await button('复制结果').click();assert.equal(await page.evaluate(()=>window.copiedText),original)
 assert.equal(await button('返回截图').count(),0)
 request=await requestAfter(()=>button('重新生成').click());assert.equal(request.body.action,'ocr');assert.equal(await page.getByRole('textbox',{name:'处理结果'}).count(),0,'Regeneration clears the old content and shows the waiting state');assert.equal(await page.locator('.capture-wait-dots i').count(),3);assert.deepEqual(await panel.boundingBox(),moved);await reply(request,'New transcription\n')
 request=await requestAfter(()=>button('解释').click());assert.equal(request.body.action,'explain');assert.deepEqual(await panel.boundingBox(),moved,'Switching panel actions preserves the dragged position');await reply(request,original)
 await button('输出语言').click();request=await requestAfter(()=>page.getByRole('option',{name:'English',exact:true}).click());assert.equal(request.body.language,'en');await reply(request,'Explanation\n\n  A\t2\n')
 assert.equal(await page.locator('.capture-tool-options').count(),0)
 request=await requestAfter(()=>button('重新生成').click());assert.equal(request.body.action,'explain');await reply(request,'Explanation\n\n  Item\tMeaning\n')
 const secondHeader=await header.boundingBox();await page.mouse.move(secondHeader.x+80,secondHeader.y+20);await page.mouse.down();await page.mouse.move(-200,-200,{steps:5});await page.mouse.up();bounds=await panel.boundingBox();assert.ok(bounds.x>=0&&bounds.y>=0,'Panel remains reachable when dragged beyond the viewport')
 await page.keyboard.press('Escape');assert.equal(await panel.count(),0);assert.equal(await page.locator('.capture-selection').count(),1)
 // Left-side placement and cancellation of an in-flight action.
 await drag(550,50,950,330);request=await requestAfter(()=>button('提取文字').click());crop=await page.locator('.capture-selection').boundingBox();bounds=await panel.boundingBox();assert.ok(bounds.x+bounds.width<=crop.x)
 await button('关闭处理结果').click();await request.route.fulfill({json:{text:'obsolete',mode:'model'}}).catch(()=>{});assert.equal(await panel.count(),0)
 // Top placement when neither horizontal side fits.
 await drag(100,340,950,570);request=await requestAfter(()=>button('提取文字').click());crop=await page.locator('.capture-selection').boundingBox();bounds=await panel.boundingBox();assert.ok(bounds.y+bounds.height<=crop.y)
 await request.route.fulfill({status:400,json:{detail:'模型未启用图片输入'}});await page.getByRole('alert').filter({hasText:'模型未启用图片输入'}).waitFor()
 request=await requestAfter(()=>button('重新生成').click());await reply(request,original)
 await page.screenshot({path:'artifacts/capture-result-text.png'})
 await page.setViewportSize({width:390,height:600});bounds=await panel.boundingBox();assert.ok(bounds.x>=0&&bounds.y>=0&&bounds.x+bounds.width<=390&&bounds.y+bounds.height<=600)
 await button('关闭处理结果').click();request=await requestAfter(()=>page.keyboard.press('l'));assert.equal(request.body.action,'ocr');await reply(request,original)
 assert.deepEqual(errors,[])
 console.log('PASS: draggable and resizable panels, four edges/corner, minimum sizes, adaptive content without text changes, position/size persistence, viewport bounds, processing, cancellation, copy, retry and shortcuts. Mocked APIs only.')
}finally{await browser.close()}
