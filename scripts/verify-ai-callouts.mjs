import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1480,height:1050}}),requests=[],errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{if(new URL(route.request().url()).pathname==='/api/capture/annotate'){requests.push({route,body:route.request().postDataJSON()});return}return route.fulfill({json:{}})})
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=960;c.height=620;const g=c.getContext('2d');g.fillStyle='#fcfaff';g.fillRect(0,0,960,620)
  g.fillStyle='#dfd0f7';g.fillRect(100,100,180,120);g.fillStyle='#bdd4f9';g.fillRect(500,100,300,170);g.fillStyle='#b6e3c8';g.fillRect(600,350,150,150)
  g.fillStyle='#58436f';g.font='22px Segoe UI';g.fillText('Settings',120,165);g.fillText('Video preview',540,190);g.fillText('Save',640,440)
  window.exports=[];Object.defineProperty(navigator,'clipboard',{value:{write:async()=>{},writeText:async()=>{}},configurable:true})
  const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:{id:'callout-fixture',name:'Synthetic',data:c.toDataURL(),width:960,height:620,scenario:'custom'},initialSelection:true,onFinish:value=>window.exports.push(value)})}).mount(node)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const button=name=>page.getByRole('button',{name,exact:true}),screen=page.locator('.capture-screen'),bar=page.locator('.capture-toolbar'),pixel=(x,y)=>screen.evaluate((c,p)=>Array.from(c.getContext('2d').getImageData(p.x,p.y,1,1).data),{x,y})
 const original=await screen.evaluate(c=>c.toDataURL()),cropBefore=await page.locator('.capture-selection').boundingBox()
 await button('AI 标注').click();await page.getByLabel('AI 标注对话').waitFor();assert.equal(await page.locator('.capture-tool-options').count(),0)
 await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('左侧加简短气泡，圈出视频，并给保存打勾');await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).press('Enter')
 await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor();const toolbarBefore=await bar.boundingBox()
 assert.equal(await page.locator('.capture-wait-dots i').count(),3);assert.equal(requests[0].body.history.length,0)
 const annotations=[{operation:'add',kind:'callout',text:'设置入口',bbox:[100,100,280,220]},{operation:'add',kind:'circle',text:'',bbox:[500,100,800,270]},{operation:'add',kind:'check',text:'',bbox:[600,350,750,500]}]
 const reply=(req,edits,answer)=>req.route.fulfill({json:{annotations:edits,answer,width:960,height:620,coordinateSpace:'image-pixels',approximate:true}})
 await reply(requests[0],annotations,'已添加 3 个标注。');await page.getByText('已添加 3 个标注。',{exact:true}).waitFor()
 assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original);assert.deepEqual(await page.locator('.capture-selection').boundingBox(),cropBefore);assert.deepEqual(await bar.boundingBox(),toolbarBefore)
 assert.equal(await page.locator('.capture-overlay').evaluate(e=>e.style.cursor),'default')
 // Follow-up references previous marks and conversation; raw input excludes generated annotations.
 await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('把气泡改成配置，删除圈线');await button('发送 AI 标注指令').click();await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor()
 assert.equal(requests[1].body.asset.data,requests[0].body.asset.data);assert.equal(requests[1].body.history.length,2);assert.equal(requests[1].body.existing.length,3)
 const [bubble,circle,check]=requests[1].body.existing
 await reply(requests[1],[{operation:'update',id:bubble.id,kind:'callout',text:'配置',bbox:bubble.bbox},{operation:'remove',id:circle.id}],'已精简气泡并删除圈线。')
 await page.getByText('已精简气泡并删除圈线。').waitFor()
 const beforeMove=await screen.evaluate(c=>c.toDataURL()),anchorBefore=await pixel(190,160)
 await mkdir('artifacts/ai-callouts',{recursive:true});await page.screenshot({path:'artifacts/ai-callouts/conversation.png'})
 // Moving the bubble keeps its pointer anchored to the source object.
 const bounds=await screen.boundingBox(),scale=bounds.width/960,point=(x,y)=>({x:bounds.x+x*scale,y:bounds.y+y*scale})
 const bubbleRect=await page.evaluate(async factor=>{const {paintAi}=await import('/src/ai-callouts.ts');return paintAi({kind:'callout',text:'配置',bbox:[100,100,280,220]},{x:0,y:0,w:960,h:620},factor).ai.bubble},scale)
 await button('截图移动标注').click();const a=point(bubbleRect.x+bubbleRect.w/2,bubbleRect.y+bubbleRect.h/2),b=point(bubbleRect.x+bubbleRect.w/2+100,bubbleRect.y+bubbleRect.h/2+160)
 await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:8});await page.mouse.up();await page.getByLabel('已选中的标注').waitFor()
 assert.notEqual(await screen.evaluate(c=>c.toDataURL()),beforeMove);assert.deepEqual(await pixel(190,160),anchorBefore)
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 // The small target dot can also be moved independently to correct an AI position.
 const anchor=point(190,160),newAnchor=point(230,210)
 await page.mouse.move(anchor.x,anchor.y);await page.mouse.down();await page.mouse.move(newAnchor.x,newAnchor.y,{steps:6});await page.mouse.up()
 assert.notEqual(await pixel(190,160),anchorBefore);assert.deepEqual(await pixel(230,210),anchorBefore)
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 await page.mouse.click(a.x,a.y);await page.keyboard.press('Delete');assert.notEqual(await screen.evaluate(c=>c.toDataURL()),beforeMove);await page.keyboard.press('Control+z');assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 // Plain questions do not fabricate annotations; aborting a pending turn cannot change pixels.
 await button('AI 标注').click();await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('这个按钮是做什么的？');await button('发送 AI 标注指令').click();await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor()
 assert.equal(requests[2].body.existing.length,2)
 await reply(requests[2],[],'用于配置应用。');await page.getByText('用于配置应用。').waitFor();assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('增加另一条注释');await button('发送 AI 标注指令').click();await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor();await button('停止 AI 标注').click()
 await reply(requests[3],annotations,'取消后的回复不得显示').catch(()=>{});assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 await button('发送 AI 标注指令').click();await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor();await requests[4].route.fulfill({status:502,json:{detail:'标注位置无效'}})
 await page.getByRole('alert').filter({hasText:'标注位置无效'}).waitFor();assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 // No physical object is a valid result; it must never paint a paragraph substitute.
 await page.getByRole('textbox',{name:'AI 标注指令',exact:true}).fill('圈出截图中的主要物品');await button('发送 AI 标注指令').click();await page.getByRole('status').filter({hasText:'正在标注截图'}).waitFor()
 await reply(requests[5],[],'截图中未找到可确认的物品，因此没有添加标注。');await page.getByText('截图中未找到可确认的物品，因此没有添加标注。',{exact:true}).waitFor()
 assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove);assert.deepEqual(await page.locator('.capture-selection').boundingBox(),cropBefore)
 // Dragging/resizing the chat does not alter image marks.
 const header=await page.locator('.capture-annotation-chat header').boundingBox();await page.mouse.move(header.x+90,header.y+20);await page.mouse.down();await page.mouse.move(150,210,{steps:7});await page.mouse.up()
 const resize=await button('调整 AI 面板 se').boundingBox();await page.mouse.move(resize.x+6,resize.y+6);await page.mouse.down();await page.mouse.move(resize.x+80,resize.y+60,{steps:5});await page.mouse.up()
 assert.equal(await screen.evaluate(c=>c.toDataURL()),beforeMove)
 await button('关闭 AI 标注').click();assert.equal(await page.locator('.capture-tools-scroll>button.active').count(),0)
 await button('完成并复制截图').click();await page.waitForFunction(()=>window.exports.length===1);assert.equal(await page.evaluate(()=>window.exports[0].data),beforeMove)
 assert.deepEqual(errors,[]);console.log('PASS: on-image callout/circle/check, follow-up edit/remove, concise bubbles, fixed anchor on drag, delete/undo, plain questions, abort/failure, panel drag/resize, persistent toolbar and exported pixels.')
}finally{await browser.close()}
