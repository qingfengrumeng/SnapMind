// Generated pixels and real local region tools. No cloud inference or private capture.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1300,height:1000}}),saved=[],calls=[],errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/tool-fixture',r=>r.fulfill({contentType:'text/html; charset=utf-8',body:'<!doctype html><meta charset="utf-8"><link rel="stylesheet" href="/src/styles.css"><link rel="stylesheet" href="/src/screenshot.css"><link rel="stylesheet" href="/src/image-conversation.css"><div id="fixture" style="height:900px"></div>'}))
 await page.route('**/api/sessions/**',r=>{if(r.request().method()==='PUT')saved.push(r.request().postDataJSON());return r.fulfill({json:r.request().url().endsWith('/image-title')?{title:'Generated region'}:{}})})
 await page.route('**/api/sessions',r=>r.fulfill({json:Array.from(new Map(saved.map(s=>[s.id,s])).values())}))
 await page.route('**/api/tools/call',r=>{calls.push(r.request().postDataJSON());return r.continue()})
 await page.goto('http://127.0.0.1:5174/tool-fixture')
 await page.evaluate(async()=>{
  const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=400;c.height=260;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);g.fillStyle='#804080';g.fillRect(20,30,80,50)
  window.original=c.toDataURL();window.chat=createApp(Chat,{initial:{id:'generated-1',name:'Generated original',data:window.original,width:400,height:260,scenario:'custom'}}).mount('#fixture')
 })
 await page.getByRole('button',{name:'引用 Generated original',exact:true}).waitFor()
 for(const name of ['解释内容','物体识别','AI 标注','二维码／条码','链接与邮箱','理解代码','注释论文','检查作答','表格提取','提取公式','图片笔记','增加截图区域'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0,name+' must be callable without a standalone button')
 const tool=call=>page.evaluate(call=>window.chat.callTool(call),call)
 const region=await tool({name:'region',arguments:{bbox:[20,30,100,80]}})
 assert.equal(region.action,'region');assert.deepEqual([region.payload.width,region.payload.height],[80,50])
 for(let attempt=0;attempt<100&&saved.at(-1)?.imageConversation?.pictures.length!==2;attempt++)await page.waitForTimeout(20)
 const scene=saved.at(-1);assert.equal(scene.imageConversation.pictures.length,2)
 assert.equal(scene.assets.find(a=>a.id==='generated-1').data,await page.evaluate(()=>window.original),'region must retain original pixels')
 assert.ok(scene.imageConversation.selectedId!== 'generated-1')
 await assert.rejects(()=>tool({name:'region',arguments:{bbox:[0,0,999,50]}}))
 assert.equal(saved.at(-1).imageConversation.pictures.length,2,'invalid region must not mutate the conversation')
 for(const name of ['chat','note','explain','code','paper','exam','formula'])await assert.rejects(()=>tool({name,arguments:{prompt:'Removed entry'}}))
 assert.equal(await page.getByRole('button',{name:'保存这份笔记',exact:true}).count(),0)
 assert.equal(saved.at(-1).assets.length,2,'Both region and original remain in the persisted image scene')
 assert.deepEqual(errors,[])
 console.log('PASS: real region tool preserves original pixels, rejects invalid geometry, restores region history and rejects conversation-only tool entries.')
}finally{await browser.close()}
