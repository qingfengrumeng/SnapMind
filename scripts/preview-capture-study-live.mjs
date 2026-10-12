import {chromium} from 'playwright'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const root='artifacts/capture-study-live',record=JSON.parse(await readFile(`${root}/results.json`,'utf8'))
assert.equal(record.passed,true)
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1000}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{
  if(new URL(route.request().url()).pathname!=='/api/capture/study')return route.fulfill({json:{}})
  const body=route.request().postDataJSON(),source=body.mode==='code'?record.turns[0].result:body.prompt.includes('练习')?record.turns[2].result:record.turns[1].result
  const originals=body.mode==='code'?[record.codeAsset]:record.paperAssets
  const ids=new Map(originals.map((a,i)=>[a.id,body.assets[i]?.id]))
  const result={...source,answer:body.mode==='paper'&&body.assets.length===1?source.answer.split('\n\n')[0]:source.answer,
   notes:source.notes.filter(n=>ids.get(n.pageId)).map(n=>({...n,pageId:ids.get(n.pageId)})),
   pages:body.assets.map((a,i)=>({...source.pages[i],id:a.id,name:a.name}))}
  return route.fulfill({json:result})
 })
 await page.goto('http://127.0.0.1:5174')
 async function mount(asset){await page.evaluate(async asset=>{window.studyApp?.unmount();document.querySelector('#study-fixture-mount')?.remove();const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const node=document.createElement('div');node.id='study-fixture-mount';document.body.append(node);window.studyApp=createApp({render:()=>h(Overlay,{source:asset,initialSelection:true})});window.studyApp.mount(node)},asset);await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')}
 const button=name=>page.getByRole('button',{name,exact:true}),panel=page.locator('.capture-study-panel')
 async function done(){await page.waitForFunction(()=>document.querySelector('.capture-study-content')?.getAttribute('aria-busy')==='false')}
 async function position(){const head=await panel.locator('header').boundingBox();await page.mouse.move(head.x+70,head.y+18);await page.mouse.down();await page.mouse.move(1110,155,{steps:6});await page.mouse.up();const handle=await button('调整学习面板 se').boundingBox();await page.mouse.move(handle.x+4,handle.y+4);await page.mouse.down();await page.mouse.move(handle.x+65,handle.y+190,{steps:6});await page.mouse.up()}
 await mount(record.codeAsset);await button('理解代码').click();await done();await position()
 assert.equal(await page.locator('.capture-study-notes button').count(),6)
 await page.locator('.capture-study-notes button').filter({hasText:'第 45 行'}).click();await page.getByLabel('当前解释对应的原文').waitFor();await page.screenshot({path:`${root}/code-preview.png`})
 await mount(record.paperAssets[0]);await button('注释论文').click();await done()
 const second=record.paperAssets[1];await page.getByLabel('选择论文或试卷页面',{exact:true}).setInputFiles({name:'second-exam.png',mimeType:'image/png',buffer:Buffer.from(second.data.split(',')[1],'base64')})
 await button('查看第 2 页').waitFor();await button('比较多页').click();await done();await position();await page.screenshot({path:`${root}/paper-comparison-preview.png`})
 await button('查看第 2 页').click();await page.locator('.capture-study-notes button').click();await page.screenshot({path:`${root}/second-page-preview.png`})
 await button('针对性练习').click();await done();assert.ok(await panel.locator('.katex').count()>0);await page.screenshot({path:`${root}/practice-preview.png`})
 assert.deepEqual(errors,[])
 console.log('PASS: live code lines, on-image notes, two-page evidence and annotations, practice formulas rendered. Recorded results only; no new cloud calls.')
}finally{await browser.close()}
