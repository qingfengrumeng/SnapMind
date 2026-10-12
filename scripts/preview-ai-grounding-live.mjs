import {chromium} from 'playwright'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const root='artifacts/ai-annotation-grounding'
const record=JSON.parse(await readFile(`${root}/results.json`,'utf8'))
assert.equal(record.passed,true)
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:900}});let turn=0
 await page.route('**/api/**',route=>new URL(route.request().url()).pathname==='/api/capture/annotate'?route.fulfill({json:record.turns[turn++].result}):route.fulfill({json:{}}))
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async asset=>{const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:asset,initialSelection:true})}).mount(node)},record.asset)
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const button=name=>page.getByRole('button',{name,exact:true}),input=page.getByRole('textbox',{name:'AI 标注指令',exact:true}),canvas=page.locator('.capture-screen')
 const original=await canvas.evaluate(c=>c.toDataURL())
 for(let i=0;i<record.turns.length;i++){
  if(i===0)await button('AI 标注').click()
  await input.fill(record.turns[i].prompt);await button('发送 AI 标注指令').click()
  await page.waitForFunction(count=>document.querySelectorAll('.capture-annotation-message').length===count,(i+1)*2)
  if(i===0)assert.equal(await canvas.evaluate(c=>c.toDataURL()),original)
  else assert.notEqual(await canvas.evaluate(c=>c.toDataURL()),original)
  if(i===1){
   const unchanged=await canvas.evaluate(async(c,{asset,bbox})=>{
    const img=new Image();img.src=asset.data;await img.decode()
    const source=document.createElement('canvas');source.width=asset.width;source.height=asset.height;source.getContext('2d').drawImage(img,0,0)
    const [l,t,r,b]=bbox,a=source.getContext('2d').getImageData(l,t,r-l,b-t).data,actual=c.getContext('2d').getImageData(l,t,r-l,b-t).data
    return a.every((v,index)=>v===actual[index])
   },{asset:record.asset,bbox:record.groundTruth[1].bbox})
   assert.equal(unchanged,true,'Text framing must leave all source text pixels unchanged')
  }
  // Move the chat beside the screenshot for comparison.
  const header=await page.locator('.capture-annotation-chat header').boundingBox()
  await page.mouse.move(header.x+80,header.y+20);await page.mouse.down();await page.mouse.move(1170,160,{steps:5});await page.mouse.up()
  await page.screenshot({path:`${root}/${['no-object','text-line','callout'][i]}-preview.png`})
 }
 assert.equal(turn,3)
 console.log('PASS: recorded live text-only result paints nothing; selected OCR line and follow-up bubble render on the image. No new cloud calls.')
}finally{await browser.close()}
