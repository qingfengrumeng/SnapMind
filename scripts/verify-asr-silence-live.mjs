// Send digitally silent PCM to the real ASR endpoint. No microphone or history.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
if(!process.argv.includes('--cloud'))throw Error('Pass --cloud for the cloud ASR silence check.')
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage();await page.route('**/src/main.ts',r=>r.fulfill({contentType:'application/javascript',body:''}));await page.goto('http://127.0.0.1:5174')
 const result=await page.evaluate(()=>new Promise((resolve,reject)=>{
  const socket=new WebSocket('ws://127.0.0.1:5174/api/speech/recognize?continuous=true'),transcripts=[],utterances=[];let finished=false,speechStarts=0
  const timer=setTimeout(()=>{finished=true;socket.close();reject(Error('Silent ASR test timed out'))},15000)
  socket.onerror=()=>{finished=true;clearTimeout(timer);reject(Error('Silent ASR connection failed'))}
  socket.onmessage=async event=>{const data=JSON.parse(event.data);if(data.type==='error'){finished=true;clearTimeout(timer);socket.close();reject(Error(data.message))}
   if(data.type==='transcript')transcripts.push(data.text);if(data.type==='utterance')utterances.push(data.text);if(data.type==='speech-started')speechStarts++
   if(data.type==='done'){finished=true;clearTimeout(timer);socket.close();resolve({text:data.text,transcripts,utterances,speechStarts})}
   if(data.type==='ready'){for(let i=0;i<20&&!finished;i++){socket.send(new ArrayBuffer(data.sampleRate/10*2));await new Promise(r=>setTimeout(r,100))}if(!finished)socket.send(JSON.stringify({type:'finish'}))}
  }
 }))
 assert.deepEqual(result,{text:'',transcripts:[],utterances:[],speechStarts:0})
 console.log('PASS: real ASR with 2 seconds of silent PCM returns no transcript, no utterance and no speech event; no microphone or saved data.')
}finally{await browser.close()}
