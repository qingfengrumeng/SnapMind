import {chromium} from 'playwright'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const record=JSON.parse(await readFile('artifacts/ai-callouts-live/results.json','utf8'))
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:900}});let turn=0
 await page.route('**/api/**',route=>{if(new URL(route.request().url()).pathname==='/api/capture/annotate')return route.fulfill({json:record.turns[turn++].result});return route.fulfill({json:{}})})
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async asset=>{const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:asset,initialSelection:true})}).mount(node)},record.asset)
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const button=name=>page.getByRole('button',{name,exact:true}),input=page.getByRole('textbox',{name:'AI 标注指令',exact:true})
 await button('AI 标注').click();await input.fill(record.turns[0].prompt);await button('发送 AI 标注指令').click()
 await page.waitForFunction(()=>document.querySelectorAll('.capture-annotation-message').length===2)
 await input.fill(record.turns[1].prompt);await button('发送 AI 标注指令').click()
 await page.waitForFunction(()=>document.querySelectorAll('.capture-annotation-message').length===4)
 assert.equal(turn,2)
 const head=await page.locator('.capture-annotation-chat header').boundingBox();await page.mouse.move(head.x+80,head.y+20);await page.mouse.down();await page.mouse.move(1000,340,{steps:7});await page.mouse.up()
 await page.screenshot({path:'artifacts/ai-callouts-live/conversation-preview.png'})
 await button('关闭 AI 标注').click();await page.getByLabel('AI 标注对话').waitFor({state:'hidden'});await page.screenshot({path:'artifacts/ai-callouts-live/image-preview.png'})
 console.log('PASS: recorded live annotations and follow-up rendered on the image. No new cloud calls.')
}finally{await browser.close()}
