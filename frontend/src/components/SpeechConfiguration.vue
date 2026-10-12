<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount,watch} from 'vue'
import {ChevronDown,Plus,Check,LoaderCircle,Zap,Volume2,Pause,ShieldCheck,Eye,EyeOff,RefreshCw} from 'lucide-vue-next'
import {api,type SpeechInput,type SpeechProfile,type SpeechRegistry,type SpeechVoice} from '../api'
import {useSpeechPlayer} from '../speech-player'
import ModelSelect from './ModelSelect.vue'
defineProps<{kind:'asr'|'tts'}>()
interface Draft extends SpeechInput{apiKey:string;showKey:boolean;busy:boolean;error:string;message:string;baseline:string}
const registry=ref<SpeechRegistry>({activeAsrId:null,activeTtsId:null,profiles:[]}),drafts=ref<Record<string,Draft>>({}),expanded=ref<string>(),loading=ref(true),error=ref(''),switching=ref(false),previewId=ref<string>()
const previewVoice=ref(''),voiceLists=ref<Record<string,{model:string;voices:SpeechVoice[]}>>({}),fetching=ref<Record<string,boolean>>({}),requests=new Map<string,AbortController>()
const modelLists=ref<Record<string,{signature:string;names:string[]}>>({}),modelFetching=ref<Record<string,boolean>>({}),modelRequests=new Map<string,AbortController>(),manualModels=ref<Record<string,boolean>>({})
const groups=[{kind:'asr' as const,title:'ASR · 语音识别',description:'语音转文字与语音输入'},{kind:'tts' as const,title:'TTS · 语音合成',description:'消息朗读与音色设置'}]
const player=useSpeechPlayer(message=>{if(previewId.value)drafts.value[previewId.value]!.error=message})
function active(kind:'asr'|'tts'){return registry.value.profiles.find(p=>p.id===registry.value[kind==='asr'?'activeAsrId':'activeTtsId'])}
function payload(d:Draft):SpeechInput{return {name:d.name,kind:d.kind,provider:'dashscope',baseUrl:d.baseUrl,model:d.model,voice:d.voice,sampleRate:d.sampleRate,rate:d.rate,volume:d.volume,pitch:d.pitch,language:d.language||'zh',apiKey:d.apiKey||undefined,clearApiKey:d.clearApiKey}}
function fingerprint(d:Draft){return JSON.stringify(payload(d))}
function dirty(id:string){const d=drafts.value[id]!;return fingerprint(d)!==d.baseline}
function apply(value:SpeechRegistry,id?:string){registry.value=value;for(const p of value.profiles){if(!drafts.value[p.id]||p.id===id){const d:Draft={...p,apiKey:'',language:p.language||'zh',clearApiKey:false,showKey:false,busy:false,error:'',message:'',baseline:''};d.baseline=fingerprint(d);drafts.value[p.id]=d}}}
async function load(){loading.value=true;error.value='';try{apply(await api.speech())}catch(e){error.value=e instanceof Error?e.message:'语音配置加载失败'}finally{loading.value=false}}
function add(kind:'asr'|'tts'){const id=crypto.randomUUID(),count=registry.value.profiles.filter(p=>p.kind===kind).length;const p:SpeechProfile={id,name:'Qwen '+kind.toUpperCase()+(count?' '+(count+1):''),kind,provider:'dashscope',baseUrl:'',model:kind==='tts'?'qwen-audio-3.1-tts-flash':'qwen3-asr-flash-realtime',voice:'longanwen_v3.1',sampleRate:kind==='tts'?22050:16000,rate:1,volume:50,pitch:1,language:'zh',hasApiKey:false};apply({...registry.value,profiles:[...registry.value.profiles,p]},id);drafts.value[id]!.baseline='';expanded.value=id}
async function save(id:string){const d=drafts.value[id]!;d.busy=true;d.error='';player.stop();try{apply(await api.saveSpeech(id,payload(d)),id);drafts.value[id]!.message='配置已保存，请按需启用'}catch(e){d.error=e instanceof Error?e.message:'保存失败'}finally{drafts.value[id]!.busy=false}}
async function enable(p:SpeechProfile){if(switching.value)return;const d=drafts.value[p.id]!;expanded.value=p.id;d.error='';if(dirty(p.id)){d.error='请先保存修改，再启用此配置';return}switching.value=true;try{const id=registry.value[p.kind==='tts'?'activeTtsId':'activeAsrId'];apply(await api.activateSpeech(p.kind,id===p.id?null:p.id));player.stop()}catch(e){d.error=e instanceof Error?e.message:'启用失败'}finally{switching.value=false}}
async function test(id:string){const d=drafts.value[id]!;d.busy=true;d.error='';d.message='';try{const result=await api.testSpeech(id,payload(d));if(result.ok)d.message='连接成功 · '+result.latencyMs+' ms（WebSocket 鉴权）';else d.error=result.error||'连接失败'}catch(e){d.error=e instanceof Error?e.message:'连接失败'}finally{d.busy=false}}
function voices(id:string){return voiceLists.value[id]?.model===drafts.value[id]!.model.trim()?voiceLists.value[id]!.voices:[]}
function voiceOptions(id:string){return [...new Set([drafts.value[id]!.voice,...voices(id).map(v=>v.id)].filter(Boolean))]}
function voiceLabels(id:string){return Object.fromEntries(voices(id).map(v=>[v.id,v.name+' · '+v.id]))}
function voiceDescriptions(id:string){return Object.fromEntries(voices(id).map(v=>[v.id,v.description]))}
function modelSignature(id:string){const d=drafts.value[id]!;return JSON.stringify([d.kind,d.baseUrl.trim(),d.apiKey.trim(),!!d.clearApiKey])}
function modelList(id:string){const list=modelLists.value[id];return list?.signature===modelSignature(id)?list:undefined}
async function fetchModels(id:string){
 modelRequests.get(id)?.abort();const controller=new AbortController();modelRequests.set(id,controller);modelFetching.value[id]=true
 const d=drafts.value[id]!,signature=modelSignature(id);d.error='';d.message=''
 try{const result=await api.speechModels(id,payload(d),controller.signal);if(!controller.signal.aborted&&signature===modelSignature(id)&&result.kind===d.kind){modelLists.value[id]={signature,names:result.models};manualModels.value[id]=false;d.message=result.models.length?'已获取 '+result.models.length+' 个 '+d.kind.toUpperCase()+' 模型':'接口未返回对应的 '+d.kind.toUpperCase()+' 模型，可手动输入模型名称'}}
 catch(e){if(!controller.signal.aborted)d.error=e instanceof Error?e.message:'获取模型列表失败'}
 finally{if(modelRequests.get(id)===controller){modelRequests.delete(id);modelFetching.value[id]=false}}
}
async function fetchVoices(id:string){
 requests.get(id)?.abort();const controller=new AbortController();requests.set(id,controller);fetching.value[id]=true;const d=drafts.value[id]!,config=payload(d);d.error='';d.message=''
 try{const result=await api.speechVoices(id,config,controller.signal);if(!controller.signal.aborted&&drafts.value[id]!.model.trim()===result.model){voiceLists.value[id]=result;d.message='已获取 '+result.voices.length+' 个官方系统音色'}}
 catch(e){if(!controller.signal.aborted)d.error=e instanceof Error?e.message:'获取音色列表失败'}
 finally{if(requests.get(id)===controller){requests.delete(id);fetching.value[id]=false}}
}
function previewing(id:string,voice:string){return previewId.value===id&&previewVoice.value===voice}
async function preview(id:string,voice=drafts.value[id]!.voice){const d=drafts.value[id]!;d.error='';if(previewing(id,voice)&&player.state.value!=='idle'){if(player.state.value==='loading')player.stop();else if(player.state.value==='paused')await player.resume();else player.pause();return}previewId.value=id;previewVoice.value=voice;const config={...payload(d),voice},english=voices(id).find(v=>v.id===voice)?.language==='en';await player.play(signal=>api.previewSpeech(id,{...config,...(english?{text:'Hello! This is a preview of my voice. How can I help you today?'}:{})},signal))}
function previewLabel(id:string,voice=drafts.value[id]!.voice){return previewing(id,voice)?(player.state.value==='loading'?'取消试听':player.state.value==='playing'?'暂停试听':player.state.value==='paused'?'继续试听':'试听音色'):'试听音色'}
function stopPreview(){player.stop();for(const [id,controller] of requests){controller.abort();fetching.value[id]=false}requests.clear();for(const [id,controller] of modelRequests){controller.abort();modelFetching.value[id]=false}modelRequests.clear()}
watch(expanded,()=>stopPreview())
watch(()=>JSON.stringify(Object.values(drafts.value).map(payload)),()=>player.stop())
onBeforeUnmount(stopPreview)
defineExpose({stopPreview})
onMounted(load)
</script>
<template>
 <div class="model-profiles speech-profiles">
  <p v-if="loading" class="model-profiles-loading"><LoaderCircle :size="16"/>正在加载配置…</p><p v-if="error" class="profile-feedback" role="alert">{{error}} <button @click="load">重试</button></p>
  <template v-if="!loading&&!error">
   <section v-for="group in groups.filter(g=>g.kind===kind)" :key="group.kind" class="speech-config-section" :aria-label="group.title">
    <div class="speech-config-actions"><button class="model-add" :aria-label="'添加 '+group.kind.toUpperCase()+' 配置'" :disabled="registry.profiles.length>=30" @click="add(group.kind)"><Plus :size="15"/>添加配置</button></div>
    <div class="model-active-summary"><span class="model-active-dot" :class="{enabled:!!active(group.kind)}"/><span>{{active(group.kind)?'当前启用：'+active(group.kind)!.name+' · '+active(group.kind)!.model:'尚未启用 '+group.kind.toUpperCase()+' 模型'}}</span><small>保存不等于启用</small></div>
    <div class="model-profile-list">
   <article v-for="p in registry.profiles.filter(p=>p.kind===group.kind)" :key="p.id" class="model-profile" :class="{expanded:expanded===p.id}">
    <div class="model-profile-row"><button class="model-profile-expand" :aria-label="'展开 '+p.name" :aria-expanded="expanded===p.id" @click="expanded=expanded===p.id?undefined:p.id"><span class="model-vendor-mark qwen"><img src="/model-logos/qwen.png" alt="Qwen"/></span><span class="model-profile-title"><strong>{{p.name}}</strong><small>{{p.kind.toUpperCase()}} · {{p.model||'点击展开配置'}}</small></span><ChevronDown class="model-expand-chevron" :size="17"/></button><div class="model-enable-control"><span>{{registry[p.kind==='tts'?'activeTtsId':'activeAsrId']===p.id?'已启用':'启用'}}</span><button class="model-enable-switch" role="switch" :aria-label="'启用 '+p.name" :aria-checked="registry[p.kind==='tts'?'activeTtsId':'activeAsrId']===p.id" :disabled="switching||drafts[p.id]!.busy" @click="enable(p)"><span/></button></div></div>
    <form v-if="expanded===p.id" class="model-profile-form" @submit.prevent="save(p.id)">
     <fieldset :disabled="drafts[p.id]!.busy||switching">
      <label class="profile-field full"><span>接口地址</span><input v-model="drafts[p.id]!.baseUrl" required maxlength="2048" :aria-label="p.name+' 接口地址'" placeholder="wss://业务空间域名/api-ws/v1/inference" spellcheck="false"/></label>
      <div class="profile-field full"><label :for="'speech-key-'+p.id">API Key <small>{{p.hasApiKey?'已保存，留空保留':''}}</small></label><div class="speech-key-field"><input :id="'speech-key-'+p.id" v-model="drafts[p.id]!.apiKey" :type="drafts[p.id]!.showKey?'text':'password'" :aria-label="p.name+' API Key'" autocomplete="off" maxlength="4096" :disabled="drafts[p.id]!.clearApiKey" :placeholder="p.hasApiKey?'留空保留已保存的密钥':'输入 API Key'"/><button type="button" :aria-label="drafts[p.id]!.showKey?'隐藏 API Key':'显示 API Key'" @click="drafts[p.id]!.showKey=!drafts[p.id]!.showKey"><EyeOff v-if="drafts[p.id]!.showKey" :size="16"/><Eye v-else :size="16"/></button></div><label v-if="p.hasApiKey" class="profile-check"><input type="checkbox" v-model="drafts[p.id]!.clearApiKey"/>清除已保存的 API Key</label></div>
      <div class="profile-field full"><div class="profile-model-heading"><label :for="'speech-model-'+p.id">模型名称</label><div><button v-if="modelList(p.id)" type="button" class="profile-manual" @click="manualModels[p.id]=!manualModels[p.id]">{{manualModels[p.id]?'选择模型':'手动输入'}}</button><button type="button" class="profile-fetch-models" :aria-busy="!!modelFetching[p.id]" :disabled="modelFetching[p.id]||drafts[p.id]!.busy||switching" @click="fetchModels(p.id)"><RefreshCw :class="{rotating:modelFetching[p.id]}" :size="14"/>获取模型列表</button></div></div><ModelSelect v-if="modelList(p.id)&&!manualModels[p.id]" :id="'speech-model-'+p.id" :model-value="drafts[p.id]!.model" @update:model-value="drafts[p.id]!.model=$event" :options="modelList(p.id)!.names" :label="p.name+' 模型名称'" search-label="输入名称筛选模型" :disabled="drafts[p.id]!.busy||switching||modelFetching[p.id]"/><input v-else :id="'speech-model-'+p.id" v-model="drafts[p.id]!.model" required maxlength="160" :aria-label="p.name+' 模型名称'" spellcheck="false"/></div>
      <template v-if="drafts[p.id]!.kind==='tts'">
       <div class="profile-field full"><div class="profile-model-heading"><label :for="'speech-voice-'+p.id">音色名称</label><button type="button" class="profile-test speech-fetch-voices" :aria-busy="!!fetching[p.id]" :disabled="fetching[p.id]||drafts[p.id]!.busy||switching" @click="fetchVoices(p.id)"><RefreshCw :class="{rotating:fetching[p.id]}" :size="14"/>获取音色列表</button></div>
        <ModelSelect :id="'speech-voice-'+p.id" :model-value="drafts[p.id]!.voice" @update:model-value="drafts[p.id]!.voice=$event" :options="voiceOptions(p.id)" :labels="voiceLabels(p.id)" :descriptions="voiceDescriptions(p.id)" :label="p.name+' 音色名称'" search-label="搜索名称或输入音色 ID" allow-custom :disabled="drafts[p.id]!.busy||switching">
         <template #action="{option}"><button type="button" data-option-action class="speech-option-preview" :class="{reading:previewing(p.id,option)&&player.state.value==='playing'}" :aria-label="previewLabel(p.id,option).replace('音色','')+' '+option" :disabled="drafts[p.id]!.busy||switching" @click.stop="preview(p.id,option)" @keydown.enter.stop @keydown.space.stop><LoaderCircle v-if="previewing(p.id,option)&&player.state.value==='loading'" :size="13"/><Pause v-else-if="previewing(p.id,option)&&player.state.value==='playing'" :size="13"/><Volume2 v-else :size="13"/>{{previewLabel(p.id,option).replace('音色','')}}</button></template>
        </ModelSelect><small>可搜索音色名称，或输入自定义音色 ID 后按 Enter。</small>
       </div>
      </template>
     </fieldset>
     <p v-if="drafts[p.id]!.kind==='asr'" class="profile-test-note">用于语音转文字、按住说话发送，以及截图工具栏中小洁精灵的实时语音通话。</p>
     <p v-if="drafts[p.id]!.error" class="profile-feedback" role="alert">{{drafts[p.id]!.error}}</p><p v-else-if="drafts[p.id]!.message" class="profile-feedback success" role="status">{{drafts[p.id]!.message}}</p>
     <div class="profile-form-footer"><span><ShieldCheck :size="13"/>{{dirty(p.id)?'有未保存的修改':'密钥仅保存在本机'}}</span><div><button type="button" class="profile-test" :disabled="drafts[p.id]!.busy||switching" @click="test(p.id)"><Zap :size="15"/>测速</button><button v-if="drafts[p.id]!.kind==='tts'" type="button" class="profile-test" :class="{reading:previewing(p.id,drafts[p.id]!.voice)&&player.state.value==='playing'}" :disabled="drafts[p.id]!.busy||switching" @click="preview(p.id)"><LoaderCircle v-if="previewing(p.id,drafts[p.id]!.voice)&&player.state.value==='loading'" :size="15"/><Pause v-else-if="previewing(p.id,drafts[p.id]!.voice)&&player.state.value==='playing'" :size="15"/><Volume2 v-else :size="15"/>{{previewLabel(p.id)}}</button><button type="submit" class="profile-save" :disabled="drafts[p.id]!.busy||switching"><LoaderCircle v-if="drafts[p.id]!.busy" :size="15"/><Check v-else :size="15"/>保存配置</button></div></div>
    </form>
   </article>
    </div>
   </section>
  </template>
 </div>
</template>
