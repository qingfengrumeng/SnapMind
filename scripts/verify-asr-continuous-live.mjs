// Synthetic speech only, one persistent ASR connection, no microphone/history.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
if(!process.argv.includes('--cloud'))throw Error('Pass --cloud for synthetic ASR verification.')
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage();await page.route('**/src/main.ts',r=>r.fulfill({contentType:'application/javascript',body:''}));await page.goto('http://127.0.0.1:5174')
 const result=await page.evaluate(async()=>{
  const response=await fetch('/api/speech/synthesize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'请提取截图文字。'})});if(!response.ok)throw Error('Test TTS failed')
  const context=new AudioContext(),decoded=await context.decodeAudioData(await response.arrayBuffer());await context.close()
  return await new Promise((resolve,reject)=>{
   const socket=new WebSocket('ws://127.0.0.1:5174/api/speech/recognize?continuous=true'),utterances=[];let partials=0,closed=false,rate=16000,samples,uploading=Promise.resolve()
   const timer=setTimeout(()=>{closed=true;socket.close();reject(Error('Continuous ASR test timeout'))},30000)
   function fail(message){closed=true;clearTimeout(timer);socket.close();reject(Error(message))}
   async function send(){try{const all=new Float32Array(samples.length+rate);all.set(samples);for(let p=0;p<all.length&&!closed;p+=rate/10){const chunk=all.subarray(p,p+rate/10),pcm=new ArrayBuffer(chunk.length*2),v=new DataView(pcm);chunk.forEach((s,i)=>v.setInt16(i*2,Math.round(Math.max(-1,Math.min(1,s))*(s<0?32768:32767)),true));socket.send(pcm);await new Promise(r=>setTimeout(r,100))}}catch(e){if(!closed)fail(e.message)}}
   socket.onerror=()=>fail('Continuous ASR connection failed');socket.onclose=()=>{if(!closed)fail('Continuous ASR closed before two turns')}
   socket.onmessage=async event=>{const data=JSON.parse(event.data);if(data.type==='error'){fail(data.message);return}
    if(data.type==='transcript'&&!data.confirmed)partials++
    if(data.type==='utterance'){utterances.push(data.text);if(utterances.length===1){await uploading;await new Promise(r=>setTimeout(r,400));uploading=send()}else if(utterances.length===2){closed=true;clearTimeout(timer);socket.send(JSON.stringify({type:'cancel'}));socket.close();resolve({utterances,partials,connections:1,finishCommands:0})}}
    if(data.type==='ready'){rate=data.sampleRate;const offline=new OfflineAudioContext(1,Math.ceil(decoded.duration*rate),rate),source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();samples=(await offline.startRendering()).getChannelData(0);uploading=send()}
   }
  })
 })
 console.log(JSON.stringify(result));assert.equal(result.utterances.length,2);assert.ok(result.utterances.every(text=>text.includes('截图')&&text.includes('文字')));assert.ok(result.partials>0)
 console.log('PASS: real continuous ASR, incremental transcript and two finalized turns on one socket without session.finish; '+JSON.stringify(result))
}finally{await browser.close()}
