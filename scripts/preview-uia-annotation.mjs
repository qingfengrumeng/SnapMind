// Render the recorded real-model response; no cloud calls.
import {chromium} from 'playwright'
import {readFile} from 'node:fs/promises'
const root='artifacts/uia-grounding',record=JSON.parse(await readFile(root+'/model-results.json','utf8')),data='data:image/png;base64,'+(await readFile(root+'/fixture.png')).toString('base64')
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1000}})
 await page.route('**/api/**',route=>route.fulfill({json:route.request().url().endsWith('/capture/annotate')?record.result:{}}))
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async({data,width,height})=>{const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:{id:'recorded-uia',name:'Generated UIA fixture',data,width,height,scenario:'custom'},initialSelection:true})}).mount(node)}, {data,width:record.result.width,height:record.result.height})
 await page.locator('.capture-overlay[data-ready="true"]').waitFor()
 await page.getByRole('button',{name:'AI 标注',exact:true}).click()
 await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('圈出 Save 按钮，给 Username 输入框添加简短说明')
 await page.getByRole('button',{name:'发送 AI 标注指令',exact:true}).click()
 await page.getByText(record.result.answer,{exact:true}).waitFor()
 await page.getByRole('button',{name:'关闭 AI 标注',exact:true}).click()
 await page.screenshot({path:root+'/actual-model-preview.png'})
 console.log('PASS: recorded real model UIA annotation rendered without additional model requests.')
}finally{await browser.close()}
