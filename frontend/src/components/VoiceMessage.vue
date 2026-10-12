<script setup lang="ts">
import {computed,onBeforeUnmount,ref} from 'vue'
import type {VoiceMessage} from '../types'
import Icon from './Icon.vue'
const props=defineProps<{voice:VoiceMessage;text:string}>()
const emit=defineEmits<{error:[message:string];play:[]}>()
const playing=ref(false),expanded=ref(false)
let audio:HTMLAudioElement|undefined
const bars=computed(()=>{const levels=props.voice.waveform,count=Math.min(18,levels.length);return Array.from({length:count},(_,i)=>Math.max(...levels.slice(Math.floor(i*levels.length/count),Math.floor((i+1)*levels.length/count))))})
const time=computed(()=>{const value=Math.max(1,Math.ceil(props.voice.duration));return Math.floor(value/60).toString().padStart(2,'0')+':'+(value%60).toString().padStart(2,'0')})
function stop(){audio?.pause();playing.value=false}
async function toggle(){
 if(playing.value){stop();return}
 if(!audio){audio=new Audio(props.voice.data);audio.onended=()=>{playing.value=false};audio.onerror=()=>{playing.value=false;emit('error','语音播放失败，请重试')}}
 emit('play');try{await audio.play();playing.value=true}catch{playing.value=false;emit('error','无法播放这条语音，请重试')}
}
onBeforeUnmount(()=>{stop();if(audio){audio.onended=null;audio.onerror=null;audio.ontimeupdate=null;audio.removeAttribute('src');audio.load()}})
defineExpose({stop})
</script>
<template>
 <div class="chat-voice-message" :class="{playing}">
  <div class="chat-voice-row"><button type="button" class="chat-voice-transcribe" :aria-label="expanded?'收起识别文字':'语音转文字'" :data-tooltip="expanded?'收起识别文字':'语音转文字'" :aria-expanded="expanded" @click="expanded=!expanded"><Icon name="file" :size="19"/></button><button type="button" class="chat-voice-bar" :aria-label="playing?'暂停语音':'播放语音'" :aria-pressed="playing" @click="toggle"><span class="chat-voice-duration">{{time}}</span><span class="chat-voice-play"><Icon :name="playing?'pause':'play'" :size="18"/></span><span class="chat-voice-wave" aria-hidden="true"><i v-for="(level,index) in bars" :key="index" :style="{height:(4+Math.sqrt(level)*24)+'px',animationDelay:index*.045+'s'}"/></span></button></div>
  <div v-if="expanded" class="chat-voice-transcript">{{text}}</div>
 </div>
</template>
