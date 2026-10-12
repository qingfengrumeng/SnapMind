// Microphone and ASR are mocked. No personal audio or real model calls.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {installMockAsr} from './mock-asr.mjs'
import {readFile,mkdir} from 'node:fs/promises'
import vm from 'node:vm'
// Check the actual worklet's PCM format, resampling, silent output and tail flush.
const packets=[];let Processor
const sandbox={sampleRate:48000,AudioWorkletProcessor:class{constructor(){this.port={postMessage:packet=>packets.push(packet)}}},registerProcessor:(_,value)=>Processor=value,DataView,ArrayBuffer,Math}
vm.runInNewContext(await readFile('frontend/public/speech-capture-worklet.js','utf8'),sandbox)
const capture=new Processor({processorOptions:{sampleRate:16000}}),out=new Float32Array(128).fill(1)
for(let i=0;i<375;i++)capture.process([[new Float32Array(128).fill(.5)]],[[out]])
capture.port.onmessage({data:'flush'})
const pcm=packets.filter(packet=>packet instanceof ArrayBuffer)
assert.equal(pcm.reduce((size,packet)=>size+packet.byteLength,0),32000)
assert.equal(new DataView(pcm[0]).getInt16(0,true),16384);assert.equal(out.every(value=>value===0),true)
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1100,height:1000}}),calls=[],errors=[]
 await installMockAsr(page);page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',r=>{const path=new URL(r.request().url()).pathname;if(path==='/api/capture/conversation'){calls.push(r.request().postDataJSON());return r.fulfill({json:{action:'chat',assetId:'voice-image',answer:'Synthetic voice answer',payload:{}}})}return r.fulfill({json:path==='/api/sessions'?[]:{tools:[],items:[]}})})
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')]);const canvas=document.createElement('canvas');canvas.width=400;canvas.height=200;const host=document.createElement('div');host.style.cssText='position:fixed;z-index:1000;left:300px;top:30px;width:440px;height:760px;background:white';document.body.append(host);window.asrChat=createApp(Chat,{initial:{id:'voice-image',name:'截图',width:400,height:200,data:canvas.toDataURL(),scenario:'custom'}});window.asrChat.mount(host)})
 const input=page.getByRole('textbox',{name:'图片对话输入'}),mic=page.getByRole('button',{name:'语音转文字',exact:true})
 await input.fill('请');await mic.click();await page.getByRole('status').filter({hasText:'正在聆听'}).waitFor();await page.evaluate(()=>voiceResult('解释图片','解释图片'));await page.getByRole('button',{name:'停止语音转文字'}).click();await mic.waitFor();assert.equal(await input.inputValue(),'请解释图片');assert.equal(calls.length,0)
 await input.fill('');await page.getByRole('button',{name:'语音输入',exact:true}).click();const hold=page.getByRole('button',{name:'按住说话',exact:true});const bounds=await hold.boundingBox();await page.mouse.move(bounds.x+40,bounds.y+20);await page.mouse.down();await page.waitForFunction(()=>document.querySelector('.image-chat-hold strong')?.textContent.startsWith('正在聆听'))
 await page.evaluate(()=>voiceResult('识别并解释这张图片'));await mkdir('artifacts/asr',{recursive:true});await page.screenshot({path:'artifacts/asr/recording.png'});await page.mouse.up();await page.getByText('Synthetic voice answer',{exact:true}).waitFor();await page.waitForFunction(()=>document.querySelector('.image-conversation')?.getAttribute('aria-busy')==='false')
 assert.equal(calls.length,1);assert.equal(calls[0].prompt,'识别并解释这张图片');assert.equal(calls[0].assets.length,1);assert.equal(await page.evaluate(()=>voiceInstances.at(-1).stops),1);assert.equal(await page.evaluate(()=>voiceInstances.at(-1).aborts),1)
 // A release before startup completes cancels without sending an empty/late turn.
 await page.getByRole('button',{name:'语音输入',exact:true}).click();await page.evaluate(()=>window.deferVoiceStart=true);const next=await hold.boundingBox();await page.mouse.move(next.x+40,next.y+20);await page.mouse.down();await page.mouse.up();assert.equal(await page.evaluate(()=>voiceInstances.at(-1).aborts),1);assert.equal(calls.length,1);await page.evaluate(()=>window.deferVoiceStart=false);await page.getByRole('button',{name:'切换文字输入'}).click()
 // Cancelling finalization preserves confirmed text and prevents automatic send.
 await page.evaluate(()=>window.deferVoiceFinish=true);await mic.click();await page.getByRole('status').filter({hasText:'正在聆听'}).waitFor();await page.evaluate(()=>voiceResult('已确认的文字加临时草稿','已确认的文字'));await page.getByRole('button',{name:'停止语音转文字'}).click();await page.getByRole('button',{name:'取消语音识别',exact:true}).click();await mic.waitFor();assert.equal(await input.inputValue(),'已确认的文字');assert.equal(calls.length,1)
 const stops=await page.evaluate(()=>window.mediaStops);await mic.click();await page.getByRole('status').filter({hasText:'正在聆听'}).waitFor();await page.evaluate(()=>window.asrChat.unmount());assert.equal(await page.evaluate(()=>window.mediaStops),stops+1);assert.equal(await page.evaluate(()=>voiceInstances.at(-1).aborts),1);assert.deepEqual(errors,[])
 console.log('PASS: PCM16 LE resampling/flush, live dictation without auto-send, hold-release automatic AI send with screenshot, early-release cancellation, finalization cancellation and microphone cleanup.')
}finally{await browser.close()}
