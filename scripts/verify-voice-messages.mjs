// Synthetic PCM and ASR/LLM/session services; actual WAV playback in Edge.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
import {installMockAsr} from './mock-asr.mjs'
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=no-user-gesture-required']})
try{
 const page=await browser.newPage({viewport:{width:1100,height:900}}),sessions=new Map(),calls=[],errors=[];let tts=0,blockReply=false,releaseReply,replyStarted
 await installMockAsr(page)
 await page.addInitScript(()=>{const Capture=window.AudioWorkletNode;window.AudioWorkletNode=class extends Capture{constructor(...args){super(...args);window.lastCapture=this}}})
 page.on('pageerror',error=>errors.push(error.message))
 await page.route('**/api/**',async route=>{
  const path=new URL(route.request().url()).pathname,method=route.request().method(),body=method==='GET'?undefined:route.request().postDataJSON()
  if(path==='/api/capture/conversation'){calls.push(body);if(blockReply)await new Promise(resolve=>{releaseReply=resolve;replyStarted()});return route.fulfill({json:{action:'ocr',assetId:body.selectedId,answer:'Synthetic screenshot text',payload:{text:'Synthetic screenshot text'}}})}
  if(path==='/api/speech/synthesize')tts++
  if(path.startsWith('/api/sessions/')&&method==='PUT'){sessions.set(body.id,structuredClone(body));return route.fulfill({json:body})}
  if(path.endsWith('/image-title'))return route.fulfill({json:{title:'语音条测试'}})
  if(path==='/api/sessions')return route.fulfill({json:[...sessions.values()]})
  if(path==='/api/image-history')return route.fulfill({json:[...sessions.values()].map(s=>({id:s.id,title:s.title,createdAt:s.createdAt,updatedAt:s.updatedAt,pinned:s.pinned}))})
  if(path.startsWith('/api/sessions/'))return route.fulfill({json:sessions.get(path.split('/').at(-1))})
  return route.fulfill({json:{tools:[],items:[]}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{
  const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')])
  const canvas=document.createElement('canvas');canvas.width=400;canvas.height=220;canvas.getContext('2d').fillRect(0,0,400,220)
  const host=document.createElement('div');host.style.cssText='position:fixed;z-index:2000;left:250px;top:25px;width:520px;height:760px;background:white;border:1px solid #eee;border-radius:18px;overflow:hidden';document.body.append(host)
  window.chatApp=createApp(Chat,{initial:{id:'voice-fixture',name:'截图',data:canvas.toDataURL(),width:400,height:220,scenario:'custom'}});window.chat=window.chatApp.mount(host)
 })
 await page.getByRole('button',{name:'语音输入',exact:true}).click();const hold=page.getByRole('button',{name:'按住说话',exact:true})
 const box=await hold.boundingBox();await page.mouse.move(box.x+box.width/2,box.y+box.height/2);await page.mouse.down()
 await page.waitForFunction(()=>voiceInstances.at(-1)?.binary.length>0)
 await page.evaluate(()=>{const bytes=new ArrayBuffer((32000-320)*2),pcm=new DataView(bytes);for(let i=0;i<32000-320;i++)pcm.setInt16(i*2,Math.round(Math.sin(i/16000*2*Math.PI*220)*4000),true);lastCapture.port.onmessage({data:bytes});voiceResult('请提取截图中的文字')})
 await page.mouse.up();await page.getByText('Synthetic screenshot text',{exact:true}).waitFor()
 const bar=page.getByRole('button',{name:'播放语音',exact:true});await bar.waitFor();assert.match(await bar.innerText(),/00:02/);assert.equal(calls.length,1);assert.equal(calls[0].prompt,'请提取截图中的文字');assert.equal(await page.locator('.chat-user-bubble').count(),0)
 const session=[...sessions.values()].at(-1),message=session.messages.find(m=>m.role==='user');assert.equal(message.voice.duration,2);assert.ok(message.voice.data.startsWith('data:audio/wav;base64,'));assert.equal(message.voice.waveform.length,32)
 await bar.hover();const transcribe=page.getByRole('button',{name:'语音转文字',exact:true}).filter({has:page.locator('.lucide-file-text-icon')});await transcribe.click();await page.locator('.chat-voice-transcript').filter({hasText:'请提取截图中的文字'}).waitFor()
 await bar.click();const pause=page.getByRole('button',{name:'暂停语音',exact:true});await pause.waitFor();assert.notEqual(await page.locator('.chat-voice-wave i').first().evaluate(el=>getComputedStyle(el).animationName),'none');await pause.click();await bar.waitFor();assert.equal(tts,0,'Playback uses the original PCM recording, never synthesizes the transcript')
 await mkdir('artifacts/voice-messages',{recursive:true});await page.screenshot({path:'artifacts/voice-messages/expanded.png'})
 await page.getByRole('button',{name:'收起识别文字',exact:true}).click();assert.equal(await page.locator('.chat-voice-transcript').count(),0)
 await page.evaluate(()=>chat.showHistory());const history=page.getByRole('button',{name:'打开 '+session.title,exact:true});await history.click();await bar.waitFor();assert.match(await bar.innerText(),/00:02/);assert.equal(await page.getByRole('navigation',{name:'下一步操作示例'}).count(),0,'Historical messages never display live follow-up cards')
 blockReply=true;const started=new Promise(resolve=>replyStarted=resolve)
 const examples=page.getByRole('navigation',{name:'下一步操作示例'}),input=page.getByRole('textbox',{name:'图片对话输入'}),send=page.getByRole('button',{name:'发送图片对话',exact:true})
 await input.fill('请解释截图中的代码');await send.click();await started;await page.getByRole('button',{name:'暂停输出',exact:true}).waitFor()
 assert.equal(await examples.count(),0,'Examples are hidden while the new reply is pending')
 assert.equal(calls.length,2,'Preparing examples does not send another model request')
 releaseReply();blockReply=false;await send.waitFor();assert.equal(await examples.count(),1,'Examples appear with the completed reply without a second generation wait')
 assert.deepEqual(await examples.locator('button strong').allTextContents(),['逐行解释代码','检查潜在问题','整理修改建议'],'Examples depend on the question even when the mocked result action is OCR')
 assert.equal(calls.length,2,'Reply completion does not request separate example generation')
 await page.evaluate(()=>chat.showHistory());await page.getByRole('button',{name:'返回对话',exact:true}).click();await input.waitFor();assert.equal(await examples.count(),0,'Returning to an existing conversation keeps examples hidden')
 await page.evaluate(()=>chatApp.unmount());assert.deepEqual(errors,[])
 console.log('PASS: recorded PCM voice send, original WAV playback/pause, animated waveform, hover transcript expand/collapse, no duplicate ASR/TTS, persisted audio and history restoration. Synthetic services/input; actual audio playback.')
}finally{await browser.close()}
