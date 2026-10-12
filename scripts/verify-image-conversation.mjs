import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1500,height:1000}}),pending=[],saved=[],errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{const path=new URL(route.request().url()).pathname;if(path==='/api/capture/conversation'){pending.push({route,body:route.request().postDataJSON()});return}if(path.startsWith('/api/sessions/')&&route.request().method()==='PUT'){saved.push(route.request().postDataJSON());return route.fulfill({json:{}})}if(path==='/api/sessions')return route.fulfill({json:Array.from(new Map(saved.map(s=>[s.id,s])).values())});if(path==='/api/settings/models')return route.fulfill({json:{activeId:null,profiles:[]}});return route.fulfill({json:{mode:'test',items:[]}})})
 await page.goto('http://127.0.0.1:5174');assert.equal(await page.getByRole('button',{name:'图片对话',exact:true}).count(),0,'Homepage dialogue has been removed')
 await page.evaluate(async()=>{const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')]);const root=document.createElement('div');root.style.cssText='position:fixed;z-index:1000;right:20px;top:20px;width:520px;height:850px;background:#fff';document.body.append(root);window.imageChatFixture=root;window.imageChatFixtureApp=createApp(Chat);window.imageChatFixtureApp.mount(root)})
 await page.getByRole('textbox',{name:'图片对话输入'}).waitFor()
 await page.getByRole('button',{name:'新建会话',exact:true}).click()
 assert.equal(await page.locator('.image-chat-actions').getByRole('button',{name:'离线识别',exact:true}).count(),0)
 for(const name of ['表格提取','理解代码','注释论文','检查作答','提取公式','图片笔记','解释内容','AI 标注','物体识别','二维码／条码','链接与邮箱'])assert.equal(await page.getByRole('button',{name,exact:true}).count(),0,'Removed independent action: '+name)
 async function pasteImage(name='pasted.png'){
  await page.getByRole('textbox',{name:'图片对话输入'}).evaluate((el,name)=>{const c=document.createElement('canvas');c.width=420;c.height=260;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,c.width,c.height);g.fillStyle='#493066';g.font='20px Segoe UI';g.fillText('Image conversation example',30,45);g.fillRect(40,90,90,80);const bytes=Uint8Array.from(atob(c.toDataURL().split(',')[1]),ch=>ch.charCodeAt(0)),clipboard=new DataTransfer();clipboard.items.add(new File([bytes],name,{type:'image/png'}));el.dispatchEvent(new ClipboardEvent('paste',{clipboardData:clipboard,bubbles:true,cancelable:true}))},name)
 }
 await pasteImage();await page.getByRole('button',{name:'引用 pasted',exact:true}).waitFor();assert.equal(await page.locator('.capture-overlay').count(),0,'paste must stay in the conversation')
 const ask=async text=>{await page.getByRole('textbox',{name:'图片对话输入'}).fill(text);await page.getByRole('button',{name:'发送图片对话'}).click();await page.getByRole('status').filter({hasText:'正在处理图片'}).waitFor()}
 const response=async (index,action,answer,payload)=>{const req=pending[index];await req.route.fulfill({json:{action,answer,payload,assetId:req.body.selectedId}});await page.getByText(answer,{exact:true}).waitFor()}
 await ask('提取文字');assert.equal(pending[0].body.assets.length,1);assert.equal(pending[0].body.history.length,0);assert.equal(await page.locator('.capture-wait-dots i').count(),3)
 await response(0,'ocr','Image conversation example',{text:'Image conversation example'})
 await ask('它是什么用途？');assert.equal(pending[1].body.history.length,2);assert.equal(pending[1].body.assets[0].id,pending[0].body.assets[0].id)
 await response(1,'chat','这是用于验证图片连续对话的示例。',{text:'这是用于验证图片连续对话的示例。'})
 await pasteImage('second.png');await page.getByRole('button',{name:'引用 second',exact:true}).waitFor();await ask('比较这两张图片');assert.equal(pending[2].body.assets.length,2);assert.equal(pending[2].body.history.length,4);await response(2,'chat','两张图的示例内容一致。',{text:'两张图的示例内容一致。'})
 await ask('提取截图中的表格');assert.equal(pending[3].body.action,undefined);await response(3,'table','已提取测试表格。',{tables:[{title:'Numbers',rows:[['Code','Value'],['001','0']]}]});assert.equal(await page.getByRole('button',{name:'复制到 Excel',exact:true}).count(),1)
 await ask('圈出色块');assert.ok(pending[4].body.history.some(turn=>turn.text.includes('001')&&turn.text.includes('Numbers')),'follow-up must carry extracted table content');await response(4,'annotate','已圈出色块。',{width:420,height:260,coordinateSpace:'image-pixels',approximate:false,answer:'已圈出色块。',annotations:[{operation:'add',kind:'circle',text:'',bbox:[40,90,130,170],locationSource:'ocr'}]})
 const annotated=await page.locator('.image-chat-picture img').getAttribute('src');assert.notEqual(annotated,pending[4].body.assets.at(-1).data)
 await page.getByRole('button',{name:'新建会话',exact:true}).click();await page.getByRole('button',{name:'历史记录',exact:true}).click();await page.locator('.image-chat-history').getByRole('button',{name:'提取文字',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.image-conversation')?.getAttribute('aria-busy')==='false')
 assert.equal(await page.locator('.image-chat-picture img').getAttribute('src'),annotated,'restore editable OCR annotation scene without baking it into the original picture')
 assert.equal(await page.getByRole('button',{name:'复制到 Excel',exact:true}).count(),1,'structured table must survive history restore')
 assert.equal(await page.locator('.chat-image-chip.active').getByRole('button',{name:'引用 second',exact:true}).count(),1,'remember selected image')
 const snapshot=saved.filter(s=>s.id.startsWith('imagechat-')).at(-1);assert.equal(snapshot.imageConversation.version,1);assert.equal(snapshot.imageConversation.pictures.find(p=>p.assetId===snapshot.imageConversation.selectedId).annotations[0].locationSource,'ocr');assert.equal(snapshot.assets.at(-1).data,pending[4].body.assets.at(-1).data)
 await ask('删除圈线');assert.equal(pending[5].body.existing.length,1);await response(5,'annotate','已删除圈线。',{width:420,height:260,coordinateSpace:'image-pixels',approximate:false,answer:'已删除圈线。',annotations:[{operation:'remove',id:pending[5].body.existing[0].id}]})
 assert.notEqual(await page.locator('.image-chat-picture img').getAttribute('src'),annotated)
 await ask('注释这两张论文页面');assert.equal(pending[6].body.action,undefined);const studyRequest=pending[6],notes=studyRequest.body.assets.map((asset,index)=>({pageId:asset.id,kind:'callout',text:'第 '+(index+1)+' 页重点',explanation:'生成测试页面的说明',targetIds:['text-1'],bbox:[30,20,300,55],locationSource:'ocr',lineLabel:null}));await response(6,'paper','已分别注释两张页面。',{mode:'paper',answer:'已分别注释两张页面。',notes,pages:studyRequest.body.assets.map((a,i)=>({id:a.id,name:a.name,width:a.width,height:a.height,number:i+1,ocrMode:'mock',warning:null})),coordinateSpace:'image-pixels'})
 const selectedRendered=await page.locator('.image-chat-picture img').getAttribute('src');await page.getByRole('button',{name:'引用 pasted',exact:true}).click();assert.notEqual(await page.locator('.image-chat-picture img').getAttribute('src'),studyRequest.body.assets[0].data,'annotations must appear on the other referenced page too');assert.notEqual(await page.locator('.image-chat-picture img').getAttribute('src'),selectedRendered)
 await ask('继续解释');await page.getByRole('button',{name:'停止',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.image-conversation')?.getAttribute('aria-busy')==='false');assert.ok(saved.length>=6,'conversation must persist')
 await page.evaluate(()=>{window.imageChatFixtureApp.unmount();window.imageChatFixture.remove()})
 // Exercise the screenshot toolbar and history using only generated pixels.
 await page.evaluate(async()=>{const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')]);const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,800,500);g.fillStyle='#555';g.font='20px Segoe UI';g.fillText('Generated screenshot',30,40);const node=document.createElement('div');document.body.append(node);createApp({render:()=>h(Overlay,{source:{id:'generated-image',name:'Synthetic',data:c.toDataURL(),width:800,height:500,scenario:'custom'},initialSelection:true})}).mount(node)})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const button=name=>page.locator('.capture-overlay').getByRole('button',{name,exact:true}),screen=page.locator('.capture-screen')
 const original=await screen.evaluate(c=>c.toDataURL()),position=await screen.boundingBox(),scale=position.width/800
 await button('截图荧光笔').click();await page.mouse.move(position.x+100*scale,position.y+100*scale);await page.mouse.down();await page.mouse.move(position.x+220*scale,position.y+100*scale);await page.mouse.up();assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original)
 await button('撤销截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),original)
 await button('重做截图标注').click();assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original)
 await button('清空截图标注').click();assert.equal(await screen.evaluate(c=>c.toDataURL()),original)
 await button('截图矩形').click();assert.equal(await button('截图矩形').getAttribute('class'),'active');await button('截图矩形').click();assert.notEqual(await button('截图矩形').getAttribute('class'),'active','click tool again must return idle')
 await button('AI对话').click();await page.getByLabel('图片对话面板',{exact:true}).waitFor();assert.equal(await page.locator('.capture-overlay').evaluate(e=>e.style.cursor),'default');assert.equal(await page.locator('.capture-toolbar').count(),0)
 await mkdir('artifacts/image-tools',{recursive:true});await page.screenshot({path:'artifacts/image-tools/conversation.png'})
 assert.deepEqual(errors,[])
 console.log('PASS: pasted/multiple images, table follow-up context, durable table/selection/OCR annotation history, editable restored marks, both-page study notes, cancellation, toolbar, idle cursor, highlighter and undo/redo/clear.')
}finally{await browser.close()}
