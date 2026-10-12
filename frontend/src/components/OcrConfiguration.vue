<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref,watch} from 'vue'
import {Check,LoaderCircle,KeyRound,ExternalLink,RefreshCw,ShieldCheck,Zap,Trash2} from 'lucide-vue-next'
import {api,type OcrInput,type OcrSettings,type OcrDocument} from '../api'
import {native} from '../desktop'
import {tr} from '../preferences'
import ConfigurationJson from './ConfigurationJson.vue'
import ModelSelect from './ModelSelect.vue'
const mask='••••••••••',loading=ref(true),loaded=ref(false),busy=ref(false),error=ref(''),message=ref(''),syncStatus=ref('saved'),latency=ref<number>(),stored=ref<OcrSettings>()
const draft=ref<OcrInput>({provider:'paddleocr',baseUrl:'',model:'PaddleOCR-VL-1.6',apiKey:'',enabled:false,assistLlm:true,clearApiKey:false,apiMode:'async'})
const fetched=ref(false),fetching=ref(false),modelNames=ref<string[]>([]),modelListError=ref('')
let listVersion=0
let timer:ReturnType<typeof setTimeout>|undefined,queue=Promise.resolve(),disposed=false,baseline=''
const ready=computed(()=>!!draft.value.baseUrl.trim()&&!draft.value.clearApiKey&&!!(draft.value.apiKey?.trim()||stored.value?.hasApiKey))
function input():OcrInput{return {...draft.value,model:draft.value.model.trim(),baseUrl:draft.value.baseUrl.trim(),apiKey:draft.value.apiKey===mask?undefined:draft.value.apiKey?.trim()||undefined,enabled:draft.value.enabled&&ready.value}}
const preview=computed<OcrDocument>(()=>({schemaVersion:1,ocr:{provider:'paddleocr',baseUrl:draft.value.baseUrl.trim(),model:draft.value.model,apiKey:!draft.value.clearApiKey&&(draft.value.apiKey||stored.value?.hasApiKey)?mask:'',enabled:draft.value.enabled&&ready.value,assistLlm:draft.value.assistLlm,apiMode:draft.value.apiMode}}))
function signature(){return JSON.stringify(input())}
function schedule(){clearTimeout(timer);syncStatus.value='pending';timer=setTimeout(()=>{timer=undefined;enqueue()},650)}
function enqueue(){queue=queue.then(sync);return queue}
async function sync(){if(!loaded.value||signature()===baseline)return;const value=input(),version=JSON.stringify(value);syncStatus.value='saving';error.value='';try{stored.value=await api.saveOcr(value);baseline=version;if(signature()===version){draft.value.apiKey=stored.value.hasApiKey?mask:'';draft.value.clearApiKey=false;draft.value.enabled=stored.value.enabled;baseline=signature()}syncStatus.value=signature()===baseline?'saved':'pending';if(signature()!==baseline&&!disposed)schedule()}catch(e){syncStatus.value='error';error.value=e instanceof Error?e.message:String(e)}}
watch(draft,()=>{message.value='';latency.value=undefined;if(loaded.value&&signature()!==baseline)schedule()},{deep:true})
async function load(){discardModelLists();loading.value=true;loaded.value=false;error.value='';try{stored.value=await api.ocr();const p=stored.value;draft.value={provider:'paddleocr',baseUrl:p.baseUrl,model:p.model,apiKey:p.hasApiKey?mask:'',enabled:p.enabled,assistLlm:p.assistLlm,clearApiKey:false,apiMode:p.apiMode||'async'};baseline=signature();loaded.value=true;syncStatus.value='saved'}catch(e){error.value=e instanceof Error?e.message:String(e)}finally{loading.value=false}}
function discardModelLists(){listVersion++;fetched.value=false;modelNames.value=[];modelListError.value='';message.value='';error.value=''}
defineExpose({discardModelLists})
async function fetchModels(){if(busy.value||!ready.value)return;discardModelLists();const version=listVersion;busy.value=true;fetching.value=true;try{const result=await api.fetchOcrModels(input());if(disposed||version!==listVersion)return;modelNames.value=result.models;fetched.value=result.models.length>0;message.value=fetched.value?tr('已获取 ','已取得 ','Fetched ')+result.models.length+tr(' 个模型',' 個模型',' models'):tr('接口没有返回模型，仍可手动输入','介面沒有回傳模型，仍可手動輸入','No models returned; manual input remains available')}catch(e){if(!disposed&&version===listVersion)modelListError.value=e instanceof Error?e.message:String(e)}finally{busy.value=false;fetching.value=false}}
function chooseModel(value:string){draft.value.model=value;draft.value.enabled=false;error.value=''}
async function save(){discardModelLists();clearTimeout(timer);timer=undefined;busy.value=true;await enqueue();busy.value=false;if(syncStatus.value==='saved')message.value=tr('OCR 配置已保存','OCR 設定已儲存','OCR configuration saved')}
async function test(){busy.value=true;error.value='';modelListError.value='';try{const result=await api.testOcr(input());latency.value=result.latencyMs;if(!result.ok)error.value=result.error||'连接失败';else message.value=tr('服务可连接；此测试不验证识别结果','服務可連線；此測試不驗證識別結果','Service reachable; recognition was not tested')}catch(e){error.value=e instanceof Error?e.message:String(e)}finally{busy.value=false}}
async function toggle(){if(!ready.value||busy.value)return;draft.value.enabled=!draft.value.enabled;await save()}
function credentialsChanged(){discardModelLists();if(draft.value.apiKey&&draft.value.apiKey!==mask)draft.value.clearApiKey=false;draft.value.enabled=false;error.value=''}
async function clearKey(){if(busy.value)return;draft.value.apiKey='';draft.value.clearApiKey=true;credentialsChanged();await save();if(syncStatus.value==='saved')message.value=tr('API Key 已清除','API Key 已清除','API key cleared')}
function selectMask(event:Event){if(draft.value.apiKey===mask)(event.target as HTMLInputElement).select()}
function restoreMask(){if(stored.value?.hasApiKey&&!draft.value.clearApiKey&&!draft.value.apiKey)draft.value.apiKey=mask}
async function portal(event:MouseEvent){if(!native)return;event.preventDefault();try{await api.openKeyPortal('paddleocr')}catch(e){error.value=e instanceof Error?e.message:String(e)}}
onMounted(load)
onBeforeUnmount(()=>{disposed=true;discardModelLists();if(timer){clearTimeout(timer);enqueue()}})
</script>
<template>
 <div class="model-profiles ocr-configuration">
  <div class="model-profiles-heading"><div><h3>{{tr('OCR 识别服务','OCR 識別服務','OCR service')}}</h3></div></div>
  <p v-if="loading" class="model-profiles-status">{{tr('正在加载…','正在載入…','Loading…')}}</p>
  <template v-else-if="loaded">
   <article class="model-profile expanded" data-profile-id="paddleocr">
    <div class="model-profile-row"><div class="ocr-provider-heading"><span class="ocr-provider-mark"><img src="/model-logos/paddleocr.png" alt=""/></span><span class="model-profile-title"><strong>PaddleOCR</strong><small>AI Studio · {{tr('文字识别 / 版面定位','文字識別 / 版面定位','Text / layout detection')}}</small></span></div><div class="model-enable-control"><span>{{draft.enabled?tr('已启用','已啟用','Enabled'):tr('启用','啟用','Enable')}}</span><button type="button" role="switch" class="model-enable-switch" aria-label="启用 PaddleOCR" :aria-checked="draft.enabled" :disabled="busy||!ready" @click="toggle"><span/></button></div></div>
    <form class="model-profile-form" aria-label="PaddleOCR 配置" @submit.prevent="save">
     <fieldset :disabled="busy">
      <label class="profile-field full"><span>{{tr('接口地址','介面位址','API URL')}}</span><input v-model="draft.baseUrl" type="url" maxlength="2048" aria-label="PaddleOCR 接口地址" placeholder="https://paddleocr.aistudio-app.com/api/v2/ocr/jobs" spellcheck="false" @input="credentialsChanged"/><small>{{tr('异步解析使用 /api/v2/ocr/jobs，提交后自动等待结果。','非同步解析使用 /api/v2/ocr/jobs，提交後自動等待結果。','Async parsing uses /api/v2/ocr/jobs and waits for the result automatically.')}}</small></label>
      <div class="profile-field full"><label for="paddleocr-key">API Key <small>Access Token</small></label><div class="profile-key-input"><input id="paddleocr-key" v-model="draft.apiKey" type="password" aria-label="PaddleOCR API Key" maxlength="4096" autocomplete="off" placeholder="输入 AI Studio Access Token" @focus="selectMask" @beforeinput="selectMask" @blur="restoreMask" @input="credentialsChanged"/></div><div class="profile-key-actions"><a class="profile-key-link" href="https://aistudio.baidu.com/paddleocr" target="_blank" rel="noopener noreferrer" @click="portal"><KeyRound :size="13"/><span>{{tr('获取 API Key','取得 API Key','Get API key')}}</span><ExternalLink :size="12"/></a><button type="button" class="profile-clear-key" :disabled="busy||!draft.apiKey?.trim()" @click="clearKey"><Trash2 :size="13"/>{{tr('清除 API Key','清除 API Key','Clear API key')}}</button></div></div>
      <div class="profile-field full"><div class="profile-model-heading"><label for="paddleocr-model">{{tr('模型名称','模型名稱','Model name')}}</label><div><button v-if="fetched" type="button" class="profile-manual" @click="discardModelLists">{{tr('手动输入','手動輸入','Manual input')}}</button><button type="button" class="profile-fetch-models" :aria-busy="fetching" :disabled="busy||!ready" @click="fetchModels"><RefreshCw :class="{rotating:fetching}" :size="14"/>{{tr('获取模型列表','取得模型清單','Fetch models')}}</button></div></div><ModelSelect v-if="fetched" id="paddleocr-model" :model-value="draft.model" :options="modelNames" label="PaddleOCR 模型" :disabled="busy" @update:model-value="chooseModel"/><input v-else id="paddleocr-model" v-model="draft.model" required maxlength="160" aria-label="PaddleOCR 模型" :placeholder="tr('填写服务提供的模型 ID','填寫服務提供的模型 ID','Enter the model ID provided by the service')" spellcheck="false" @input="draft.enabled=false"/></div>
     </fieldset>
     <p v-if="error||modelListError" class="profile-feedback" role="alert">{{error||modelListError}}</p><p v-else-if="message" class="profile-feedback success" role="status">{{message}}</p>
     <div v-if="latency!==undefined" class="profile-latency"><Zap :size="14"/><span>{{tr('连接响应延迟','連線回應延遲','Connection latency')}}</span><strong>{{latency}}<small> ms</small></strong></div>
     <div class="profile-form-footer"><span><ShieldCheck :size="13"/>{{tr('密钥输入始终隐藏','金鑰輸入始終隱藏','Key input stays hidden')}}</span><div><button type="button" class="profile-test" :disabled="busy||!ready" @click="test"><Zap :size="15"/>{{tr('测速','測速','Test latency')}}</button><button type="submit" class="profile-save" :disabled="busy"><LoaderCircle v-if="busy" :size="15"/><Check v-else :size="15"/>{{tr('保存配置','儲存設定','Save configuration')}}</button></div></div>
     <p class="profile-test-note">{{tr('测速仅检查连接，不提交截图，也不消耗识别额度。启用后，识别时会将截图发送给 PaddleOCR。','測速僅檢查連線，不提交截圖，也不消耗識別額度。啟用後，識別時會將截圖傳送給 PaddleOCR。','Connection testing sends no image. Once enabled, recognition sends images to PaddleOCR.')}}</p>
    </form>
   </article>
   <ConfigurationJson :value="preview" :show-keys="false" lock-keys :status="syncStatus" :error="error"/>
  </template>
  <div v-else class="model-profiles-status"><p role="alert">{{error}}</p><button @click="load">{{tr('重新加载','重新載入','Reload')}}</button></div>
 </div>
</template>
