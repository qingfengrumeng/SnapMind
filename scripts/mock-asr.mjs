// Fake local ASR transport and microphone; no cloud calls or real recording.
export async function installMockAsr(page){
 await page.addInitScript(()=>{
  const OriginalWebSocket=window.WebSocket
  window.voiceInstances=[];window.mediaStops=0;window.audioCloses=0
  window.WebSocket=class{
   static OPEN=1
   constructor(url){if(!String(url).includes('/speech/recognize'))return new OriginalWebSocket(url);this.continuous=String(url).includes('continuous=true');this.readyState=1;this.aborts=0;this.stops=0;this.binary=[];this.text='';window.voiceInstances.push(this);if(!window.deferVoiceStart)queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({type:'ready',sampleRate:16000})}))}
   send(data){if(typeof data!=='string'){this.binary.push(data);return}const control=JSON.parse(data);if(control.type==='finish'){this.stops++;if(!window.deferVoiceFinish)queueMicrotask(()=>this.onmessage?.({data:JSON.stringify({type:'done',text:this.text})}))}}
   close(){this.readyState=3;this.aborts++}
  }
  Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{if(window.denyMic)throw new DOMException('Denied','NotAllowedError');return {getTracks:()=>[{stop:()=>window.mediaStops++}]}}})
  window.AudioContext=class{constructor(){this.audioWorklet={addModule:async()=>{}};this.destination={}}async resume(){}async close(){window.audioCloses++}createMediaStreamSource(){return {connect(){},disconnect(){}}}}
  window.AudioWorkletNode=class{constructor(){this.port={onmessage:null,postMessage:()=>queueMicrotask(()=>this.port.onmessage?.({data:{flushed:true}}))};queueMicrotask(()=>this.port.onmessage?.({data:new ArrayBuffer(640)}))}connect(){}disconnect(){}}
  window.voiceResult=(text,confirmed=text)=>{const ws=window.voiceInstances.at(-1);ws.text=confirmed;ws.onmessage?.({data:JSON.stringify({type:'transcript',text,confirmed})});if(ws.continuous&&confirmed)ws.onmessage?.({data:JSON.stringify({type:'utterance',text:confirmed})})}
 })
}
