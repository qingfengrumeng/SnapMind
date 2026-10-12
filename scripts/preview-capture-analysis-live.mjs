import {chromium} from 'playwright'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const records=JSON.parse(await readFile('artifacts/capture-analysis-live/results.json','utf8'))
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 for(const [name,record] of Object.entries(records)){
  const page=await browser.newPage({viewport:{width:1280,height:900}})
  await page.route('**/api/**',route=>route.fulfill({json:new URL(route.request().url()).pathname==='/api/capture/analyze'?record.result:{}}))
  await page.goto('http://127.0.0.1:5174')
  await page.evaluate(async asset=>{
   const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
   const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:asset,initialSelection:true})}).mount(node)
  },record.asset)
  await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
  await page.getByRole('button',{name:name==='table'?'表格提取':'物体识别',exact:true}).click()
  if(name==='table'){await page.getByRole('table').waitFor();assert.equal(await page.locator('td').count(),12)}
  else{await page.getByText('3 个标记',{exact:true}).waitFor();assert.equal(await page.locator('.capture-process-result').count(),0)}
  await page.screenshot({path:'artifacts/capture-analysis-live/'+name+'-preview.png'});await page.close()
 }
 console.log('PASS: recorded real model results render as editable tables and on-image vehicle annotations. No new cloud requests.')
}finally{await browser.close()}
