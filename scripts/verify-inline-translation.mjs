// Synthetic two-column screenshots; every API call is mocked.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[],locateRequests=[],translateRequests=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname
  if(path==='/api/capture/locate'){locateRequests.push({route,body:route.request().postDataJSON()});return}
  if(path==='/api/capture/translate-inline'){translateRequests.push({route,body:route.request().postDataJSON()});return}
  return route.fulfill({json:{}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=960;c.height=620;const g=c.getContext('2d');g.fillStyle='#fbf9ff';g.fillRect(0,0,960,620)
  const rows=[['Left title',70,110],['First paragraph',70,190],['Save result',70,270],['Right title',540,110],['Second paragraph',540,190],['Cancel',540,270]]
  g.font='24px Arial';g.fillStyle='#30283f'
  window.fixtureLines=rows.map(([text,x,y],i)=>{const m=g.measureText(text);g.fillText(text,x,y);return {id:'text-'+(i+1),text,bbox:[x-m.actualBoundingBoxLeft-20,y-m.actualBoundingBoxAscent-40,x+m.actualBoundingBoxRight-20,y+m.actualBoundingBoxDescent-40],granularity:'line',page:0,label:'text'}})
  window.original=c.toDataURL();window.exports=[];window.copiedText=''
  Object.defineProperty(navigator,'clipboard',{value:{writeText:async text=>{window.copiedText=text},write:async()=>{}},configurable:true})
  const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:{id:'inline-translation-fixture',name:'Synthetic',data:c.toDataURL(),width:960,height:620,scenario:'custom'},onFinish:result=>window.exports.push(result)})}).mount(node)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const button=name=>page.getByRole('button',{name,exact:true})
 const screen=page.locator('.capture-screen'),bar=page.locator('.capture-toolbar')
 const bounds=await screen.boundingBox(),point=(x,y)=>({x:bounds.x+x*bounds.width/960,y:bounds.y+y*bounds.height/620})
 const a=point(20,40),b=point(920,580);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:4});await page.mouse.up()
 const cropBefore=await page.locator('.capture-selection').boundingBox(),originalPixels=await screen.evaluate(c=>c.toDataURL());let barBefore
 await button('翻译').click()
 await page.getByRole('status').filter({hasText:'正在定位文字'}).waitFor()
 barBefore=await bar.boundingBox()
 assert.equal(await page.locator('.capture-process-result').count(),0)
 assert.equal(await page.locator('.capture-tool-options').count(),0)
 assert.equal(await page.locator('.capture-wait-dots i').count(),3)
 assert.equal(await bar.isVisible(),true)
 assert.equal(locateRequests.length,1);assert.equal(locateRequests[0].body.granularity,'line');assert.equal(locateRequests[0].body.asset.width,900)
 const lines=await page.evaluate(()=>window.fixtureLines)
 await locateRequests[0].route.fulfill({json:{text:'fixture',regions:lines,width:900,height:540,mode:'paddleocr',coordinateSpace:'image-pixels',fallback:false}})
 await page.getByRole('status').filter({hasText:'正在翻译'}).waitFor()
 assert.equal(translateRequests.length,1)
 const translated=['左栏标题','第一段内容','保存结果','右栏标题','第二段内容','取消']
 const reply=(req,texts=translated)=>req.route.fulfill({json:{language:req.body.language,width:900,height:540,coordinateSpace:'image-pixels',lines:req.body.lines.map((line,i)=>({...line,sourceText:line.text,text:texts[i]}))}})
 await reply(translateRequests[0]);await page.getByLabel('截图原位译文').waitFor()
 assert.equal(await page.locator('.capture-translated-line').count(),6)
 assert.notEqual(await screen.evaluate(c=>c.toDataURL()),originalPixels)
 assert.deepEqual(await page.locator('.capture-selection').boundingBox(),cropBefore)
 assert.deepEqual(await bar.boundingBox(),barBefore,'Toolbar stays fixed throughout translation')
 const spans=await page.locator('.capture-translated-line').evaluateAll(items=>items.map(e=>({id:e.dataset.lineId,text:e.textContent,r:e.getBoundingClientRect().toJSON(),whiteSpace:getComputedStyle(e).whiteSpace,userSelect:getComputedStyle(e).userSelect})))
 assert.ok(spans.every(s=>s.whiteSpace==='pre'&&s.userSelect==='text'))
 const left=spans.find(s=>s.id==='text-1'),right=spans.find(s=>s.id==='text-4');assert.ok(right.r.x-left.r.x>500)
 // Real pointer drag selects translated text without moving the capture.
 await page.mouse.move(left.r.x+1,left.r.y+left.r.height/2);await page.mouse.down();await page.mouse.move(left.r.x+left.r.width-1,left.r.y+left.r.height/2,{steps:8});await page.mouse.up()
 const selected=await page.evaluate(()=>window.getSelection().toString());assert.ok(selected.trim().length>0)
 await page.keyboard.press('Control+c');assert.equal(await page.evaluate(()=>window.copiedText),selected)
 assert.deepEqual(await page.locator('.capture-selection').boundingBox(),cropBefore)
 await button('复制全部译文').click();const plain=await page.evaluate(()=>window.copiedText);assert.equal(plain,'左栏标题\t右栏标题\n第一段内容\t第二段内容\n保存结果\t取消')
 await page.keyboard.press('Control+a');await page.keyboard.press('Control+c');assert.equal(await page.evaluate(()=>window.copiedText),plain)
 const translatedPixels=await screen.evaluate(c=>c.toDataURL())
 await button('查看原文').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),originalPixels);assert.equal(await page.locator('.capture-translation-text').count(),0)
 await button('查看译文').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),translatedPixels)
 // Language changes reuse OCR positions, always send the original pixels, and do not open a panel.
 await button('翻译语言').click();await page.getByRole('option',{name:'English',exact:true}).click()
 await page.getByRole('status').filter({hasText:'正在翻译'}).waitFor();assert.equal(locateRequests.length,1);assert.equal(translateRequests.length,2)
 assert.equal(translateRequests[1].body.asset.data,translateRequests[0].body.asset.data);assert.equal(translateRequests[1].body.language,'en')
 await reply(translateRequests[1],['Long translated heading that must fit within the original line','First paragraph translated','Save result','Right heading','Second paragraph translated','Cancel'])
 await page.getByLabel('截图原位译文').waitFor();assert.equal(await page.locator('.capture-process-result').count(),0)
 const long=page.locator('[data-line-id="text-1"]');assert.ok(await long.evaluate(e=>e.scrollWidth<=e.clientWidth+1));assert.ok(await long.evaluate(e=>parseFloat(getComputedStyle(e).fontSize)<15))
 // Failed regeneration clears visual output, retains the original, and allows retry.
 await button('重新翻译').click();await page.getByRole('status').filter({hasText:'正在翻译'}).waitFor()
 assert.equal(await screen.evaluate(c=>c.toDataURL()),originalPixels)
 await translateRequests[2].route.fulfill({status:502,json:{detail:'译文与文字行未能完整对应'}})
 await page.waitForFunction(()=>!document.querySelector('.capture-inline-translation-progress'))
 assert.equal(await page.locator('.capture-process-result').count(),0)
 await button('重新翻译').click();await page.getByRole('status').filter({hasText:'正在翻译'}).waitFor();await reply(translateRequests[3])
 await page.getByLabel('截图原位译文').waitFor()
 // Undo the latest generation, then undo the preceding language change and original translation.
 await button('撤销截图标注').click();assert.equal(await page.locator('.capture-translated-line').count(),6)
 await button('撤销截图标注').click();assert.equal(await page.locator('.capture-translated-line').count(),6)
 await button('撤销截图标注').click();assert.equal(await page.locator('.capture-translation-text').count(),0);assert.equal(await screen.evaluate(c=>c.toDataURL()),originalPixels)
 await button('重新翻译').click();await page.getByRole('status').filter({hasText:'正在翻译'}).waitFor()
 await button('翻译').click();await translateRequests[4].route.fulfill({json:{width:900,height:540,lines:[]}}).catch(()=>{})
 assert.equal(await page.locator('.capture-translation-text').count(),0);assert.equal(await page.locator('.capture-tools-scroll>button.active').count(),0)
 // Final image export contains the translated canvas pixels.
 await button('翻译').click();await page.getByRole('status').filter({hasText:'正在翻译'}).waitFor();await reply(translateRequests[5]);await page.getByLabel('截图原位译文').waitFor()
 await page.screenshot({path:'artifacts/inline-translation.png'})
 await button('完成并复制截图').click();await page.waitForFunction(()=>window.exports.length===1);assert.equal(await page.evaluate(()=>window.exports.length),1)
 assert.equal(await page.evaluate(async()=>{const r=window.exports[0],i=new Image();i.src=r.data;await i.decode();const c=document.createElement('canvas');c.width=i.width;c.height=i.height;c.getContext('2d').drawImage(i,0,0);const expected=document.createElement('canvas');expected.width=900;expected.height=540;expected.getContext('2d').drawImage(document.querySelector('.capture-screen'),20,40,900,540,0,0,900,540);return c.toDataURL()===expected.toDataURL()}),true)
 // Dark backgrounds retain their colors and pixels outside text patches.
 const dark=await page.evaluate(async()=>{const {paintTranslation}=await import('/src/inline-translation.ts'),c=document.createElement('canvas');c.width=220;c.height=100;const g=c.getContext('2d');g.fillStyle='#242428';g.fillRect(0,0,220,100);g.fillStyle='#eee';g.font='20px Arial';g.fillText('Original',20,45);const painted=paintTranslation(c,{lines:[{id:'text-1',text:'译文',sourceText:'Original',bbox:[20,28,94,46]}]});g.drawImage(painted.layer,0,0);return {outside:[...g.getImageData(200,80,1,1).data],padding:[...g.getImageData(19,27,1,1).data],color:painted.lines[0].color}})
 assert.deepEqual(dark.outside,[36,36,40,255]);assert.deepEqual(dark.padding,[36,36,40,255]);assert.ok(dark.color.match(/\d+/g).slice(0,3).every(v=>Number(v)>180))
 assert.deepEqual(errors,[])
 console.log('PASS: no translation panel, OCR line positions, fixed columns/toolbar, native text selection/copy, original view, cached positions, original-image regeneration, fitted text, failure/retry, undo, cancellation and translated image export. Mocked APIs only.')
}finally{await browser.close()}
