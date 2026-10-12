import {ref,onMounted,onBeforeUnmount} from 'vue'
import {api} from './api'
import {createSpeechTurns,isSpeechFiller} from './speech-turns'
import {pcmRecording} from './voice-recording'
import type {VoiceMessage} from './types'

export function useSpeechInput(update:(text:string)=>void,finished:(recognized:boolean)=>void,options:{autoFinish?:boolean;continuous?:boolean;onUtterance?:(text:string)=>void;cancelOnBlur?:boolean;onSpeechStart?:()=>void;record?:()=>boolean;onRecording?:(recording:VoiceMessage)=>void}={}){
 const active=ref(false),starting=ref(false),finishing=ref(false),error=ref(''),seconds=ref(0)
 let socket:WebSocket|undefined,stream:MediaStream|undefined,context:AudioContext|undefined,node:AudioWorkletNode|undefined,source:MediaStreamAudioSourceNode|undefined
 let version=0,disposed=false,prefix='',suffix='',selection='',confirmed='',finishSent=false,stopRequested=false,startedAt=0
 let timer:ReturnType<typeof setTimeout>|undefined,flushTimer:ReturnType<typeof setTimeout>|undefined,tick:ReturnType<typeof setInterval>|undefined
 let rejectStart:((reason:Error)=>void)|undefined
 let frames:ArrayBuffer[]=[],recording=false,recordRate=16000,recordBytes=0
 const turns=createSpeechTurns(text=>{if(disposed||!socket)return;confirmed='';update('');options.onUtterance?.(text)})
 function releaseMedia(){if(node){node.port.onmessage=null;node.disconnect();node=undefined}source?.disconnect();source=undefined;stream?.getTracks().forEach(track=>track.stop());stream=undefined;context?.close().catch(()=>{});context=undefined;clearInterval(tick)}
 function close(){frames=[];recordBytes=0;recording=false;turns.reset();version++;rejectStart?.(new Error('录音已取消'));rejectStart=undefined;clearTimeout(timer);clearTimeout(flushTimer);releaseMedia();if(socket){socket.onopen=null;socket.onmessage=null;socket.onerror=null;socket.onclose=null;socket.close();socket=undefined}active.value=false;starting.value=false;finishing.value=false}
 function cancel(){if(active.value||starting.value||finishing.value)update((prefix+(confirmed||selection)+suffix).slice(0,3000));close()}
 function failure(message:string){error.value=message;cancel()}
 async function start(text:string,from=text.length,to=from){
  if(socket||disposed)return
  error.value='';prefix=text.slice(0,from);suffix=text.slice(to);selection=text.slice(from,to);confirmed='';seconds.value=0;stopRequested=false;finishSent=false;starting.value=true
  frames=[];recordBytes=0;recording=!!options.record?.()&&!options.continuous
  const own=++version
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw new Error('当前环境无法使用麦克风，请检查系统权限')
   const url=new URL(api.speechSocketUrl());if(options.continuous)url.searchParams.set('continuous','true');const ws=new WebSocket(url.href);socket=ws
   const ready=new Promise<number>((resolve,reject)=>{
    rejectStart=reject
    ws.onmessage=event=>{try{const data=JSON.parse(event.data);if(data.type==='ready')resolve(data.sampleRate);else if(data.type==='error')reject(new Error(data.message))}catch{reject(new Error('语音服务返回异常'))}}
    ws.onerror=()=>reject(new Error('无法连接语音识别服务，请检查本地后端和网络'))
    ws.onclose=()=>reject(new Error('语音识别连接已关闭'))
   })
   timer=setTimeout(()=>failure('语音识别连接超时，请重试'),15000)
   const sampleRate=await ready
   recordRate=sampleRate
   rejectStart=undefined
   if(own!==version)return
   if(![8000,16000].includes(sampleRate))throw new Error('语音服务采样率无效')
   clearTimeout(timer)
   ws.onmessage=event=>{
    if(own!==version)return
    try{
     const data=JSON.parse(event.data)
     if(data.type==='speech-started'){turns.speechStarted();options.onSpeechStart?.()}
     else if(data.type==='transcript'){
      if(options.continuous&&typeof data.text==='string'&&isSpeechFiller(data.text))return
      confirmed=data.confirmed||'';const next=prefix+(options.continuous&&turns.text()?turns.text()+' ':'')+data.text+suffix
      if(next.length>3000){failure('识别文字超过输入框限制，请分段说话');return}update(next)
      if(options.autoFinish&&!options.continuous&&confirmed.trim())stop()
     }else if(data.type==='utterance'&&options.continuous){
      confirmed='';if(typeof data.text==='string'&&data.text.trim())turns.push(data.text)
     }else if(data.type==='done'){
      const result=data.text||'';if(result.trim()&&recording)options.onRecording?.(pcmRecording(frames,recordRate));update((prefix+(result||selection)+suffix).slice(0,3000));close()
      if(!result.trim()){error.value='未识别到语音，请重试';finished(false)}else finished(true)
     }else if(data.type==='error'){confirmed=data.confirmed||confirmed;failure(data.message||'语音识别失败，请重试')}
    }catch{failure('语音识别返回异常，请重试')}
   }
   ws.onerror=()=>{if(own===version)failure('语音识别连接失败，请重试')}
   ws.onclose=()=>{if(own===version)failure('语音识别连接中断，请重试')}
   timer=setTimeout(()=>failure('麦克风开启超时，请检查权限后重试'),30000)
   const media=await navigator.mediaDevices.getUserMedia({audio:{channelCount:1,echoCancellation:true,noiseSuppression:true,autoGainControl:true},video:false})
   if(own!==version){media.getTracks().forEach(track=>track.stop());return}stream=media
   const audio=new AudioContext();context=audio
   await audio.audioWorklet.addModule('/speech-capture-worklet.js')
   if(own!==version)return
   await audio.resume();if(own!==version)return
   const capture=new AudioWorkletNode(audio,'snapmind-pcm',{processorOptions:{sampleRate}});node=capture
   capture.port.onmessage=event=>{
    if(own!==version)return
    if(event.data.flushed){sendFinish();return}
    if(ws.readyState!==WebSocket.OPEN||finishSent)return
    if(recording&&event.data instanceof ArrayBuffer){recordBytes+=event.data.byteLength;if(recordBytes>recordRate*2*120){failure('录音超过两分钟，请分段发送');return}frames.push(event.data.slice(0))}
    if(ws.bufferedAmount>sampleRate*2*5){failure('语音上传速度不足，请检查网络后重试');return}
    ws.send(event.data)
   }
   source=audio.createMediaStreamSource(media);source.connect(capture);capture.connect(audio.destination)
   starting.value=false;active.value=true;startedAt=Date.now();clearTimeout(timer)
   tick=setInterval(()=>seconds.value=Math.floor((Date.now()-startedAt)/1000),250)
   timer=setTimeout(stop,options.continuous?1800000:120000)
  }catch(e){if(own!==version)return;const names:Record<string,string>={NotAllowedError:'麦克风权限未开启，请在系统或浏览器设置中允许访问',NotFoundError:'未找到麦克风，请连接录音设备',NotReadableError:'无法使用麦克风，设备可能正被占用'};const systemDenied=e instanceof Error&&e.name==='NotAllowedError'&&/by system/i.test(e.message);failure(systemDenied?'Windows 拒绝了麦克风访问。请检查“麦克风访问”和“允许桌面应用访问麦克风”，开启后点击重新连接。':e instanceof Error?(names[e.name]||e.message):'无法启动语音识别')}
 }
 function sendFinish(){if(!socket||finishSent)return;finishSent=true;clearTimeout(flushTimer);releaseMedia();if(socket.readyState===WebSocket.OPEN)socket.send(JSON.stringify({type:'finish'}));timer=setTimeout(()=>failure('语音识别收尾超时，请重试'),30000)}
 function stop(){if(!socket||stopRequested)return;stopRequested=true;if(starting.value){cancel();return}active.value=false;finishing.value=true;clearTimeout(timer);clearInterval(tick);node?.port.postMessage('flush');flushTimer=setTimeout(sendFinish,100)}
 function blurred(){if(options.cancelOnBlur!==false&&(active.value||finishing.value))cancel()}
 onMounted(()=>window.addEventListener('blur',blurred))
 onBeforeUnmount(()=>{disposed=true;cancel();window.removeEventListener('blur',blurred)})
 return {active,starting,finishing,error,seconds,start,stop,cancel}
}
