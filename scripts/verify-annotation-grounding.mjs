import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1000}}),requests=[]
 await page.route('**/api/**',route=>{if(route.request().url().endsWith('/capture/annotate')){requests.push(route);return}return route.fulfill({json:{}})})
 await page.goto('http://127.0.0.1:5174')
 const result=await page.evaluate(async()=>{
  const {captureControls}=await import('/src/capture-controls.ts')
  const bounds={x:100,y:50,w:200,h:120},control={id:'control-1',text:'Save',controlType:'Button',bbox:[10,10,95,45]},reader=async(id,rect)=>{if(id!=='frame')throw Error('wrong frame');return [control]}
  return {
   valid:await captureControls('frame',bounds,[],reader),
   outside:await captureControls('frame',bounds,[{x:300,y:100,w:20,h:20}],reader),
   redacted:await captureControls('frame',bounds,[{x:120,y:70,w:10,h:10}],reader),
   failed:await captureControls('wrong-frame',bounds,[],reader),
   fractional:await captureControls('frame',{...bounds,x:100.5,y:50.25},[],reader),
  }
 })
 assert.equal(result.valid.length,1);assert.deepEqual(result.valid,result.outside);assert.deepEqual(result.redacted,[]);assert.deepEqual(result.failed,[]);assert.deepEqual(result.fractional[0].bbox,[9.5,9.75,94.5,44.75])
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=640;c.height=420;const g=c.getContext('2d');g.fillStyle='#fcfaff';g.fillRect(0,0,640,420);g.fillStyle='#efe6ff';g.fillRect(60,70,180,60);g.fillStyle='#4e3969';g.font='24px Segoe UI';g.fillText('Save',115,108)
  const node=document.createElement('div');document.body.append(node);window.uiaExports=[];createApp({render:()=>h(Overlay,{source:{id:'uia-paint',name:'Generated buttons',data:c.toDataURL(),width:640,height:420,scenario:'custom'},initialSelection:true,onFinish:value=>window.uiaExports.push(value)})}).mount(node)
 })
 await page.locator('.capture-overlay[data-ready="true"]').waitFor();const screen=page.locator('.capture-screen'),original=await screen.evaluate(c=>c.toDataURL())
 const button=name=>page.getByRole('button',{name,exact:true})
 await button('AI 标注').click();await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('圈出保存按钮');await button('发送 AI 标注指令').click()
 await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor()
 await requests[0].fulfill({json:{answer:'已使用真实控件边界。',annotations:[{operation:'add',kind:'circle',text:'',bbox:[60,70,240,130],locationSource:'uia'}],width:640,height:420,coordinateSpace:'image-pixels',approximate:false}})
 await page.getByText('已使用真实控件边界。',{exact:true}).waitFor();assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original)
 assert.equal(await page.locator('.capture-overlay').evaluate(e=>e.style.cursor),'default');assert.equal(await page.locator('.capture-toolbar').isVisible(),true)
 // A UI control is outlined outside its full box, without striking through its label.
 const unchanged=await screen.evaluate(c=>{const image=new Image();image.src=window.uiaSource||'';return c.getContext('2d').getImageData(80,95,10,10).data.every((v,i)=>i%4===3?v===255:i%4===0?v===239:i%4===1?v===230:v===255)})
 assert.ok(unchanged)
 await mkdir('artifacts/uia-grounding',{recursive:true});await page.screenshot({path:'artifacts/uia-grounding/annotation.png'})
 await button('关闭 AI 标注').click();await button('完成并复制截图').click();await page.waitForFunction(()=>window.uiaExports.length===1)
 assert.ok(await page.evaluate(()=>window.uiaExports[0].data!==''))
 console.log('PASS: native control payload filtering, fractional coordinates, redaction/failure fallback, UIA outline, persistent toolbar and export.')
}finally{await browser.close()}
