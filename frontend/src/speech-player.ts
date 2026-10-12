import {ref,onBeforeUnmount} from 'vue'

export function useSpeechPlayer(onError:(message:string)=>void,onEnded?:()=>void){
 const state=ref<'idle'|'loading'|'playing'|'paused'>('idle')
 let audio:HTMLAudioElement|undefined,controller:AbortController|undefined,url:string|undefined,reader:ReadableStreamDefaultReader<Uint8Array>|undefined,version=0
 function stop(){version++;controller?.abort();controller=undefined;void reader?.cancel().catch(()=>{});reader=undefined;if(audio){audio.onended=null;audio.onerror=null;audio.pause();audio.removeAttribute('src');audio.load();audio=undefined}if(url)URL.revokeObjectURL(url);url=undefined;state.value='idle'}
 function wait(target:EventTarget,event:string,signal:AbortSignal){return new Promise<void>((resolve,reject)=>{const clear=()=>{target.removeEventListener(event,done);target.removeEventListener('error',bad);signal.removeEventListener('abort',abort)},done=()=>{clear();resolve()},bad=()=>{clear();reject(new Error('音频解码失败，请重新试听'))},abort=()=>{clear();reject(signal.reason)};if(signal.aborted){reject(signal.reason);return}target.addEventListener(event,done,{once:true});target.addEventListener('error',bad,{once:true});signal.addEventListener('abort',abort,{once:true})})}
 async function play(fetchAudio:(signal:AbortSignal)=>Promise<Response>){
  stop();const own=version,run=new AbortController();controller=run;state.value='loading'
  try{
   const response=await fetchAudio(run.signal);if(own!==version){void response.body?.cancel();return}
   const media=new Audio();audio=media
   media.onended=()=>{if(own===version){stop();onEnded?.()}}
   media.onerror=()=>{if(own===version){stop();onError('音频播放失败，请重新试听')}}
   if(typeof MediaSource==='undefined'||!MediaSource.isTypeSupported('audio/mpeg')||typeof media.addEventListener!=='function'){
    const blob=await response.blob();if(own!==version)return;if(!blob.size)throw Error('语音服务返回了空音频');url=URL.createObjectURL(blob);media.src=url;await media.play();if(own===version)state.value='playing';return
   }
   const source=new MediaSource(),opened=wait(source,'sourceopen',run.signal);url=URL.createObjectURL(source);media.src=url;media.preload='auto';await opened
   if(own!==version)return
   const buffer=source.addSourceBuffer('audio/mpeg');reader=response.body!.getReader();let first=true,total=0,playing:Promise<void>|undefined
   while(own===version){
    const {done,value}=await reader.read();if(own!==version)return;if(done)break;if(!value.byteLength)continue
    total+=value.byteLength;if(total>32_000_000)throw Error('生成音频过大，请分段朗读')
    const appended=wait(buffer,'updateend',run.signal);try{buffer.appendBuffer(new Uint8Array(value))}catch(e){run.abort();await appended.catch(()=>{});throw e}await appended
    if(first){first=false;playing=media.play().then(()=>{if(own===version&&state.value!=='paused')state.value='playing'});void playing.catch(e=>{if(own===version){stop();onError(e instanceof Error?e.message:'音频播放失败，请重新试听')}})}
   }
   if(own!==version)return
   if(!total)throw Error('语音服务返回了空音频');reader.releaseLock();reader=undefined;if(source.readyState==='open')source.endOfStream();await playing
  }catch(e){if(own!==version)return;stop();onError(e instanceof Error?e.message:'语音合成失败，请重试')}
 }
 function pause(){if(state.value==='playing'&&audio){audio.pause();state.value='paused'}}
 async function resume(){if(state.value!=='paused'||!audio)return;const own=version;try{await audio.play();if(own===version)state.value='playing'}catch{if(own===version){stop();onError('音频播放失败，请重新试听')}}}
 onBeforeUnmount(stop)
 return {state,play,pause,resume,stop}
}
