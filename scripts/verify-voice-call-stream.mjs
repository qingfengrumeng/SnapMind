// Verify sentence playback starts before the agent's final result, with mock services.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {installMockAsr} from './mock-asr.mjs'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage(),requests=[],errors=[];await installMockAsr(page);page.on('pageerror',e=>errors.push(e.message))
 await page.addInitScript(()=>{window.testAudios=[];window.Audio=class{constructor(){window.testAudios.push(this)}async play(){}pause(){}removeAttribute(){}load(){}}})
 await page.route('**/api/**',async r=>{const path=new URL(r.request().url()).pathname;if(path==='/api/speech/synthesize'){requests.push(r.request().postDataJSON().text);return r.fulfill({contentType:'audio/mpeg',body:Buffer.from('ID3fixture')})}return r.fulfill({json:path.endsWith('/image-title')?{title:'流式语音测试'}:r.request().method()==='PUT'?r.request().postDataJSON():{tools:[],items:[]}})})
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{const [{default:Spirit},{createApp}]=await Promise.all([import('/src/components/VoiceSpirit.vue'),import('/node_modules/.vite/deps/vue.js')]);const c=document.createElement('canvas');c.width=200;c.height=100;const host=document.createElement('div');document.body.append(host);window.spiritApp=createApp(Spirit,{asset:{id:'fixture',name:'Synthetic',width:200,height:100,data:c.toDataURL(),scenario:'custom'},annotations:[],anchor:{x:20,y:20,w:200,h:100},execute:async(request,signal,onChunk)=>{window.callSignal=signal;window.voiceDelta=onChunk;return await new Promise(resolve=>window.finishReply=resolve)}});window.spiritApp.mount(host)})
 await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'));assert.equal(await page.evaluate(()=>voiceInstances.length),0);await page.evaluate(()=>testAudios.at(-1).onended());await page.waitForFunction(()=>voiceInstances.length===1&&voiceInstances[0].binary.length>0)
 await page.evaluate(()=>voiceResult('请解释截图',''));assert.equal(await page.locator('.spirit-user').count(),0,'User ASR partials stay out of the assistant reply card');assert.equal(await page.evaluate(()=>window.voiceDelta!==undefined),false,'Partial ASR does not prematurely execute a tool')
 await page.evaluate(()=>voiceResult('请解释截图'));await page.waitForFunction(()=>typeof voiceDelta==='function')
 await page.evaluate(()=>voiceDelta('第一句已经生成。'));await page.waitForFunction(()=>document.querySelector('.voice-spirit')?.classList.contains('spirit-speaking'));assert.equal(requests.at(-1),'第一句已经生成。');assert.equal(await page.evaluate(()=>callSignal.aborted),false,'LLM request is still active when TTS starts')
 await page.evaluate(()=>voiceDelta('第二句接着生成。'));assert.equal(requests.length,2,'Later sentence queues while the first sentence plays')
 await page.evaluate(()=>testAudios.at(-1).onended());await page.waitForTimeout(60);assert.equal(requests.at(-1),'第二句接着生成。');assert.equal(requests.length,3,'Second sentence starts before final agent result')
 await page.evaluate(()=>finishReply({action:'chat',assetId:'fixture',answer:'第一句已经生成。第二句接着生成。',payload:{}}));await page.waitForTimeout(60);assert.equal(requests.length,3,'No duplicate whole-answer synthesis after the final result')
 await page.evaluate(()=>{window.previousDelta=voiceDelta;voiceResult('换个说法')});await page.waitForFunction(()=>voiceDelta!==previousDelta&&callSignal.aborted===false);await page.evaluate(()=>voiceDelta('新的回复。'));await page.waitForTimeout(60);assert.equal(requests.at(-1),'新的回复。');assert.equal(await page.evaluate(()=>voiceInstances.length),1,'Continuous ASR is not reconnected between turns')
 await page.evaluate(()=>spiritApp.unmount());assert.equal(await page.evaluate(()=>callSignal.aborted),true);assert.equal(await page.evaluate(()=>voiceInstances[0].readyState),3);assert.deepEqual(errors,[])
 console.log('PASS: ASR partials displayed immediately, persistent connection, sentence TTS while LLM result is still pending, ordered sentence playback, no duplicate final synthesis, interruption and unmount cancellation.')
}finally{await browser.close()}
