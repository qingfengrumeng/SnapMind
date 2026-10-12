// Explicit cloud smoke test with generated speech. Never opens a microphone.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
if(!process.argv.includes('--cloud'))throw Error('Pass --cloud to use the configured TTS/ASR services with a synthetic sentence.')
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage()
 // Keep the real local document origin, without mounting the app or saving sessions.
 await page.route('**/src/main.ts',r=>r.fulfill({contentType:'application/javascript',body:''}))
 await page.goto('http://127.0.0.1:5174')
 const agent=process.argv.includes('--agent')
 const result=await page.evaluate(async(agent)=>{
  const response=await fetch('/api/speech/synthesize',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:agent?'提取截图中的全部文字。':'你好，我是 SnapMind，正在测试语音识别。'})})
  if(!response.ok)throw Error('Synthetic TTS failed: '+response.status)
  const audio=new AudioContext(),decoded=await audio.decodeAudioData(await response.arrayBuffer());await audio.close()
  const recognition=await new Promise((resolve,reject)=>{
   const socket=new WebSocket('ws://127.0.0.1:5174/api/speech/recognize');let sent=0,finished=false,speechStarts=0
   const timer=setTimeout(()=>{socket.close();reject(Error('ASR smoke timeout'))},30000)
   socket.onerror=()=>{clearTimeout(timer);reject(Error('ASR socket failed'))}
   socket.onclose=()=>{if(!finished){clearTimeout(timer);reject(Error('ASR socket closed before completion'))}}
   socket.onmessage=async event=>{
    const data=JSON.parse(event.data)
    if(data.type==='error'){finished=true;clearTimeout(timer);socket.close();reject(Error(data.message))}
    else if(data.type==='speech-started')speechStarts++
    else if(data.type==='done'){finished=true;clearTimeout(timer);socket.close();resolve({text:data.text,pcmBytes:sent,speechStarts,source:'generated-test-speech'})}
    else if(data.type==='ready'){
     try{
      const offline=new OfflineAudioContext(1,Math.ceil(decoded.duration*data.sampleRate),data.sampleRate),source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start()
      const buffer=await offline.startRendering(),samples=buffer.getChannelData(0)
      for(let start=0;start<samples.length;start+=data.sampleRate/10){
       const slice=samples.subarray(start,start+data.sampleRate/10),pcm=new ArrayBuffer(slice.length*2),view=new DataView(pcm)
       slice.forEach((value,i)=>{const clipped=Math.max(-1,Math.min(1,value));view.setInt16(i*2,Math.round(clipped*(clipped<0?32768:32767)),true)})
       socket.send(pcm);sent+=pcm.byteLength;await new Promise(r=>setTimeout(r,100))
      }
      socket.send(JSON.stringify({type:'finish'}))
     }catch(error){finished=true;clearTimeout(timer);socket.close();reject(error)}
    }
   }
  })
  if(!agent)return recognition
  const canvas=document.createElement('canvas');canvas.width=500;canvas.height=160;const g=canvas.getContext('2d');g.fillStyle='white';g.fillRect(0,0,500,160);g.fillStyle='black';g.font='28px Arial';g.fillText('SnapMind voice test',30,75)
  const asset={id:'synthetic-voice-agent-test',name:'Synthetic test',data:canvas.toDataURL(),width:500,height:160,scenario:'custom'}
  const reply=await fetch('/api/capture/conversation?stream=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({assets:[asset],selectedId:asset.id,prompt:recognition.text,history:[],existing:[]})})
  if(!reply.ok)throw Error('Screenshot agent test failed: '+reply.status)
  const reader=reply.body.getReader(),decoderText=new TextDecoder();let pending='',answer,modelChunks=0
  while(true){const {done,value}=await reader.read();if(done)break;pending+=decoderText.decode(value,{stream:true});let end;while((end=pending.indexOf('\n\n'))>=0){const block=pending.slice(0,end);pending=pending.slice(end+2);const raw=block.split('\n').find(line=>line.startsWith('data:'))?.slice(5);if(!raw)continue;const event=JSON.parse(raw);if(event.type==='error')throw Error(event.message);if(event.type==='chunk')modelChunks++;if(event.type==='result')answer=event.result}}
  if(!answer?.answer.includes('SnapMind')||!modelChunks)throw Error('Screenshot agent did not stream the synthetic text')
  const voice=await fetch('/api/speech/synthesize?stream=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:answer.answer})});if(!voice.ok)throw Error('Reply TTS failed: '+voice.status)
  const decoder=new AudioContext();const replyAudio=await decoder.decodeAudioData(await voice.arrayBuffer());await decoder.close()
  return {...recognition,action:answer.action,modelChunks,replyAudioSeconds:replyAudio.duration}
 },agent)
 if(agent){assert.ok(result.text.includes('文字'));assert.equal(result.action,'ocr');assert.ok(result.replyAudioSeconds>0&&result.speechStarts>0)}else assert.ok(result.text.includes('你好')&&result.text.includes('语音识别'))
 console.log('PASS: real Qwen ASR'+(agent?' → screenshot agent → TTS':' through local WebSocket proxy')+', synthetic audio/image, no microphone or saved sessions; '+JSON.stringify(result))
}finally{await browser.close()}
