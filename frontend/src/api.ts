import type { Session, Message } from './types'
import {native} from './desktop'
const base=native&&!/^https?:$/.test(location.protocol)?'http://127.0.0.1:8776/api':'/api'
export interface ModelConfig {provider:'openai-compatible'|'ollama';baseUrl:string;model:string;hasApiKey:boolean}
export interface UsageSummary{inputTokens:number;outputTokens:number;requests:number;llmRequests?:number;ocrRequests?:number;unreportedRequests?:number;models:{model:string;kind?:'ocr';historical?:boolean;inputTokens:number|null;outputTokens:number|null;requests:number}[]}
export type UsageKind='llm'|'ocr'
export interface UsageMetrics{requests:number;inputTokens?:number;outputTokens?:number;totalTokens?:number;cachedInputTokens?:number|null;uncachedInputTokens?:number|null;cacheReportedRequests?:number;cacheInputTokens?:number;cacheHitRate?:number|null;unreportedRequests?:number;unbucketedRequests:number}
export interface UsagePoint extends UsageMetrics{key:string;label:string}
export interface UsageAnalytics{kind:UsageKind;range:{start:string;end:string;timezone:string;granularity:'hour'|'day'};summary:UsageMetrics;models:(UsageMetrics&{model:string})[];trend:UsagePoint[];modelTrends:{model:string;points:UsagePoint[]}[]}
export interface ModelProfile extends ModelConfig{id:string;name:string;vendor:'deepseek'|'kimi'|'qwen'|'doubao'|'glm'|'custom';vision:boolean;saved:boolean;apiKeyUrl?:string|null}
export interface ModelRegistry{activeId:string|null;profiles:ModelProfile[];configFile?:string}
export interface OcrInput{provider:'paddleocr';baseUrl:string;model:string;apiKey?:string;clearApiKey?:boolean;enabled:boolean;assistLlm:boolean;apiMode?:'async'|'sync'}
export interface OcrUsage{date:string;timezone:string;dailyLimit:number;submitted:number;remaining:number;cloudAvailable:boolean;reason?:string|null;retryAfterSeconds:number;counterScope:string}
export interface OcrSettings extends OcrInput{hasApiKey:boolean;apiKeyUrl:string;usage?:OcrUsage;fallback?:string}
export interface LocatedText{ text:string; regions:{id:string;text:string;bbox:[number,number,number,number];granularity:'line'|'block';page:number;label:string;words?:{text:string;bbox:number[]}[]}[];width:number;height:number;mode:string;coordinateSpace:'image-pixels';fallback:boolean;fallbackReason?:string;usage?:OcrUsage}
export interface InlineTranslationResult{lines:{id:string;sourceText:string;text:string;bbox:[number,number,number,number]}[];language:string;coordinateSpace:'image-pixels';width:number;height:number}
export interface ExtractedTable{title:string;rows:string[][]}
export interface DetectedObject{id:string;label:string;bbox:[number,number,number,number]}
export interface ObjectDetection{objects:DetectedObject[];width:number;height:number;coordinateSpace:'image-pixels';approximate:boolean}
export interface ControlTarget{id:string;text:string;controlType:'Button'|'Edit'|'ComboBox'|'CheckBox'|'RadioButton'|'Hyperlink'|'MenuItem'|'TabItem'|'ListItem'|'TreeItem'|'Slider'|'Spinner';bbox:[number,number,number,number]}
export interface AiAnnotation{kind:'callout'|'circle'|'check'|'cross'|'rectangle'|'arrow'|'highlight'|'text'|'number';text:string;bbox:[number,number,number,number];locationSource?:'ocr'|'uia'|'object-detection'|'existing'|'visual'}
export interface AiExisting extends AiAnnotation{id:string}
export interface AiTurn{role:'user'|'assistant';text:string}
export type ImageAction='chat'|'ocr'|'offline'|'translate'|'explain'|'table'|'detect'|'annotate'|'code'|'paper'|'exam'|'formula'|'qr'|'entities'|'crop'|'highlight'|'mosaic'|'heal'|'lift'|'region'|'note'|'blur'|'restore_image'|'draw'|'undo'|'clear_annotations'|'answer'
export interface ImageToolCall{name:ImageAction;arguments:{imageId?:string;prompt?:string;language?:string;bbox?:number[];targetText?:string}}
export interface ImageNote{markdown:string;imageIds:string[]}
export interface ImageToolCatalog{version:number;coordinateSpace:'image-pixels';tools:{type:'function';function:{name:ImageAction;description:string;parameters:Record<string,unknown>}}[]}
export interface ImageConversationResult{action:ImageAction;assetId:string|null;answer:string;payload:Record<string,unknown>|InlineTranslationResult|AiAnnotationResult|StudyResult|ObjectDetection;steps?:ImageConversationResult[];agent?:{version:number;mode:string;toolCalls:number}}
export interface AgentEvent{type:string;phase?:string;tool?:string;name?:string;step?:number;attempt?:number;text?:string}
export interface ImageUtility{codes?:{text:string;format:string;bbox:number[];url:string|null}[];entities?:{kind:string;text:string;url:string;bbox:number[]}[];regions?:LocatedText['regions'];text?:string;width:number;height:number}
export type AiAnnotationEdit=(AiAnnotation&{operation:'add';id?:never})|(AiAnnotation&{operation:'update';id:string})|{operation:'remove';id:string}
export interface AiAnnotationResult{answer:string;annotations:AiAnnotationEdit[];width:number;height:number;coordinateSpace:'image-pixels';approximate:boolean}
export type StudyMode='code'|'paper'
export interface StudyNote extends AiAnnotation{pageId:string;targetIds:string[];explanation:string;lineLabel:string|null}
export interface StudyResult{answer:string;notes:StudyNote[];mode:StudyMode;coordinateSpace:'image-pixels';pages:{id:string;name:string;width:number;height:number;number:number;ocrMode:string;warning:string|null}[]}
export interface OcrDocument{schemaVersion:number;ocr:OcrInput}
export interface SpeechInput{name:string;kind:'asr'|'tts';provider:'dashscope';baseUrl:string;model:string;voice:string;sampleRate:number;rate:number;volume:number;pitch:number;language?:string;apiKey?:string;clearApiKey?:boolean}
export interface SpeechProfile extends SpeechInput{id:string;hasApiKey:boolean}
export interface SpeechRegistry{activeAsrId:string|null;activeTtsId:string|null;profiles:SpeechProfile[]}
export interface SpeechVoice{id:string;name:string;description:string;language:string}
export interface SnapMindConfiguration{schemaVersion:number;activeModelId:string|null;models:{id:string;name:string;provider:ModelProfile['vendor'];baseUrl:string;apiKey:string;model:string;enabled:boolean;vision:boolean}[]}
export interface ProfileInput{name:string;vendor:ModelProfile['vendor'];provider:ModelConfig['provider'];baseUrl:string;model:string;vision:boolean;apiKey?:string;clearApiKey?:boolean}
export interface ModelConnection{ok:boolean;latencyMs:number;models:string[];modelAvailable:boolean|null;error?:string;statusCode?:number}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const r = await fetch(base + path, { ...init, signal:init?.signal||AbortSignal.timeout(8000), headers: { 'Content-Type': 'application/json', ...init?.headers } })
  if (!r.ok) {const body=await r.json().catch(()=>({detail:'服务暂时不可用'}));throw new Error(Array.isArray(body.detail)?'配置格式不正确，请检查输入':body.detail||'请求失败')}
  return r.json()
}
export const api = {
  speechSocketUrl:()=>{const url=new URL(base+'/speech/recognize',location.href);url.protocol=url.protocol==='https:'?'wss:':'ws:';return url.href},
  speech:()=>request<SpeechRegistry>('/settings/speech'),
  openMicrophoneSettings:()=>request<{opened:boolean}>('/settings/microphone/open',{method:'POST'}),
  saveSpeech:(id:string,config:SpeechInput)=>request<SpeechRegistry>('/settings/speech/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify(config)}),
  activateSpeech:(kind:'asr'|'tts',activeId:string|null)=>request<SpeechRegistry>('/settings/speech/active',{method:'PUT',body:JSON.stringify({kind,activeId})}),
  testSpeech:(id:string,config:SpeechInput)=>request<{ok:boolean;latencyMs:number;authVerified:boolean;error?:string}>('/settings/speech/'+encodeURIComponent(id)+'/test',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.timeout(20000)}),
  synthesize:(text:string,signal:AbortSignal)=>audioRequest('/speech/synthesize',{text},signal),
  previewSpeech:(id:string,config:SpeechInput&{text?:string},signal:AbortSignal)=>audioRequest('/settings/speech/'+encodeURIComponent(id)+'/preview',config,signal),
  speechVoices:(id:string,config:SpeechInput,signal:AbortSignal)=>request<{model:string;voices:SpeechVoice[];source:string}>('/settings/speech/'+encodeURIComponent(id)+'/voices',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.any([signal,AbortSignal.timeout(20000)])}),
  speechModels:(id:string,config:SpeechInput,signal:AbortSignal)=>request<{kind:'asr'|'tts';models:string[];source:string}>('/settings/speech/'+encodeURIComponent(id)+'/models',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.any([signal,AbortSignal.timeout(25000)])}),
  imageTools:()=>request<ImageToolCatalog>('/tools'),
  callImageTool:(call:ImageToolCall,context:{sessionId?:string;turnId?:string;userMessageId?:string;undoSnapshot?:{asset:import('./types').Asset;annotations:AiExisting[]};assets:import('./types').Asset[];selectedId:string|null;prompt?:string;history:AiTurn[];existing:AiExisting[];controls?:ControlTarget[];language?:string},signal?:AbortSignal)=>request<ImageConversationResult>('/tools/call',{method:'POST',body:JSON.stringify({...call,context}),signal:signal||AbortSignal.timeout(240000)}),
  imageConversation:(assets:import('./types').Asset[],selectedId:string|null,prompt:string,history:AiTurn[],existing:AiExisting[],signal:AbortSignal,action?:ImageAction,language='zh-CN',controls:ControlTarget[]=[],sessionId?:string,turnId?:string,onChunk?:(text:string)=>void,onEvent?:(event:AgentEvent)=>void,userMessageId?:string,undoSnapshot?:{asset:import('./types').Asset;annotations:AiExisting[]})=>imageStream({sessionId,turnId,userMessageId,undoSnapshot,assets,selectedId,prompt,history,existing,controls,action,language},signal,onChunk||(()=>{}),onEvent),
  imageUtility:(asset:import('./types').Asset,action:'offline'|'qr'|'entities',signal?:AbortSignal)=>request<ImageUtility>('/capture/utility',{method:'POST',body:JSON.stringify({asset,action}),signal:signal||AbortSignal.timeout(60000)}),
  repairImage:(asset:import('./types').Asset,mask:string,extract=false,signal?:AbortSignal)=>request<{data:string;width:number;height:number;layer?:{data:string;bbox:[number,number,number,number]}}>('/capture/repair',{method:'POST',body:JSON.stringify({asset,mask,extract}),signal:signal||AbortSignal.timeout(60000)}),
  annotateCapture:(asset:import('./types').Asset,prompt:string,history:AiTurn[],existing:AiExisting[],signal?:AbortSignal,controls:ControlTarget[]=[])=>request<AiAnnotationResult>('/capture/annotate',{method:'POST',body:JSON.stringify({asset,prompt,history,existing,controls}),signal:signal||AbortSignal.timeout(150000)}),
  detectObjects:(asset:import('./types').Asset,target:'all'|'vehicles',signal?:AbortSignal)=>request<ObjectDetection>('/capture/analyze',{method:'POST',body:JSON.stringify({asset,action:'detect',target}),signal:signal||AbortSignal.timeout(150000)}),
  ocr:()=>request<OcrSettings>('/settings/ocr'),
  saveOcr:(config:OcrInput)=>request<OcrSettings>('/settings/ocr',{method:'PUT',body:JSON.stringify(config)}),
  fetchOcrModels:(config:OcrInput)=>request<{models:string[]}>('/settings/ocr/models',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.timeout(25000)}),
  testOcr:(config:OcrInput)=>request<{ok:boolean;latencyMs:number;error?:string;authVerified:boolean}>('/settings/ocr/test',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.timeout(20000)}),
  health: () => request<{mode:string; storage:string}>('/health'),
  locateCapture:(asset:import('./types').Asset,signal?:AbortSignal,granularity:'auto'|'line'='auto')=>request<LocatedText>('/capture/locate',{method:'POST',body:JSON.stringify({asset,granularity}),signal:signal||AbortSignal.timeout(120000)}),
  translateInline:(asset:import('./types').Asset,lines:LocatedText['regions'],language:string,signal?:AbortSignal)=>request<InlineTranslationResult>('/capture/translate-inline',{method:'POST',body:JSON.stringify({asset,lines:lines.map(({id,text,bbox})=>({id,text,bbox})),language}),signal:signal||AbortSignal.timeout(150000)}),
  processCapture:(asset:import('./types').Asset,action:'ocr'|'translate'|'explain',language='zh-CN',signal?:AbortSignal)=>request<{text:string;mode:string;model?:string;location?:LocatedText}>('/capture/process',{method:'POST',body:JSON.stringify({asset,action,language,engine:'multimodal'}),signal:signal||AbortSignal.timeout(240000)}),
  modelConfig:()=>request<ModelConfig>('/settings/model'),
  usage:()=>request<UsageSummary>('/usage'),
  usageAnalytics:(kind:UsageKind,start:string,end:string,signal?:AbortSignal)=>request<UsageAnalytics>('/usage/analytics?'+new URLSearchParams({kind,start,end}),{signal}),
  models:()=>request<ModelRegistry>('/settings/models'),
  saveProfile:(id:string,config:ProfileInput)=>request<ModelRegistry>('/settings/models/'+encodeURIComponent(id),{method:'PUT',body:JSON.stringify(config)}),
  syncProfile:(id:string,config:ProfileInput)=>request<ModelRegistry>('/settings/models/'+encodeURIComponent(id)+'/draft',{method:'PUT',body:JSON.stringify(config)}),
  configuration:(revealKeys=false)=>request<SnapMindConfiguration>('/settings/config?reveal_keys='+revealKeys),
  activateProfile:(activeId:string|null)=>request<ModelRegistry>('/settings/models/active',{method:'PUT',body:JSON.stringify({activeId})}),
  testProfile:(id:string,config:ProfileInput)=>request<ModelConnection>('/settings/models/'+encodeURIComponent(id)+'/test',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.timeout(20000)}),
  fetchProfileModels:(id:string,config:ProfileInput)=>request<ModelConnection>('/settings/models/'+encodeURIComponent(id)+'/models',{method:'POST',body:JSON.stringify(config),signal:AbortSignal.timeout(25000)}),
  openKeyPortal:(vendor:ModelProfile['vendor']|'paddleocr')=>request<{opened:boolean}>('/settings/key-portals/'+encodeURIComponent(vendor)+'/open',{method:'POST'}),
  saveModelConfig:(config:{provider:ModelConfig['provider'];baseUrl:string;model:string;apiKey?:string;clearApiKey?:boolean})=>request<ModelConfig>('/settings/model',{method:'PUT',body:JSON.stringify(config)}),
  list: () => request<Session[]>('/sessions'),
  imageHistory:()=>request<import('./types').ImageHistoryItem[]>('/image-history'),
  session:(id:string)=>request<Session>('/sessions/'+encodeURIComponent(id)),
  sessionMetadata:(id:string,change:{title?:string;pinned?:boolean})=>request<import('./types').ImageHistoryItem>('/sessions/'+encodeURIComponent(id)+'/metadata',{method:'PATCH',body:JSON.stringify(change)}),
  imageTitle:(id:string)=>request<{title:string;source:string}>('/sessions/'+encodeURIComponent(id)+'/image-title',{method:'POST',signal:AbortSignal.timeout(240000)}),
  save: (s: Session) => request<Session>('/sessions/' + s.id, {method:'PUT', body: JSON.stringify(s)}),
  remove: (id: string) => request<void>('/sessions/' + id, {method:'DELETE'}),
  async chat(session: Session, action: string, prompt: string, signal: AbortSignal, onChunk: (chunk: string) => void): Promise<Message> {
    const r = await fetch(base+'/chat', { method: 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({session, action, prompt}), signal })
    if (!r.ok) {const data=await r.json().catch(()=>({detail:'模型服务连接失败，请确认本地服务已启动。'}));throw new Error(typeof data.detail==='string'?data.detail:'模型请求失败，请检查配置。')}
    const reader = r.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = '', result: Message | undefined
    while (true) {
      const {done,value} = await reader.read()
      if (done) break
      buffer += decoder.decode(value, {stream:true})
      let split: number
      while ((split=buffer.indexOf('\n\n')) >= 0) {
        const event=buffer.slice(0,split); buffer=buffer.slice(split+2)
        const raw=event.split('\n').find(l=>l.startsWith('data: '))?.slice(6)
        if (!raw) continue
        const data=JSON.parse(raw)
        if (data.type==='chunk') onChunk(data.text)
        if (data.type==='result') result=data.message
      }
    }
    if (!result) throw new Error('返回中断，请重试。')
    return result
  }
}
async function audioRequest(path:string,body:unknown,signal:AbortSignal):Promise<Response>{
 const response=await fetch(base+path+'?stream=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal:AbortSignal.any([signal,AbortSignal.timeout(125000)])})
 if(!response.ok){const data=await response.json().catch(()=>({detail:'语音合成失败，请重试'}));throw new Error(typeof data.detail==='string'?data.detail:'语音配置格式不正确')}
 if(!response.headers.get('Content-Type')?.startsWith('audio/'))throw new Error('语音服务未返回有效音频')
 if(!response.body)throw new Error('语音服务返回了空音频');return response
}
async function imageStream(body:unknown,signal:AbortSignal,onChunk:(text:string)=>void,onEvent?:(event:AgentEvent)=>void):Promise<ImageConversationResult>{
 const response=await fetch(base+'/capture/conversation?stream=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(body),signal})
 if(!response.ok){const data=await response.json().catch(()=>({detail:'截图处理失败'}));throw new Error(typeof data.detail==='string'?data.detail:'截图处理失败')}
 if(!response.headers.get('Content-Type')?.includes('text/event-stream'))return response.json()
 const reader=response.body!.getReader(),decoder=new TextDecoder();let pending='',result:ImageConversationResult|undefined
 try{while(true){const {done,value}=await reader.read();if(done)break;pending+=decoder.decode(value,{stream:true});let end:number;while((end=pending.indexOf('\n\n'))>=0){const block=pending.slice(0,end);pending=pending.slice(end+2);const raw=block.split('\n').find(line=>line.startsWith('data:'))?.slice(5);if(!raw)continue;const event=JSON.parse(raw);if(event.type==='error')throw new Error(event.message||'回复中断');if(event.type==='chunk')onChunk(event.text);onEvent?.(event);if(event.type==='result')result=event.result}}
 }finally{await reader.cancel().catch(()=>{});reader.releaseLock()}
 if(!result)throw new Error('回复中断，请重试');return result
}
