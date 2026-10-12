// Real screenshot canvas, generated image and controlled multi-step tool output.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1400,height:950}}),pending=[],errors=[]
 page.on('pageerror',error=>errors.push(error.message))
 await page.route('**/api/**',route=>{
  const path=new URL(route.request().url()).pathname
  if(path==='/api/capture/conversation'){pending.push(route);return}
  return route.fulfill({json:path==='/api/image-history'?[]:{tools:[],items:[]}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const c=document.createElement('canvas');c.width=800;c.height=400;const g=c.getContext('2d');g.fillStyle='white';g.fillRect(0,0,800,400);g.fillStyle='black';g.fillRect(100,100,180,30);g.fillRect(100,220,240,30)
  window.sourcePng=c.toDataURL();g.fillStyle='white';g.fillRect(100,100,180,30);window.firstEdit=c.toDataURL();g.fillRect(100,220,240,30);window.finalEdit=c.toDataURL()
  const host=document.createElement('div');document.body.append(host);window.editOverlay=createApp(Overlay,{source:{id:'generated-edits',name:'Synthetic screenshot',data:sourcePng,width:800,height:400,scenario:'custom'},initialSelection:true});editOverlay.mount(host)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true');await page.getByRole('button',{name:'AI对话',exact:true}).click()
 await page.getByRole('textbox',{name:'图片对话输入'}).fill('涂抹掉截图中的全部文字');await page.getByRole('button',{name:'发送图片对话',exact:true}).click()
 while(!pending.length)await page.waitForTimeout(20)
 const request=pending[0].request().postDataJSON(),pictures=await page.evaluate(()=>({first:firstEdit,last:finalEdit}))
 const step=data=>({action:'heal',assetId:request.selectedId,answer:'已完成文字消除，可撤销。',payload:{data,width:800,height:400}})
 await pending[0].fulfill({json:{...step(pictures.last),steps:[step(pictures.first),step(pictures.last)]}})
 await page.getByText('已完成文字消除，可撤销。',{exact:true}).waitFor()
 const values=await page.locator('.capture-screen').evaluate(c=>{const g=c.getContext('2d');return [[150,115],[150,235]].map(([x,y])=>Array.from(g.getImageData(x,y,1,1).data))})
 assert.deepEqual(values,[[255,255,255,255],[255,255,255,255]],'Both tool results must reach the actual screenshot before completion feedback')
 const cards=page.getByRole('navigation',{name:'下一步操作示例'});await cards.waitFor();assert.equal(await cards.locator('button').count(),3);assert.ok((await cards.locator('button').first().boundingBox()).height<50)
 await mkdir('artifacts/conversation-edits',{recursive:true});await page.screenshot({path:'artifacts/conversation-edits/applied.png'})
 await page.evaluate(()=>editOverlay.unmount());assert.deepEqual(errors,[])
 console.log('PASS: sequential multi-step erasure applied to actual screenshot pixels before completion; compact latest-reply cards. Generated screenshot and controlled services only.')
}finally{await browser.close()}
