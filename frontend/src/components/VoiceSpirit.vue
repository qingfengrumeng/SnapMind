<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref,useId,watch} from 'vue'
import {AudioLines,Mic,MicOff,Pause,Play,PhoneOff,RotateCcw} from 'lucide-vue-next'
import type {AiExisting,AiTurn} from '../api'
import {api} from '../api'
import type {Asset,Message,Session,VoiceCallRecord} from '../types'
import {useSpeechInput} from '../speech-input'
import {useSpeechPlayer} from '../speech-player'
import {isSpeechFiller} from '../speech-turns'
import {spiritGreeting,speechText,type VoiceCallExecutor} from '../voice-call'
import {native} from '../desktop'
import '../voice-spirit.css'

const props=defineProps<{asset:Asset;rendered?:Asset;annotations:AiExisting[];anchor:{x:number;y:number;w:number;h:number};execute:VoiceCallExecutor}>()
const emit=defineEmits<{close:[]}>()
const uid=useId().replace(/:/g,''),root=ref<HTMLElement>(),position=ref({x:0,y:0}),jumping=ref(false),paused=ref(false),failure=ref(''),saveError=ref(''),transcript=ref(''),answer=ref(spiritGreeting),thinking=ref(false),elapsed=ref(0)
const messages=ref<Message[]>([]),sessionId='voicecall-'+crypto.randomUUID(),createdAt=new Date().toISOString()
const micMuted=ref(false)
const callAsset={...props.asset}
let callEndedAt:string|undefined
let disposed=false,controller:AbortController|undefined,version=0,title='与小洁的语音对话',titleGenerated=false,titlePending=false,saveQueue:Promise<unknown>=Promise.resolve(),drag:{id:number;x:number;y:number;left:number;top:number;moved:boolean}|undefined
let jumpTimer:ReturnType<typeof setTimeout>|undefined,listenTimer:ReturnType<typeof setTimeout>|undefined,clock:ReturnType<typeof setInterval>|undefined,observer:ResizeObserver|undefined
let speechQueue:string[]=[],speechPending='',speechBusy=false
const player=useSpeechPlayer(fail,()=>{speechBusy=false;pumpSpeech();scheduleListen()})
const speech=useSpeechInput(text=>{if(micMuted.value)return;transcript.value=text;if(text.trim()&&!paused.value&&!failure.value)interrupt()},recognized=>{const text=transcript.value.trim();if(disposed||micMuted.value||paused.value||failure.value)return;if(recognized&&text){void send(text)}else scheduleListen()}, {continuous:true,onUtterance:text=>{if(!disposed&&!micMuted.value&&!paused.value&&!failure.value)void send(text)},cancelOnBlur:false,onSpeechStart:()=>{if(!micMuted.value)interrupt()}})
const state=computed(()=>failure.value?'error':paused.value?'paused':player.state.value==='playing'?'speaking':player.state.value==='loading'?'synthesizing':thinking.value?'thinking':micMuted.value?'muted':speech.finishing.value?'recognizing':speech.starting.value?'connecting':'listening')
const status=computed(()=>({error:'连接需要检查',paused:'通话已暂停',thinking:'正在理解并执行',synthesizing:'正在准备语音',speaking:'小洁正在说话',muted:'麦克风已暂停',recognizing:'正在确认你的话',connecting:'正在连接麦克风',listening:'正在听你说话'})[state.value])
const duration=computed(()=>Math.floor(elapsed.value/60).toString().padStart(2,'0')+':'+(elapsed.value%60).toString().padStart(2,'0'))
function clamp(){const r=root.value;position.value={x:Math.max(8,Math.min(position.value.x,innerWidth-(r?.offsetWidth||300)-8)),y:Math.max(8,Math.min(position.value.y,innerHeight-(r?.offsetHeight||350)-8))}}
function place(){const r=root.value,width=r?.offsetWidth||280,height=r?.offsetHeight||350,a=props.anchor,reserve=innerWidth>=600?160:0;position.value={x:Math.min(a.x+a.w+width+reserve+24<innerWidth?a.x+a.w+16:Math.max(8,a.x+a.w-width-12),innerWidth-width-reserve-8),y:a.y+(a.h-height)/2};clamp()}
function bounce(){jumping.value=false;nextTick(()=>{if(disposed)return;jumping.value=true;clearTimeout(jumpTimer);jumpTimer=setTimeout(()=>jumping.value=false,650)})}
function beginDrag(e:PointerEvent){if(e.button!==0)return;drag={id:e.pointerId,x:e.clientX,y:e.clientY,left:position.value.x,top:position.value.y,moved:false};(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}
function moveDrag(e:PointerEvent){if(!drag||e.pointerId!==drag.id)return;const dx=e.clientX-drag.x,dy=e.clientY-drag.y;if(Math.hypot(dx,dy)>4)drag.moved=true;if(drag.moved){position.value={x:drag.left+dx,y:drag.top+dy};clamp()}}
function endDrag(e:PointerEvent){if(!drag||e.pointerId!==drag.id)return;const clicked=!drag.moved;drag=undefined;if(clicked&&e.type==='pointerup')bounce()}
function clearSpeech(){speechQueue=[];speechPending='';speechBusy=false;player.stop()}
function pumpSpeech(){if(speechBusy||!speechQueue.length||disposed||paused.value||failure.value)return;const text=speechQueue.shift()!;speechBusy=true;void player.play(signal=>api.synthesize(text,signal))}
function queueSpeech(text:string,flush=false){speechPending+=text;let match:RegExpExecArray|null;while((match=/^[\s\S]*?[。！？!?\n]|^[\s\S]{80}/.exec(speechPending))){const part=match[0];speechPending=speechPending.slice(part.length);const spoken=speechText(part);if(spoken)speechQueue.push(spoken)}if(flush&&speechPending.trim()){speechQueue.push(speechText(speechPending));speechPending=''}pumpSpeech()}
function interrupt(){if(disposed||paused.value||failure.value)return;version++;controller?.abort();controller=undefined;thinking.value=false;clearSpeech()}
function stopResources(){clearTimeout(listenTimer);version++;controller?.abort();controller=undefined;thinking.value=false;clearSpeech();speech.cancel()}
function fail(message:string){if(disposed)return;failure.value=message;stopResources()}
function scheduleListen(){clearTimeout(listenTimer);if(!disposed&&!micMuted.value&&!paused.value&&!failure.value&&!speech.active.value&&!speech.starting.value&&!speech.finishing.value)listenTimer=setTimeout(()=>{if(disposed||micMuted.value||paused.value||failure.value)return;transcript.value='';void speech.start('')},0)}
function hasCompletedExchange(){const [user,reply]=messages.value;return user?.role==='user'&&reply?.role==='assistant'&&!reply.failed&&!reply.paused&&!!reply.text.trim()}
function persist(){
 if(!hasCompletedExchange())return saveQueue
 const voiceCall:VoiceCallRecord={startedAt:createdAt,startMessageId:messages.value[0]!.id,endedAt:callEndedAt,endMessageId:callEndedAt?messages.value.at(-1)?.id:undefined}
 const value:Session={id:sessionId,title,scenario:'custom',assets:[{...props.asset}],messages:JSON.parse(JSON.stringify(messages.value)),voiceCall,formula:'',rows:[],createdAt,updatedAt:new Date().toISOString(),pinned:false,imageConversation:{version:1,selectedId:props.asset.id,pictures:[{assetId:props.asset.id,annotations:JSON.parse(JSON.stringify(props.annotations)),rendered:props.rendered}],titleGenerated}}
 saveQueue=saveQueue.catch(()=>{}).then(()=>api.save(value)).catch(e=>{if(!disposed)saveError.value=e instanceof Error?e.message:'会话保存失败'});return saveQueue
}
async function makeTitle(){if(titleGenerated||titlePending||disposed)return;titlePending=true;try{await saveQueue;const result=await api.imageTitle(sessionId);if(disposed)return;title=result.title.slice(0,18)||title;titleGenerated=true;await persist()}catch{/* Keep the saved call even if automatic naming is unavailable. */}finally{titlePending=false}}
async function send(text:string){
 if(isSpeechFiller(text))return
 if(!hasCompletedExchange())messages.value=[]
 interrupt();const own=version,run=new AbortController();controller=run;thinking.value=true;transcript.value='';const history:AiTurn[]=[{role:'assistant',text:spiritGreeting},...messages.value.filter(m=>!m.failed&&!m.paused).slice(-19).map(m=>({role:m.role,text:m.text.slice(0,2500)}))],turnId=crypto.randomUUID()
 messages.value.push({id:turnId,role:'user',text,images:messages.value.some(m=>m.role==='user')?undefined:[{...callAsset}]});await persist();if(run.signal.aborted||disposed)return
 // Keep listening during generation and playback so a new utterance can interrupt either.
 scheduleListen()
 let streamed=false
 try{const result=await props.execute({prompt:text,history,sessionId,turnId},AbortSignal.any([run.signal,AbortSignal.timeout(240000)]),chunk=>{if(run.signal.aborted||disposed||own!==version)return;if(!streamed){answer.value='';streamed=true}answer.value+=chunk;queueSpeech(chunk)});if(run.signal.aborted||disposed||own!==version)return
  answer.value=result.answer||'';messages.value.push({id:crypto.randomUUID(),role:'assistant',text:answer.value,action:result.action,imageOutput:result});thinking.value=false;controller=undefined;void persist();void makeTitle();queueSpeech(streamed?'':answer.value,true)
 }catch(e){if(!run.signal.aborted&&!disposed&&own===version){const message=e instanceof Error?e.message:'操作失败，请重试';messages.value.push({id:crypto.randomUUID(),role:'assistant',text:message,failed:true});void persist();fail(message)}}
 finally{if(controller===run){controller=undefined;thinking.value=false}}
}
function togglePause(){if(paused.value){paused.value=false;failure.value='';speech.error.value='';scheduleListen()}else{paused.value=true;stopResources()}}
function toggleMicrophone(){micMuted.value=!micMuted.value;if(micMuted.value){clearTimeout(listenTimer);speech.cancel();transcript.value=''}else scheduleListen()}
function retry(){failure.value='';speech.error.value='';paused.value=false;scheduleListen()}
async function openMicSettings(){try{await api.openMicrophoneSettings()}catch(e){failure.value=e instanceof Error?e.message:'请手动打开系统麦克风设置'}}
watch(speech.error,message=>{if(message&&message!=='未识别到语音，请重试')fail(message)})
onMounted(async()=>{await nextTick();place();observer=new ResizeObserver(clamp);if(root.value)observer.observe(root.value);window.addEventListener('resize',clamp);const start=Date.now();clock=setInterval(()=>elapsed.value=Math.floor((Date.now()-start)/1000),1000);await player.play(signal=>api.synthesize(spiritGreeting,signal))})
onBeforeUnmount(()=>{disposed=true;stopResources();callEndedAt=new Date().toISOString();void persist();clearTimeout(jumpTimer);clearInterval(clock);observer?.disconnect();window.removeEventListener('resize',clamp)})
defineExpose({stop:stopResources})
</script>
<template>
 <aside ref="root" class="voice-spirit" :class="'spirit-'+state" :style="{left:position.x+'px',top:position.y+'px'}" role="region" aria-label="小洁实时语音通话" @pointerdown.stop @pointermove.stop @pointerup.stop @contextmenu.prevent.stop @keydown.esc.stop.prevent="emit('close')">
  <div class="spirit-dialogue">
   <header><span class="spirit-name"><i/>小洁 <small>SnapMind AI 精灵</small></span><span class="spirit-duration">{{duration}}</span></header>
   <p class="spirit-answer" aria-live="polite">{{answer}}</p>
  <div v-if="failure" class="spirit-error-message" role="alert"><p>{{failure}}</p><div><button v-if="native&&/麦克风/.test(failure)" type="button" @click="openMicSettings"><Mic :size="12"/>打开麦克风设置</button><button type="button" @click="retry"><RotateCcw :size="12"/>重新连接</button></div></div>
   <p v-if="saveError" class="spirit-save-error" role="status">会话保存失败：{{saveError}}</p>
  </div>
  <button type="button" class="spirit-avatar" :class="{jumping}" aria-label="小洁精灵，点击互动，拖动移动" data-tooltip-disabled @pointerdown="beginDrag" @pointermove="moveDrag" @pointerup="endDrag" @pointercancel="endDrag" @lostpointercapture="drag=undefined" @click="e=>{if(e.detail===0)bounce()}">
   <svg class="spirit-art" viewBox="0 0 220 190" aria-hidden="true">
    <defs>
     <linearGradient :id="uid+'-body'" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#fff"/><stop offset=".45" stop-color="#e9ddff"/><stop offset="1" stop-color="#aa76f4"/></linearGradient>
     <linearGradient :id="uid+'-wing'" x1="0" y1="0" x2="1" y2="1"><stop stop-color="#d0fff0" stop-opacity=".9"/><stop offset="1" stop-color="#b39bff" stop-opacity=".6"/></linearGradient>
    </defs>
    <ellipse class="spirit-shadow" cx="110" cy="174" rx="42" ry="7" fill="#6c40a7" opacity=".13"/>
    <g class="spirit-floating">
     <g class="spirit-wings" :fill="'url(#'+uid+'-wing)'" stroke="#fff" stroke-opacity=".8" stroke-width="1.5"><path d="M79 106C44 100 22 70 41 64C67 57 77 78 88 96C57 67 24 104 52 119C68 128 82 114 89 109Z"/><path d="M141 106C176 100 198 70 179 64C153 57 143 78 132 96C163 67 196 104 168 119C152 128 138 114 131 109Z"/></g>
     <path d="M101 53Q86 32 96 23M119 52Q137 34 128 22" fill="none" stroke="#b78bee" stroke-width="3" stroke-linecap="round"/>
     <path d="m96 12 3 7 8 3-8 3-3 8-3-8-8-3 8-3Z" fill="#b398f5"/><circle cx="128" cy="20" r="5" fill="#a0eed5" stroke="white" stroke-width="2"/>
     <path d="M70 98C63 53 92 43 111 43C146 43 159 66 149 100C171 121 149 157 111 155C69 154 48 124 70 98Z" :fill="'url(#'+uid+'-body)'" stroke="white" stroke-width="2.5"/>
     <ellipse cx="110" cy="86" rx="32" ry="26" fill="#fff" opacity=".87"/>
     <g class="spirit-eyes"><ellipse cx="96" cy="86" rx="4.5" ry="7" fill="#51406f"/><ellipse cx="125" cy="86" rx="4.5" ry="7" fill="#51406f"/><circle cx="97" cy="84" r="1.6" fill="#fff"/><circle cx="126" cy="84" r="1.6" fill="#fff"/></g>
     <ellipse cx="86" cy="98" rx="7" ry="3.5" fill="#f6bddc" opacity=".7"/><ellipse cx="136" cy="98" rx="7" ry="3.5" fill="#f6bddc" opacity=".7"/>
     <path class="spirit-mouth" d="M104 99Q110 106 117 99" fill="none" stroke="#796091" stroke-width="2.5" stroke-linecap="round"/>
     <path d="M101 128C89 117 95 109 103 114L110 121L117 114C125 109 131 117 119 128L110 136Z" fill="#8750df" opacity=".75"/>
     <path d="M65 114Q51 118 56 128M154 114Q168 118 163 128" fill="none" stroke="#dec4fc" stroke-width="8" stroke-linecap="round"/>
     <path d="M92 151Q88 163 82 157M127 151Q133 163 140 157" fill="none" stroke="#ccb0f2" stroke-width="8" stroke-linecap="round"/>
     <path class="spirit-sparkle" d="m179 40 3 7 8 3-8 3-3 8-3-8-8-3 8-3Z" fill="#b290f4"/><circle cx="39" cy="138" r="3" fill="#98dec9"/>
    </g>
   </svg>
  </button>
  <div class="spirit-call-controls">
   <div class="spirit-call-status" role="status"><span v-if="['connecting','thinking','synthesizing','recognizing'].includes(state)" class="spirit-wait-indicator" aria-hidden="true"><i/><i/><i/></span><AudioLines v-else-if="state==='speaking'" :size="14"/><Mic v-else :size="14"/><span>{{status}}</span><small v-if="speech.active.value">麦克风已开启</small></div>
   <div class="spirit-call-buttons"><button type="button" class="spirit-microphone" :class="{muted:micMuted}" :aria-pressed="micMuted" :aria-label="micMuted?'恢复接收语音':'暂停接收语音'" :title="micMuted?'恢复接收语音':'暂停接收语音'" @click="toggleMicrophone"><MicOff v-if="micMuted" :size="15"/><Mic v-else :size="15"/></button><button type="button" :aria-label="paused?'继续通话':'暂停通话'" :title="paused?'继续通话':'暂停通话'" @click="togglePause"><Play v-if="paused" :size="15"/><Pause v-else :size="15"/></button><button type="button" class="spirit-hangup" aria-label="结束通话" title="结束通话" @click="emit('close')"><PhoneOff :size="15"/></button></div>
  </div>
 </aside>
</template>
