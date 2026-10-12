// Generated image, mocked requests and speech only. No model or microphone access.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1100,height:1000}}),calls=[],errors=[]
 let blocked=true,release,longReply=''
 await page.addInitScript(()=>{
  window.reads=[];window.speechEvents=[];window.Audio=class{constructor(url){this.url=url;window.reads.push(this)}async play(){window.speechEvents.push(this.started?'resume':'play');this.started=true}pause(){window.speechEvents.push('pause')}removeAttribute(){}load(){window.speechEvents.push('cancel')}}
  Object.defineProperty(navigator.clipboard,'writeText',{value:async text=>window.copied=text})
 })
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',async r=>{
  const path=new URL(r.request().url()).pathname
  if(path==='/api/speech/synthesize'){await page.evaluate(data=>window.ttsText=data.text,r.request().postDataJSON());return r.fulfill({contentType:'audio/mpeg',body:Buffer.from('ID3fixture')})}
  if(path==='/api/capture/conversation'){
   const request=r.request().postDataJSON();calls.push(request)
   if(blocked)await new Promise(resolve=>release=resolve)
   await r.fulfill({json:{action:'chat',assetId:request.selectedId,answer:blocked?'Late cancelled answer':longReply||'Synthetic answer '+calls.length,payload:{}}}).catch(()=>{})
  }else await r.fulfill({json:path==='/api/sessions'?[]:{tools:[],items:[]}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=420;c.height=260;const g=c.getContext('2d');g.fillStyle='#f4edff';g.fillRect(0,0,420,260);g.fillStyle='#51326f';g.font='24px sans-serif';g.fillText('Synthetic screenshot',30,120)
  const host=document.createElement('div');host.style.cssText='position:fixed;z-index:1000;left:50%;top:20px;transform:translateX(-50%);width:440px;height:760px;background:white;border:1px solid #e5d6fa;border-radius:18px;overflow:hidden';document.body.append(host)
  window.messageApp=createApp(Chat,{initial:{id:'message-image',name:'当前截图',scenario:'custom',width:420,height:260,data:c.toDataURL()}});window.messageApp.mount(host)
 })
 const input=page.getByRole('textbox',{name:'图片对话输入'}),send=page.getByRole('button',{name:'发送图片对话',exact:true}),draftImages=page.locator('.image-chat-attachments .chat-image-chip')
 await draftImages.waitFor();await input.fill('这是什么？');await send.click()
 const stop=page.getByRole('button',{name:'暂停输出',exact:true});await stop.waitFor();assert.equal(await stop.locator('.chat-stop-square').count(),1);assert.equal(await page.getByRole('button',{name:'停止',exact:true}).count(),0)
 await page.waitForFunction(()=>document.querySelector('.sent-image-attachments img'))
 assert.equal(await page.locator('.chat-avatar[aria-label="用户"]').count(),1);assert.equal(await page.locator('.chat-avatar .snapmind-logo').count(),1)
 await stop.click();await page.getByText('已暂停输出',{exact:true}).waitFor();assert.equal(await send.isVisible(),true);assert.equal(await draftImages.count(),0)
 assert.equal(await page.getByRole('button',{name:'继续输出',exact:true}).count(),0,'Thinking cancellation cannot resume');assert.equal(await input.inputValue(),'这是什么？','Thinking cancellation keeps the question ready to resend')
 release();await page.waitForTimeout(150);assert.equal(await page.getByText('Late cancelled answer',{exact:true}).count(),0)
 blocked=false;await page.getByRole('button',{name:'重新生成',exact:true}).click();await page.getByText('Synthetic answer 2',{exact:true}).waitFor()
 assert.equal(await page.getByRole('navigation',{name:'下一步操作示例'}).count(),0,'Regeneration without a new user question does not display cards')
 assert.equal(await page.locator('.image-chat-turn.user').count(),1,'Regeneration does not duplicate the user message')
 assert.deepEqual(calls[1].assets,calls[0].assets);assert.deepEqual(calls[1].history,calls[0].history);assert.equal(calls[1].prompt,calls[0].prompt)
 await page.getByRole('button',{name:'查看 当前截图',exact:true}).click();await page.getByRole('dialog',{name:'图片预览 当前截图'}).waitFor();await page.getByRole('button',{name:'关闭图片预览'}).click()
 await page.getByRole('button',{name:'复制消息',exact:true}).click();assert.equal(await page.evaluate(()=>window.copied),'Synthetic answer 2')
 const copied=page.getByRole('button',{name:'复制消息',exact:true});await page.waitForFunction(()=>document.querySelector('.chat-answer-actions .copied .lucide-check-icon'));await page.mouse.move(1,1);await copied.hover();await page.getByRole('tooltip').filter({hasText:'消息已复制'}).waitFor();assert.equal(await page.getByRole('button',{name:'重新生成',exact:true}).locator('.lucide-rotate-ccw-icon').count(),1)
 const read=page.getByRole('button',{name:'朗读消息',exact:true});await read.hover();await page.getByRole('tooltip').filter({hasText:'朗读消息'}).waitFor();await read.click();await page.getByRole('button',{name:'暂停朗读',exact:true}).waitFor();assert.equal(await page.evaluate(()=>window.ttsText),'Synthetic answer 2')
 await page.getByRole('button',{name:'暂停朗读',exact:true}).click();await page.getByRole('button',{name:'继续朗读',exact:true}).click();assert.deepEqual(await page.evaluate(()=>window.speechEvents.slice(-2)),['pause','resume'])
 await page.waitForFunction(()=>{const el=document.querySelector('.chat-answer-actions button.reading');return el&&getComputedStyle(el).backgroundColor==='rgb(98, 23, 183)'&&getComputedStyle(el).color==='rgb(255, 255, 255)'})
 await input.fill('再解释一下');await send.click();await page.getByText('Synthetic answer 3',{exact:true}).waitFor()
 assert.equal(await page.locator('.sent-image-attachments img').count(),1,'The screenshot is attached only to its first user message');assert.equal(await draftImages.count(),0);assert.equal(calls[2].assets[0].id,'message-image','Follow-ups keep image context');assert.equal(calls[2].history.length,2)
 await page.getByRole('button',{name:'重新生成',exact:true}).first().click();await page.getByText('Synthetic answer 4',{exact:true}).waitFor();assert.equal(calls[3].history.length,0,'Earlier reply regeneration excludes later conversation');assert.equal(await page.locator('.image-chat-turn.user').count(),2)
 await mkdir('artifacts/chat-messages',{recursive:true});await page.screenshot({path:'artifacts/chat-messages/conversation.png'})
 longReply='这是用于暂停和继续验证的内容😀。\n'.repeat(45)+'完整输出结束。';await send.waitFor();await input.fill('请继续解释');await send.click()
 const output=page.locator('.image-chat-turn.assistant').last().locator('.capture-study-message');await output.waitFor();await page.getByRole('button',{name:'暂停输出',exact:true}).click();const resume=page.getByRole('button',{name:'继续输出',exact:true});await resume.waitFor();assert.equal(await resume.locator('.chat-output-resume').count(),1)
 const partial=await output.textContent();assert.ok(partial.length>0&&partial.length<longReply.length);await page.getByText('已暂停输出',{exact:true}).waitFor();await page.waitForTimeout(180);assert.equal(await output.textContent(),partial,'Paused output must not advance');const requestCount=calls.length
 assert.equal(await page.getByRole('navigation',{name:'下一步操作示例'}).count(),0,'Prepared examples remain hidden until the reply finishes')
 await page.screenshot({path:'artifacts/chat-messages/paused-output.png'});await resume.click();assert.equal(await page.getByText('已暂停输出',{exact:true}).count(),0);await page.waitForFunction(text=>document.querySelectorAll('.image-chat-turn.assistant .capture-study-message').item(document.querySelectorAll('.image-chat-turn.assistant .capture-study-message').length-1)?.textContent===text,longReply)
 await send.waitFor();assert.equal(calls.length,requestCount,'Resume continues the same buffered answer without a new model call');assert.equal(await output.textContent(),longReply)
 const examples=page.getByRole('navigation',{name:'下一步操作示例'});await examples.waitFor();assert.equal(await examples.locator('button').count(),3)
 longReply='';await input.fill('保留这个尚未发送的草稿');const beforeExample=calls.length
 await examples.getByRole('button',{name:'提取截图文字',exact:true}).click();await page.getByText('Synthetic answer '+(beforeExample+1),{exact:true}).waitFor();await send.waitFor()
 assert.equal(calls.length,beforeExample+1,'One card click sends exactly one request');assert.match(calls.at(-1).prompt,/提取当前截图中的全部文字/);assert.equal(calls.at(-1).assets[0].id,'message-image');assert.equal(await input.inputValue(),'保留这个尚未发送的草稿','Card actions preserve the unsent draft')
 await page.screenshot({path:'artifacts/chat-messages/followup-cards.png'})
 await page.evaluate(()=>window.messageApp.unmount());assert.equal(await page.evaluate(()=>window.speechEvents.at(-1)),'cancel');assert.deepEqual(errors,[])
 console.log('PASS: inline prompt wrapping, send/stop control, aborted reply suppression, avatars, first-send image and preview, follow-up image context, snapshot regeneration without duplicate messages, copy, tooltip, reading pause/resume and cleanup. Mocked requests and speech only.')
}finally{await browser.close()}
