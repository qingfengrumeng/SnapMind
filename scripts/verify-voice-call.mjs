// Synthetic microphone, ASR, LLM/tool responses, TTS, and session storage only.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
import {installMockAsr} from './mock-asr.mjs'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[],calls=[],tts=[],saved=[]
 let releaseLate,releaseFirst,firstStarted
 const firstRequest=new Promise(resolve=>firstStarted=resolve)
 const recognizedReply='识别到的文字是：SnapMind voice test。\n'+Array.from({length:8},(_,index)=>`截图文字第 ${index+1} 行。`).join('\n')
 await installMockAsr(page)
 await page.addInitScript(()=>{window.audioEvents=[];window.testAudios=[];window.Audio=class{constructor(){window.testAudios.push(this)}async play(){window.audioEvents.push('play')}pause(){window.audioEvents.push('pause')}removeAttribute(){}load(){window.audioEvents.push('clear')}}})
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',async r=>{
  const path=new URL(r.request().url()).pathname,method=r.request().method(),body=method==='GET'?undefined:r.request().postDataJSON()
  if(path==='/api/speech/synthesize'){tts.push(body.text);return r.fulfill({contentType:'audio/mpeg',body:Buffer.from('ID3synthetic')})}
  if(path==='/api/capture/conversation'){
   calls.push(body);const annotation=body.prompt.includes('圈出')||body.prompt.includes('延迟')
   if(calls.length===1)await new Promise(resolve=>{releaseFirst=resolve;firstStarted()})
   if(body.prompt.includes('撤销')){
    assert.ok(body.undoSnapshot,'Cross-turn undo carries the actual previous screenshot');assert.equal(body.undoSnapshot.annotations.length,0)
    const asset=body.undoSnapshot.asset
    return r.fulfill({json:{action:'restore_image',assetId:body.selectedId,answer:'已撤销最近一次截图操作。',payload:{data:asset.data,width:asset.width,height:asset.height,annotations:body.undoSnapshot.annotations}}})
   }
   if(body.prompt.includes('延迟'))await new Promise(resolve=>releaseLate=resolve)
   return r.fulfill({json:{action:annotation?'annotate':'ocr',assetId:body.selectedId,answer:annotation?'已完成标题标注，可撤销。':recognizedReply,payload:annotation?{answer:'已完成标题标注，可撤销。',annotations:[{operation:'add',kind:'circle',text:'标题',bbox:[40,30,330,90]}],width:800,height:500,coordinateSpace:'image-pixels',approximate:false}:{text:'SnapMind voice test'}}}).catch(()=>{})
  }
  if(path.endsWith('/image-title'))return r.fulfill({json:{title:'语音识字与标注',source:'test'}})
  if(path.startsWith('/api/sessions/')&&method==='PUT'){saved.push(body);return r.fulfill({json:body})}
  if(path==='/api/image-history'){const latest=new Map(saved.map(s=>[s.id,s]));return r.fulfill({json:[...latest.values()].map(s=>({id:s.id,title:s.title,createdAt:s.createdAt,updatedAt:s.updatedAt,pinned:s.pinned,hasVoiceCall:!!s.voiceCall}))})}
  if(path.startsWith('/api/sessions/')&&method==='GET')return r.fulfill({json:saved.findLast(s=>s.id===path.split('/').at(-1))})
  return r.fulfill({json:path==='/api/sessions'?[]:{tools:[],items:[]}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Overlay},{createApp}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,800,500);g.fillStyle='#493368';g.font='28px Segoe UI';g.fillText('SnapMind voice test',40,65)
  const host=document.createElement('div');document.body.append(host);window.voiceOverlay=createApp(Overlay,{source:{id:'voice-call-fixture',name:'Synthetic screenshot',data:c.toDataURL(),width:800,height:500,scenario:'custom'},initialSelection:true});window.voiceOverlay.mount(host)
 })
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const call=page.locator('[data-capture-tool="voiceCall"]')
 await call.click();const spirit=page.getByRole('region',{name:'小洁实时语音通话'})
 await spirit.waitFor();await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'));assert.equal(await page.evaluate(()=>voiceInstances.length),0,'Introduction is not fed into ASR')
 assert.match(tts[0],/嗨，我是 SnapMind 里的 AI 精灵——小洁/);assert.match(await spirit.innerText(),/截图、识字、翻译、标注/);assert.equal(await call.getAttribute('aria-pressed'),'true')
 assert.equal(saved.length,0,'An introduction alone does not create a historical session')
 await spirit.getByRole('button',{name:'结束通话',exact:true}).click();await page.waitForTimeout(100);assert.equal(saved.length,0,'Hanging up without a query never saves the introduction')
 await call.click();await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'))
 assert.equal(await page.locator('.capture-toolbar').isVisible(),false,'Screenshot toolbar hides during the call')
 await mkdir('artifacts/voice-call',{recursive:true});await page.waitForTimeout(400);await page.screenshot({path:'artifacts/voice-call/xiaojie.png'})
 const darkPreview=await page.addStyleTag({content:'.capture-screen{filter:brightness(.13)}'});await page.screenshot({path:'artifacts/voice-call/xiaojie-glass-dark.png'});await darkPreview.evaluate(element=>element.remove())
 const mic=spirit.getByRole('button',{name:'暂停接收语音',exact:true}),pauseButton=spirit.getByRole('button',{name:'暂停通话',exact:true})
 assert.ok((await mic.boundingBox()).x<(await pauseButton.boundingBox()).x,'Microphone control sits to the left of pause')
 const audioEventsBeforeMute=await page.evaluate(()=>audioEvents.length)
 await mic.click();await spirit.getByRole('button',{name:'恢复接收语音',exact:true}).waitFor()
 assert.equal(await page.evaluate(()=>audioEvents.length),audioEventsBeforeMute,'Muting input does not pause or cancel AI playback')
 assert.equal(await spirit.getByRole('button',{name:'恢复接收语音',exact:true}).getAttribute('aria-pressed'),'true')
 await page.evaluate(()=>testAudios.at(-1).onended());await page.waitForTimeout(120)
 assert.equal(await page.evaluate(()=>voiceInstances.length),0,'Playback completion never restarts a muted microphone')
 await spirit.getByText('麦克风已暂停',{exact:true}).waitFor()
 await spirit.getByRole('button',{name:'恢复接收语音',exact:true}).click();await page.waitForFunction(()=>voiceInstances.length===1&&voiceInstances[0].binary.length>0)
 await page.evaluate(()=>{window.staleTranscript=voiceInstances.at(-1).onmessage})
 await mic.click();assert.equal(await page.evaluate(()=>voiceInstances.at(-1).readyState),3,'Muting releases the active ASR connection')
 const callsBeforeMute=calls.length
 await page.evaluate(()=>staleTranscript({data:JSON.stringify({type:'utterance',text:'不应执行的旧语音'})}));await page.waitForTimeout(100)
 assert.equal(calls.length,callsBeforeMute,'Late ASR events cannot start a task while muted')
 await spirit.getByRole('button',{name:'恢复接收语音',exact:true}).click();await page.waitForFunction(()=>voiceInstances.length===2&&voiceInstances.at(-1).binary.length>0)
 const avatar=spirit.getByRole('button',{name:'小洁精灵，点击互动，拖动移动'})
 await avatar.click();await page.waitForFunction(()=>document.querySelector('.spirit-avatar')?.classList.contains('jumping'))
 const before=await spirit.boundingBox(),a=await avatar.boundingBox();await page.mouse.move(a.x+a.width/2,a.y+a.height/2);await page.mouse.down();await page.mouse.move(a.x+a.width/2-150,a.y+a.height/2-80,{steps:8});await page.mouse.up();const after=await spirit.boundingBox();assert.ok(before.x-after.x>140&&before.y-after.y>70)
 // VAD interrupts introductory speech before the transcript is finalized.
 await page.evaluate(()=>voiceInstances.at(-1).onmessage({data:JSON.stringify({type:'speech-started'})}));await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-listening'))
 await page.evaluate(()=>voiceResult('用户尚未说完的内容',''))
 assert.equal(await spirit.locator('.spirit-user').count(),0,'Live user transcription is never rendered in the reply card')
 assert.equal(await spirit.locator('.spirit-dialogue').innerText().then(text=>text.includes('用户尚未说完的内容')),false)
 await page.evaluate(()=>voiceResult('嗯。'));await page.waitForTimeout(600)
 assert.equal(calls.length,0,'Filler hallucinations never invoke the screenshot agent')
 assert.equal(saved.length,0,'Filler hallucinations never create a call history record')
 await page.evaluate(()=>voiceResult('提取截图里的文字'))
 await firstRequest;assert.equal(saved.length,0,'The first question remains unsaved until its AI reply completes');releaseFirst()
 await page.waitForFunction(()=>document.querySelector('.spirit-answer')?.textContent.includes('识别到的文字'))
 await page.waitForFunction(()=>window.voiceInstances.length===2&&document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'))
 assert.equal(calls.length,1);assert.equal(calls[0].prompt,'提取截图里的文字');assert.equal(calls[0].assets.length,1);assert.equal(calls[0].assets[0].width,800);assert.ok(calls[0].sessionId.startsWith('voicecall-'));assert.ok(tts.at(-1).includes('识别到的文字'));assert.ok(saved.some(s=>s.messages.some(m=>m.role==='user'&&m.images?.length===1)))
 assert.ok(saved.at(-1).voiceCall);assert.equal(saved.at(-1).messages[0].images[0].data,calls[0].assets[0].data,'First question includes the original screenshot')
 assert.ok(saved.every(s=>s.messages[0]?.role==='user'&&s.messages[1]?.role==='assistant'),'Every saved call starts with a completed question and reply')
 const replyCard=spirit.locator('.spirit-dialogue'),longHeight=(await replyCard.boundingBox()).height
 assert.equal(await replyCard.innerText().then(text=>text.includes('提取截图里的文字')),false,'Confirmed user queries stay in memory without appearing in the reply card')
 assert.ok(longHeight>230,'Multi-line replies expand the card beyond the previous height cap')
 assert.equal(await spirit.locator('.spirit-answer').evaluate(el=>el.scrollHeight<=el.clientHeight+1),true,'Replies do not create a nested scrolling area')
 await page.evaluate(()=>voiceResult('圈出标题'))
 await page.waitForFunction(()=>document.querySelector('.spirit-answer')?.textContent.includes('已完成标题标注，可撤销'))
 await page.waitForFunction(()=>window.voiceInstances.length===2&&document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'))
 assert.ok(calls[1].history.some(h=>h.role==='assistant'&&h.text.includes('识别到的文字')));assert.ok(saved.at(-1).imageConversation.pictures[0].annotations.length===1)
 assert.equal(await spirit.locator('.spirit-answer').textContent(),'已完成标题标注，可撤销。')
 assert.ok((await replyCard.boundingBox()).height<longHeight-100,'Short task confirmations shrink the card automatically')
 await page.screenshot({path:'artifacts/voice-call/task-reply.png'})
 assert.equal(await page.locator('[data-capture-tool="undo"]').isDisabled(),false,'Voice annotation updates the actual screenshot undo stack')
 await page.evaluate(()=>voiceResult('撤销刚才的操作'))
 await page.waitForFunction(()=>document.querySelector('.spirit-answer')?.textContent.includes('已撤销'))
 await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'))
 assert.equal(calls.length,3);assert.equal(saved.at(-1).imageConversation.pictures[0].annotations.length,0,'Natural language undo restores screenshot annotations across queries')
 await spirit.getByRole('button',{name:'暂停通话',exact:true}).click();await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-paused'));assert.equal(await page.evaluate(()=>voiceInstances.at(-1).readyState),3)
 await spirit.getByRole('button',{name:'继续通话',exact:true}).click();await page.waitForFunction(()=>window.voiceInstances.length===3&&voiceInstances.at(-1).binary.length>0)
 // A queued old operation must not apply after hangup.
 await page.evaluate(()=>voiceResult('延迟圈出标题'));await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-thinking'));while(!releaseLate)await page.waitForTimeout(10)
 await spirit.getByRole('button',{name:'结束通话',exact:true}).click();assert.equal(await spirit.count(),0);assert.equal(await call.getAttribute('aria-pressed'),'false');assert.equal(await page.locator('.capture-toolbar').isVisible(),true,'Toolbar restores after hangup');assert.equal(await page.evaluate(()=>voiceInstances.at(-1).readyState),3);const audioCount=tts.length;releaseLate();await page.waitForTimeout(250);assert.equal(tts.length,audioCount,'No late TTS after hangup')
 // Shortcut reopens it; denied permission is explicit and can be retried.
 await page.evaluate(()=>window.denyMic=true);await page.keyboard.press('x');await spirit.waitFor();await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'));await page.evaluate(()=>testAudios.at(-1).onended());await spirit.getByRole('alert').filter({hasText:'麦克风权限未开启'}).waitFor();assert.notEqual(await spirit.locator('.spirit-answer').evaluate(el=>getComputedStyle(el).color),await spirit.getByRole('alert').evaluate(el=>getComputedStyle(el).color),'Microphone errors do not turn the introduction red');await page.evaluate(()=>window.denyMic=false);await spirit.getByRole('button',{name:'重新连接',exact:true}).click();await page.waitForFunction(()=>voiceInstances.at(-1).binary.length>0)
 await page.setViewportSize({width:420,height:720});await page.waitForTimeout(100);const narrow=await spirit.boundingBox();assert.ok(narrow.x>=7&&narrow.x+narrow.width<=413&&narrow.y+narrow.height<=713);await page.screenshot({path:'artifacts/voice-call/xiaojie-mobile.png'})
 await page.evaluate(()=>window.voiceOverlay.unmount());assert.equal(await spirit.count(),0);assert.equal(await page.evaluate(()=>voiceInstances.at(-1).readyState),3);assert.ok(await page.evaluate(()=>mediaStops>=3&&audioCloses>=3));assert.deepEqual(errors,[])
 const recordedId=calls[0].sessionId
 for(let attempt=0;attempt<100&&!saved.findLast(s=>s.id===recordedId)?.voiceCall.endedAt;attempt++)await page.waitForTimeout(20)
 const record=saved.findLast(s=>s.id===recordedId);assert.ok(record.voiceCall.endedAt);assert.equal(new Set(saved.map(s=>s.id)).size,1,'Each useful call creates one independent session; empty calls create none')
 await page.evaluate(async()=>{const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')]);const host=document.createElement('div');host.style.cssText='position:fixed;inset:10px;background:white;z-index:3000';document.body.append(host);window.historyApp=createApp(Chat);window.historyChat=historyApp.mount(host);await historyChat.showHistory()})
 const historyRow=page.getByRole('button',{name:'打开 '+record.title,exact:true});await historyRow.waitFor();assert.equal(await historyRow.locator('.history-call-badge .lucide-phone-call-icon').count(),1)
 await historyRow.click();await page.getByRole('separator',{name:'语音通话开始',exact:true}).waitFor();await page.getByRole('separator',{name:'语音通话结束',exact:true}).waitFor();assert.equal(await page.locator('.sent-image-attachments img').count(),1);assert.equal(await page.locator('.chat-voice-message').count(),0,'Call history contains plain text rather than audio bars')
 await page.getByRole('button',{name:'查看 截图',exact:true}).click();await page.getByRole('dialog',{name:'图片预览 截图'}).waitFor();await page.getByRole('button',{name:'关闭图片预览'}).click()
 const input=page.getByRole('textbox',{name:'图片对话输入'});await input.fill('请继续解释刚才的截图内容');await page.getByRole('button',{name:'发送图片对话',exact:true}).click();await page.getByRole('button',{name:'发送图片对话',exact:true}).waitFor()
 assert.equal(calls.at(-1).sessionId,recordedId);assert.ok(calls.at(-1).history.some(m=>m.role==='user'&&m.text==='提取截图里的文字'));assert.equal(saved.at(-1).voiceCall.endMessageId,record.voiceCall.endMessageId,'Text continuation preserves the original call boundary')
 assert.equal(await page.getByRole('separator',{name:'语音通话结束'}).evaluate(el=>!!el.nextElementSibling?.classList.contains('user')),true,'Text follow-ups render after the call-ended divider')
 await page.screenshot({path:'artifacts/voice-call/text-history.png'});await page.evaluate(()=>historyApp.unmount());assert.deepEqual(errors,[])
 console.log('PASS: immediate draggable/jumping Xiaojie, introduction TTS, VAD interruption, automatic ASR → screenshot agent → TTS, multi-turn context, real screenshot annotations/undo, persisted image history, pause/resume, hangup/late response guards, shortcut, microphone permission retry, narrow layout, resource cleanup. All inputs/services mocked.')
}finally{await browser.close()}
