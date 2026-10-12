// Generated pixels and mocked API only; no user files, microphone or cloud calls.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true}),rows=[],calls=[]
try{
 const page=await browser.newPage({viewport:{width:1600,height:1000}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname
  calls.push(path)
  if(path==='/api/image-history')return route.fulfill({json:[]})
  if(path==='/api/capture/process'){await new Promise(r=>setTimeout(r,600));return route.fulfill({json:{text:'Generated OCR result'}}).catch(()=>{})}
  await route.fulfill({json:{tools:[],items:[],profiles:[],activeId:null}})
 })
 await page.route('**/response-fixture',route=>route.fulfill({contentType:'text/html',body:'<link rel="stylesheet" href="/src/styles.css"><link rel="stylesheet" href="/src/screenshot.css"><link rel="stylesheet" href="/src/image-conversation.css"><div id="fixture"></div>'}))
 await page.goto('http://127.0.0.1:5174/response-fixture')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const canvas=document.createElement('canvas');canvas.width=2560;canvas.height=1440
  const g=canvas.getContext('2d'),gradient=g.createLinearGradient(0,0,2560,1440);gradient.addColorStop(0,'#faf6ff');gradient.addColorStop(1,'#c7b3ee');g.fillStyle=gradient;g.fillRect(0,0,2560,1440);g.fillStyle='#453057';g.font='28px Arial';for(let y=60;y<1440;y+=60)g.fillText('Generated screenshot response benchmark',50,y)
  window.fixtureApp=createApp({render:()=>h(Overlay,{source:{id:'response-generated',name:'Generated',data:canvas.toDataURL(),width:2560,height:1440,scenario:'custom'},initialSelection:true})});window.fixtureApp.mount('#fixture')
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 for(const id of ['rect','ellipse','arrow','pen','text','mosaic','blur','highlight','heal']){
  const samples=[]
  for(let n=0;n<3;n++){
   if(n)await page.locator(`[data-capture-tool="${id}"]`).click()
   const sample=await page.evaluate(async id=>{const button=document.querySelector(`[data-capture-tool="${id}"]`),start=performance.now();button.click();await new Promise(r=>requestAnimationFrame(()=>setTimeout(r,0)));return {ms:performance.now()-start,active:button.classList.contains('active'),options:!!document.querySelector('.capture-tool-options')}},id)
   assert.equal(sample.active,true);assert.equal(sample.options,true);samples.push(Math.round(sample.ms*10)/10)
  }
  rows.push({button:id,firstFeedbackMs:samples,medianMs:[...samples].sort((a,b)=>a-b)[1]})
 }
 const ocr=await page.evaluate(async()=>{const start=performance.now();document.querySelector('[data-capture-tool="ocr"]').click();await new Promise(r=>requestAnimationFrame(()=>setTimeout(r,0)));return {ms:performance.now()-start,loading:document.querySelector('.capture-process-result')?.getAttribute('aria-busy')==='true'}})
 assert.equal(ocr.loading,true);rows.push({button:'ocr-loading',firstFeedbackMs:Math.round(ocr.ms*10)/10,providerDelayMs:600})
 await page.getByRole('button',{name:'关闭处理结果',exact:true}).click()
 const chat=await page.evaluate(async()=>{const start=performance.now();document.querySelector('[data-capture-tool="chat"]').click();await new Promise(r=>requestAnimationFrame(()=>setTimeout(r,0)));return {ms:performance.now()-start,feedback:!!document.querySelector('.capture-panel-preparing,.image-conversation')}})
 assert.equal(chat.feedback,true);await page.locator('.image-conversation').waitFor();rows.push({button:'chat-opening',firstFeedbackMs:Math.round(chat.ms*10)/10})
 await page.getByRole('button',{name:'关闭截图对话',exact:true}).click()
 for(const id of ['chat','voiceCall']){
  await page.evaluate(id=>{const b=document.querySelector(`[data-capture-tool="${id}"]`);b.click();b.click()},id)
  await page.waitForTimeout(100);assert.equal(await page.locator('.capture-panel-preparing,.image-conversation,.voice-spirit').count(),0,'Cancelled preparation must not reopen a panel')
 }
 const before=calls.filter(p=>p==='/api/capture/process').length
 await page.evaluate(()=>{const b=document.querySelector('[data-capture-tool="ocr"]');b.click();b.click()})
 await page.waitForTimeout(100);assert.equal(calls.filter(p=>p==='/api/capture/process').length,before,'Cancel before encoding finishes must suppress the request')
 const history=await page.evaluate(async()=>{
  window.fixtureApp.unmount()
  const [{default:History},{createApp,h}]=await Promise.all([import('/src/components/ImageConversationHistory.vue'),import('/node_modules/.vite/deps/vue.js')])
  const ready=new Promise(resolve=>window.releaseHistory=resolve),start=performance.now()
  window.fixtureApp=createApp({render:()=>h(History,{ready})});window.fixtureApp.mount('#fixture')
  await new Promise(r=>requestAnimationFrame(()=>setTimeout(r,0)));return {ms:performance.now()-start,visible:!!document.querySelector('.image-history'),loading:document.querySelector('.history-empty')?.textContent||document.querySelector('.image-history')?.textContent}
 })
 assert.equal(history.visible,true);assert.match(history.loading,/正在读取/);rows.push({button:'history-pending-save',firstFeedbackMs:Math.round(history.ms*10)/10,saveStillPending:true})
 await page.evaluate(()=>window.releaseHistory());await page.waitForFunction(()=>!document.querySelector('.image-history')?.textContent.includes('正在读取会话'))
 assert.deepEqual(errors,[])
 await mkdir('artifacts/ui-response',{recursive:true});await writeFile('artifacts/ui-response/results.json',JSON.stringify({resolution:[2560,1440],fixture:'generated / mocked',rows,rapidCancellation:'PASS'},null,2));console.log(JSON.stringify(rows))
}finally{await browser.close()}
