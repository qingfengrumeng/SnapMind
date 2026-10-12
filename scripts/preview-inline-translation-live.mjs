// Render recorded synthetic API results. This preview makes no provider calls.
import {chromium} from 'playwright'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const record=JSON.parse(await readFile('artifacts/inline-translation-live/result.json','utf8'))
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname
  return route.fulfill({json:path==='/api/capture/locate'?record.location:path==='/api/capture/translate-inline'?record.translation:{}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async asset=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:asset,initialSelection:true})}).mount(node)
 },record.asset)
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 await page.getByRole('button',{name:'翻译',exact:true}).click();await page.getByLabel('截图原位译文').waitFor()
 assert.equal(await page.locator('.capture-translated-line').count(),6)
 assert.equal(await page.locator('.capture-process-result').count(),0)
 assert.equal(await page.getByRole('button',{name:'完成并复制截图',exact:true}).isVisible(),true)
 await page.screenshot({path:'artifacts/inline-translation-live/translated.png'})
 assert.deepEqual(errors,[])
 console.log('PASS: recorded real OCR/LLM output renders as six selectable translated lines directly on the screenshot; no result panel.')
}finally{await browser.close()}
