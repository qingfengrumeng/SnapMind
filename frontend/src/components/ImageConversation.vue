<script setup lang="ts">
import {ref,computed,nextTick,onBeforeUnmount,onMounted,watch} from 'vue'
import type {Asset,TextAttachment,Session,Message,ImageHistoryItem,VoiceCallRecord,VoiceMessage as VoiceMessageData} from '../types'
import {readCaptureFile} from '../capture'
import {api,type ImageAction,type ImageConversationResult,type AiTurn,type AiExisting,type ExtractedTable,type ImageUtility,type AiAnnotationResult,type ControlTarget,type ImageToolCall,type ImageNote} from '../api'
import {assetCanvas,canvasAsset,annotationEdits,renderAnnotations,applyImageResult,copyTable} from '../image-actions'
import {desktop,native} from '../desktop'
import Icon from './Icon.vue'
import SnapMindLogo from './SnapMindLogo.vue'
import StudyText from './StudyText.vue'
import ImageToolMenu from './ImageToolMenu.vue'
import ImageAttachmentPreview from './ImageAttachmentPreview.vue'
import TextAttachmentPreview from './TextAttachmentPreview.vue'
import VoiceMessage from './VoiceMessage.vue'
import ImageConversationHistory from './ImageConversationHistory.vue'
import {attachmentPrompt,attachmentBytes,pastedAttachment} from '../text-attachments'
import {useSpeechInput} from '../speech-input'
import {useSpeechPlayer} from '../speech-player'
import {imageSteps,agentToolLabels} from '../agent-results'
import {followupExamples,type FollowupExample} from '../followup-examples'
import {toolCommands,slashQuery,filterToolCommands,buildToolCall,isImageTool,type ImageToolCommand} from '../image-tool-commands'
const props=defineProps<{initial?:Asset;controls?:(asset:Asset,prompt:string)=>Promise<ControlTarget[]>;applyResult?:(result:ImageConversationResult,rendered?:Asset,signal?:AbortSignal)=>Promise<void>}>()
const emit=defineEmits<{result:[result:ImageConversationResult,rendered?:Asset];toast:[text:string];close:[]}>()
type Picture={source:Asset;rendered:Asset;annotations:AiExisting[];undo:{source:Asset;rendered:Asset;annotations:AiExisting[]}[]}
type RequestContext=Parameters<typeof api.callImageTool>[1]
type Turn=AiTurn&{voice?:VoiceMessageData;id?:string;action?:ImageAction;assetId?:string;tables?:ExtractedTable[];entities?:ImageUtility['entities'];codes?:ImageUtility['codes'];note?:ImageNote;textAttachments?:TextAttachment[];images?:Asset[];output?:ImageConversationResult;paused?:boolean;failed?:boolean;retry?:{action?:ImageAction;question:string;toolCall?:ImageToolCall;userId:string;context?:RequestContext}}
const attachedImageIds=ref<string[]>([]),imagePreview=ref<Asset>(),speakingId=ref<string>(),readingPaused=ref(false)
const copiedAnswerId=ref<string>()
const voicePlayers=ref<InstanceType<typeof VoiceMessage>[]>([])
let pendingVoice:VoiceMessageData|undefined
function stopVoicePlayback(){for(const player of voicePlayers.value)player.stop()}
const agentStatus=ref('')
const liveFollowupId=ref<string>()
const voiceCall=ref<VoiceCallRecord>()
let copiedAnswerTimer:ReturnType<typeof setTimeout>|undefined
async function copyAnswer(turn:Turn){if(!await copy(turn.text)||disposed)return;clearTimeout(copiedAnswerTimer);copiedAnswerId.value=turn.id;copiedAnswerTimer=setTimeout(()=>copiedAnswerId.value=undefined,2500)}
const draftPictures=computed(()=>pictures.value.filter(p=>attachedImageIds.value.includes(p.source.id)))
const reader=useSpeechPlayer(message=>error.value=message)
watch(reader.state,value=>{readingPaused.value=value==='paused';if(value==='idle')speakingId.value=undefined},{flush:'sync'})
async function readAnswer(turn:Turn){
 stopVoicePlayback()
 if(speakingId.value===turn.id){if(reader.state.value==='loading')reader.stop();else if(readingPaused.value)await reader.resume();else reader.pause();return}
 reader.stop();speakingId.value=turn.id;await reader.play(signal=>api.synthesize(turn.text,signal))
}
function readingLabel(turn:Turn){return speakingId.value===turn.id?(reader.state.value==='loading'?'取消朗读':readingPaused.value?'继续朗读':'暂停朗读'):'朗读消息'}
async function regenerate(turn:Turn){if(busy.value||!turn.retry)return;const user=turns.value.find(t=>t.id===turn.retry!.userId);if(!user)return;if(speakingId.value===turn.id){reader.stop();speakingId.value=undefined;readingPaused.value=false}try{await send(turn.retry.action,turn.retry.question,turn.retry.toolCall,user,turn)}catch{/* The request error is shown in the conversation. */}}
const textAttachments=ref<TextAttachment[]>([]),textPreview=ref<TextAttachment>()
function removeText(id:string){if(busy.value)return;textAttachments.value=textAttachments.value.filter(a=>a.id!==id)}
function visibleTurn(turn:Turn){return turn.textAttachments?.length?turn.text.split('\n\n--- 文本附件：')[0]:turn.text}
const pictures=ref<Picture[]>([]),selectedId=ref<string>(),turns=ref<Turn[]>([]),prompt=ref(''),busy=ref(false),pending=ref(''),error=ref(''),language=ref('zh-CN'),fileInput=ref<HTMLInputElement>(),body=ref<HTMLElement>(),input=ref<HTMLTextAreaElement>()
const selected=computed(()=>pictures.value.find(p=>p.source.id===selectedId.value))
const preparedFollowups=ref<{turnId:string;examples:FollowupExample[]}>()
const followups=computed<FollowupExample[]>(()=>{
 const turn=turns.value.at(-1),picture=selected.value,prepared=preparedFollowups.value
 if(!turn||!prepared||turn.id!==liveFollowupId.value||prepared.turnId!==turn.id||turn.role!=='assistant'||!turn.output||turn.failed||turn.paused||!picture||busy.value||outputPaused.value||turn.assetId!==picture.source.id)return []
 return prepared.examples.filter(example=>!example.requiresUndo||picture.undo.length>0)
})
async function sendFollowup(query:string){if(busy.value||outputPaused.value||voiceRunning.value||restoring.value)return;await send(undefined,query,undefined,undefined,undefined,true)}
const historyOpen=ref(false),restoring=ref(false),sessionId=ref('imagechat-'+crypto.randomUUID()),sessionTitle=ref('截图对话'),sessionCreated=ref(new Date().toISOString()),sessionUpdated=ref(new Date().toISOString()),sessionPinned=ref(false),titleGenerated=ref(false)
let saveQueue:Promise<unknown>=Promise.resolve(),titleJob:string|undefined
function snapshot():Session{
 const assets=new Map<string,Asset>();for(const t of turns.value)for(const a of t.images||[])assets.set(a.id,{...a});for(const p of pictures.value)assets.set(p.source.id,{...p.source})
 const messages:Message[]=turns.value.map(t=>({id:t.id!,role:t.role,text:t.text,voice:t.voice,action:t.action,sources:t.images?.map(a=>a.id),textAttachments:t.textAttachments,paused:t.paused||(!t.text?true:undefined),failed:t.failed,images:t.images,imageOutput:t.output,imageRequest:t.retry?{action:t.retry.action,question:t.retry.question,toolCall:t.retry.toolCall,userId:t.retry.userId,context:t.retry.context}:undefined,imageResult:t.role==='assistant'?{assetId:t.assetId,tables:t.tables,codes:t.codes,entities:t.entities,note:t.note}:undefined}))
 return {id:sessionId.value,title:sessionTitle.value,scenario:'custom',assets:[...assets.values()],messages,voiceCall:voiceCall.value,formula:'',rows:[],createdAt:sessionCreated.value,updatedAt:sessionUpdated.value,pinned:sessionPinned.value,imageConversation:{version:1,selectedId:selectedId.value||null,pictures:pictures.value.map(p=>({assetId:p.source.id,annotations:p.annotations,rendered:p.rendered.data!==p.source.data?p.rendered:undefined})),titleGenerated:titleGenerated.value}}
}
function persist(edited=true){if(restoring.value||!turns.value.some(t=>t.text))return saveQueue;if(edited)sessionUpdated.value=new Date().toISOString();const value=snapshot();saveQueue=saveQueue.catch(()=>{}).then(()=>api.save(value)).catch(e=>{if(!disposed)error.value='会话保存失败：'+(e instanceof Error?e.message:'请重试')});return saveQueue}
async function makeTitle(){const id=sessionId.value;if(titleGenerated.value||titleJob===id||!pictures.value.length)return;titleJob=id;try{await persist();const result=await api.imageTitle(id);if(disposed||sessionId.value!==id||titleGenerated.value)return;sessionTitle.value=result.title.slice(0,18)||'截图对话';titleGenerated.value=true;await persist()}catch{/* Preserve the saved conversation even if title generation fails. */}finally{if(titleJob===id)titleJob=undefined}}
const historyReady=ref<Promise<unknown>>()
function showHistory(){if(busy.value||restoring.value)return;liveFollowupId.value=undefined;preparedFollowups.value=undefined;speech.cancel();reader.stop();speakingId.value=undefined;readingPaused.value=false;historyReady.value=persist(false);historyOpen.value=true}
function historyChanged(item:ImageHistoryItem){if(item.id===sessionId.value){sessionTitle.value=item.title;sessionPinned.value=item.pinned;sessionUpdated.value=item.updatedAt;if(item.titleGenerated)titleGenerated.value=true}}
function historyDeleted(ids:string[]){if(ids.includes(sessionId.value)){sessionId.value='imagechat-'+crypto.randomUUID();sessionCreated.value=new Date().toISOString();sessionUpdated.value=sessionCreated.value;sessionTitle.value='截图对话';sessionPinned.value=false;titleGenerated.value=false;turns.value=[];voiceCall.value=undefined;liveFollowupId.value=undefined;preparedFollowups.value=undefined;restoredOutput.value=undefined;outputPaused.value=false;attachedImageIds.value=pictures.value.map(p=>p.source.id)}}
async function restoreHistory(id:string){if(busy.value||restoring.value)return;restoring.value=true;error.value='';try{await saveQueue;const session=await api.session(id);if(!session.imageConversation)throw new Error('此会话没有截图记录');speech.cancel();reader.stop();speakingId.value=undefined;readingPaused.value=false
 liveFollowupId.value=undefined;preparedFollowups.value=undefined;voiceCall.value=session.voiceCall?{...session.voiceCall,endMessageId:session.voiceCall.endMessageId||session.messages.at(-1)?.id,endedAt:session.voiceCall.endedAt||session.updatedAt}:undefined
 const assets=new Map(session.assets.map(a=>[a.id,a]));pictures.value=session.imageConversation.pictures.flatMap(scene=>{const asset=assets.get(scene.assetId);return asset?[{source:asset,rendered:scene.rendered||asset,annotations:scene.annotations,undo:[]}]:[]});selectedId.value=session.imageConversation.selectedId||pictures.value[0]?.source.id
 turns.value=session.messages.map(m=>({id:m.id,role:m.role,text:m.text||(m.role==='assistant'?'已暂停输出':''),action:m.action as ImageAction|undefined,...m.imageResult,textAttachments:m.textAttachments,voice:m.voice,paused:m.paused,failed:m.failed,output:m.imageOutput,images:m.images||m.sources?.flatMap(id=>assets.has(id)?[assets.get(id)!]:[]),retry:m.imageRequest}))
 sessionId.value=session.id;sessionTitle.value=session.title;sessionCreated.value=session.createdAt;sessionUpdated.value=session.updatedAt;sessionPinned.value=session.pinned;titleGenerated.value=session.imageConversation.titleGenerated||false;prompt.value='';textAttachments.value=[];attachedImageIds.value=[];chosenTool.value=undefined;historyOpen.value=false;const last=turns.value.at(-1);restoredOutput.value=last?.paused&&last.output?.answer&&last.output.answer.startsWith(last.text)&&last.text.length<last.output.answer.length?last:undefined;outputPaused.value=!!restoredOutput.value;await nextTick();body.value?.scrollTo({top:body.value.scrollHeight})
 }catch(e){error.value=e instanceof Error?e.message:'无法打开历史会话'}finally{restoring.value=false}}
const voiceMode=ref(false)
const speech=useSpeechInput(text=>{prompt.value=text;caret.value=text.length;collapsedCaret.value=true},async recognized=>{if(voiceMode.value){const recording=pendingVoice;pendingVoice=undefined;voiceMode.value=false;await nextTick();if(recognized&&recording)await submit(recording);else focusComposer()}},{record:()=>voiceMode.value,onRecording:recording=>pendingVoice=recording})
const {active:voiceActive,starting:voiceStarting,finishing:voiceFinishing,error:voiceError,seconds:voiceSeconds}=speech
const voiceRunning=computed(()=>voiceActive.value||voiceStarting.value||voiceFinishing.value)
function startVoice(){if(busy.value||outputPaused.value||voiceRunning.value)return;pendingVoice=undefined;stopVoicePlayback();reader.stop();closeToolMenu();if(voiceMode.value)speech.start('');else speech.start(prompt.value,input.value?.selectionStart??prompt.value.length,input.value?.selectionEnd??prompt.value.length)}
function toggleDictation(){if(voiceFinishing.value)speech.cancel();else if(voiceRunning.value)speech.stop();else startVoice()}
function toggleVoiceMode(){speech.cancel();voiceMode.value=!voiceMode.value;closeToolMenu();if(!voiceMode.value)focusComposer()}
function beginHold(e:PointerEvent){if(e.button!==0||busy.value)return;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId);startVoice()}
function holdKey(e:KeyboardEvent){if(e.isComposing||e.repeat||![' ','Enter'].includes(e.key))return;e.preventDefault();startVoice()}
function releaseHoldKey(e:KeyboardEvent){if(![' ','Enter'].includes(e.key))return;e.preventDefault();speech.stop()}
function attachmentSize(asset:Asset){const content=asset.data.split(',')[1]||'',bytes=Math.max(0,Math.floor(content.length*3/4)-(content.endsWith('==')?2:content.endsWith('=')?1:0));return bytes>=1024*1024?(bytes/1024/1024).toFixed(1)+' MB':(bytes/1024).toFixed(1)+' KB'}
const conversationRoot=ref<HTMLElement>(),composer=ref<HTMLElement>(),availableTools=ref<ImageToolCommand[]>([]),toolLoading=ref(false),toolError=ref(''),chosenTool=ref<ImageToolCommand>(),targetText=ref(''),bboxText=ref(''),caret=ref(0),collapsedCaret=ref(true),dismissedQuery=ref(''),activeToolIndex=ref(0),menuHeight=ref(360)
const toolListId='image-tools-'+crypto.randomUUID()
let composerObserver:ResizeObserver|undefined
let draftWidth=0
const draftScroll=ref(0)
function resizeDraft(){
 const field=input.value;if(!field||!field.clientWidth)return
 const lineHeight=parseFloat(getComputedStyle(field).lineHeight),limit=Math.ceil(lineHeight*3)
 field.style.height='0px';const contentHeight=field.scrollHeight
 field.style.height=Math.min(limit,Math.max(Math.ceil(lineHeight),contentHeight))+'px'
 field.style.overflowY=contentHeight>limit?'auto':'hidden'
 draftScroll.value=field.scrollTop
}
watch(()=>[prompt.value,chosenTool.value?.name,voiceMode.value,input.value],resizeDraft,{flush:'post'})
const slashToken=computed(()=>collapsedCaret.value?slashQuery(prompt.value,caret.value):undefined)
const querySignature=computed(()=>prompt.value+'@'+caret.value)
const toolMenuOpen=computed(()=>!!slashToken.value&&!busy.value&&dismissedQuery.value!==querySignature.value)
const matchingTools=computed(()=>filterToolCommands(availableTools.value,slashToken.value?.query||''))
const activeTool=computed(()=>matchingTools.value[activeToolIndex.value])
const recommendedTools=computed(()=>{const names=selected.value?['ocr','table','translate']:[];return names.flatMap(name=>{const tool=availableTools.value.find(t=>t.name===name);return tool?[tool]:[]})})
const requiresTarget=computed(()=>chosenTool.value?.required.includes('targetText'))
const requiresBox=computed(()=>chosenTool.value?.required.includes('bbox'))
const canSubmit=computed(()=>{
 if(busy.value||outputPaused.value||toolMenuOpen.value||voiceRunning.value)return false
 if(!chosenTool.value)return !!prompt.value.trim()||textAttachments.value.length>0
 if(!selected.value)return false
 try{buildToolCall(chosenTool.value,prompt.value,targetText.value,bboxText.value,language.value);return true}catch{return false}
})
watch(()=>matchingTools.value.map(t=>t.name).join(','),()=>activeToolIndex.value=0)
async function loadTools(){
 if(toolLoading.value)return;toolLoading.value=true;toolError.value=''
 try{const catalog=await api.imageTools();if(!disposed)availableTools.value=toolCommands(catalog)}catch(e){if(!disposed)toolError.value=e instanceof Error?e.message:'功能列表暂不可用，请重试'}finally{toolLoading.value=false}
}
function syncComposer(){const field=input.value;if(!field)return;caret.value=field.selectionStart;collapsedCaret.value=field.selectionStart===field.selectionEnd;if(dismissedQuery.value!==querySignature.value)dismissedQuery.value=''}
function closeToolMenu(){dismissedQuery.value=querySignature.value}
function outsideComposer(e:PointerEvent){if(toolMenuOpen.value&&!composer.value?.contains(e.target as Node))closeToolMenu()}
async function focusComposer(position=prompt.value.length){await nextTick();input.value?.focus();input.value?.setSelectionRange(position,position);syncComposer()}
function chooseTool(tool:ImageToolCommand,source:'menu'|'example'='menu'){
 const token=slashToken.value
 if(token)prompt.value=(prompt.value.slice(0,token.start)+prompt.value.slice(token.end)).trim()
 if(source==='example')prompt.value=tool.example||tool.summary||tool.description
 chosenTool.value=tool;targetText.value='';bboxText.value='';error.value='';dismissedQuery.value='';focusComposer()
}
function clearTool(){chosenTool.value=undefined;targetText.value='';bboxText.value='';focusComposer()}
async function stepTool(direction:number){if(!matchingTools.value.length)return;activeToolIndex.value=(activeToolIndex.value+direction+matchingTools.value.length)%matchingTools.value.length;await nextTick();document.getElementById(toolListId+'-'+activeTool.value?.name)?.scrollIntoView({block:'nearest'})}
async function submit(voice?:VoiceMessageData){
 if(toolMenuOpen.value){if(activeTool.value)chooseTool(activeTool.value);return}
 if(!chosenTool.value){if(slashToken.value){dismissedQuery.value='';return}await send(undefined,undefined,undefined,undefined,undefined,false,voice);return}
 if(busy.value)return
 try{const tool=chosenTool.value,call=buildToolCall(tool,prompt.value,targetText.value,bboxText.value,language.value);if(!selected.value)throw new Error('请先粘贴、上传或引用截图');const result=await send(tool.name,prompt.value.trim()||tool.label,call,undefined,undefined,false,voice);if(result&&chosenTool.value===tool)clearTool()}catch(e){error.value=e instanceof Error?e.message:'功能调用失败，请重试'}
}
function submitArgument(e:KeyboardEvent){if(e.isComposing||e.keyCode===229)return;e.preventDefault();submit()}
const actions:{id:ImageAction;label:string;icon:string;prompt:string}[]=[
 {id:'ocr',label:'提取文字',icon:'ocr',prompt:'提取截图中的文字'},
 {id:'translate',label:'原位翻译',icon:'translate',prompt:'按原文行位置翻译截图'},
]
let run:AbortController|undefined,disposed=false
let activeAnswer:Turn|undefined
const outputPaused=ref(false)
const restoredOutput=ref<Turn>()
let outputTimer:ReturnType<typeof setTimeout>|undefined,outputStep:(()=>void)|undefined,finishOutput:((completed:boolean)=>void)|undefined
function revealAnswer(answer:Turn,text:string,position=0){
 const characters=Array.from(text)
 if(characters.length<=120){answer.text=text;outputPaused.value=false;return Promise.resolve(true)}
 return new Promise<boolean>(resolve=>{
  finishOutput=resolve;outputPaused.value=false
  outputStep=()=>{if(disposed){cancelReveal();return}if(outputPaused.value)return;position=Math.min(characters.length,position+Math.max(1,Math.ceil(characters.length/40)));answer.text=characters.slice(0,position).join('');nextTick(()=>body.value?.scrollTo({top:body.value.scrollHeight}));if(position===characters.length){outputStep=undefined;finishOutput=undefined;outputTimer=undefined;resolve(true)}else outputTimer=setTimeout(outputStep!,24)}
  outputStep()
 })
}
function cancelReveal(){clearTimeout(outputTimer);outputTimer=undefined;outputStep=undefined;const finish=finishOutput;finishOutput=undefined;outputPaused.value=false;finish?.(false)}
function pauseOutput(){if(outputStep&&activeAnswer?.text){clearTimeout(outputTimer);outputTimer=undefined;outputPaused.value=true;activeAnswer.paused=true;persist()}else stop()}
async function resumeOutput(){
 if(!outputPaused.value)return
 if(outputStep&&activeAnswer){outputPaused.value=false;activeAnswer.paused=false;persist();outputStep();return}
 const answer=restoredOutput.value,response=answer?.output;if(!answer||!response)return
 restoredOutput.value=undefined;const controller=new AbortController();run=controller;activeAnswer=answer;busy.value=true;answer.paused=false;persist()
 try{if(!await revealAnswer(answer,response.answer,Array.from(answer.text).length)||disposed)return
  if(response.action==='table')answer.tables=(response.payload as {tables:ExtractedTable[]}).tables
  if(response.action==='entities')answer.entities=(response.payload as ImageUtility).entities
  if(response.action==='qr')answer.codes=(response.payload as ImageUtility).codes
 }finally{if(run===controller){run=undefined;activeAnswer=undefined;busy.value=false;persist();makeTitle();focusComposer()}}
}
function stop(){speech.cancel();if(run&&activeAnswer){const hadOutput=!!activeAnswer.text;if(!hadOutput)activeAnswer.text='已暂停输出';activeAnswer.paused=true;attachedImageIds.value=[];if(hadOutput||disposed){prompt.value='';textAttachments.value=[]}persist();if(!disposed)makeTitle()}cancelReveal();run?.abort();run=undefined;activeAnswer=undefined;busy.value=false;pending.value=''}
function contextHistory(before?:Turn){let total=0;const result:AiTurn[]=[];const source=before?turns.value.slice(0,turns.value.indexOf(before)):turns.value;for(const t of [...source].reverse()){if(t.paused||t.failed||!t.text)continue;const context=t.role==='assistant'&&t.tables?.length?'\n以下为此前提取表格的节选，引用图片编号 '+(t.assetId||'')+'：\n'+JSON.stringify(t.tables.slice(0,3).map(table=>({title:table.title,rows:table.rows.slice(0,40)}))):'';const text=(t.text+context).slice(0,12000);if(total+text.length>55000||result.length===20)break;total+=text.length;result.unshift({role:t.role,text})}return result}
async function send(action?:ImageAction,question?:string,toolCall?:ImageToolCall,retryUser?:Turn,retryAnswer?:Turn,fromSuggestion=false,voice?:VoiceMessageData){
 const draftSubmission=!retryUser&&!fromSuggestion
 const attachments=(retryUser?.textAttachments||(fromSuggestion?[]:textAttachments.value)).map(a=>({...a})),text=retryUser?.text||attachmentPrompt((question||prompt.value||actions.find(a=>a.id===action)?.prompt||'').trim(),attachments)
 const last=turns.value.at(-1),previous=turns.value.at(-2)
 if(!retryUser&&last?.failed&&previous?.role==='user'&&previous.text===text&&last.retry?.action===action&&last.retry?.toolCall?.name===toolCall?.name){retryUser=previous;retryAnswer=last}
 const saved=retryAnswer?.retry?.context,picture=saved?pictures.value.find(p=>p.source.id===saved.selectedId):selected.value
 if(!text||busy.value||outputPaused.value||disposed||voiceRunning.value)return;if(action&&!picture){error.value='请先粘贴、上传或引用截图';return}
 if(action&&!toolCall)clearTool()
 if((action==='region'||toolCall?.name==='region')&&pictures.value.length>=6){error.value='最多引用 6 张图片，请先移除一张';if(toolCall)throw new Error(error.value);return}
 const assets=saved?.assets||pictures.value.map(p=>({...p.source})),id=saved?.selectedId||picture?.source.id||null,history=saved?.history||contextHistory(retryUser),controller=new AbortController(),signal=AbortSignal.any([controller.signal,AbortSignal.timeout(240000)])
 const user:Turn=retryUser||{id:crypto.randomUUID(),role:'user',text,voice,assetId:id||undefined,textAttachments:attachments.length?attachments:undefined,images:fromSuggestion?[]:draftPictures.value.map(p=>({...p.rendered}))}
 const answer:Turn={id:retryAnswer?.id||crypto.randomUUID(),role:'assistant',text:'',retry:{action,question:question||prompt.value,toolCall,userId:user.id!}}
 liveFollowupId.value=undefined;preparedFollowups.value=retryUser?undefined:{turnId:answer.id!,examples:followupExamples(question||text)}
 if(retryAnswer){const index=turns.value.indexOf(retryAnswer);turns.value.splice(index,1,answer)}else{if(!retryUser)turns.value.push(user);turns.value.push(answer)}
 activeAnswer=turns.value.find(t=>t.id===answer.id)
 run=controller;busy.value=true;error.value='';pending.value=attachments.length?(question||prompt.value||'阅读文本附件'):text
 persist()
 nextTick(()=>{if(run===controller)body.value?.scrollTo({top:body.value.scrollHeight})})
 try{
  const controls=saved?.controls||(picture&&props.controls?await props.controls(picture.source,text):[]);if(signal.aborted||disposed)return
  const call=toolCall&&attachments.length?{...toolCall,arguments:{...toolCall.arguments,prompt:text}}:toolCall
  const context:RequestContext=saved||{assets,selectedId:id,prompt:text,history,existing:JSON.parse(JSON.stringify(picture?.annotations||[])),controls,language:language.value}
  activeAnswer!.retry!.context=context
  await persist();if(signal.aborted||disposed)return
  const undo=picture?.undo.at(-1);if(!saved&&undo)context.undoSnapshot={asset:undo.source,annotations:undo.annotations};context.sessionId=sessionId.value;context.turnId=answer.id;context.userMessageId=user.id;agentStatus.value='正在理解你的要求'
  const response=call?await api.callImageTool(call,context,signal):await api.imageConversation(assets,id,text,history,context.existing,signal,action,context.language,controls,sessionId.value,answer.id,undefined,event=>{if(event.type==='agent_status')agentStatus.value=event.phase==='executing'?'正在'+(agentToolLabels[event.tool||'']||'执行操作'):event.phase==='retrying'?'正在重试工具':'正在分析下一步'},user.id,context.undoSnapshot);if(signal.aborted||disposed)return
  for(const step of imageSteps(response)){
   if(step.action==='restore_image'){
    const removed=(step.payload as {removedImageIds?:string[]}).removedImageIds||[]
    pictures.value=pictures.value.filter(p=>!removed.includes(p.source.id));if(step.assetId)selectedId.value=step.assetId
   }
   const stepPicture=pictures.value.find(p=>p.source.id===step.assetId)
   if(step.assetId&&!stepPicture)throw new Error('工具结果引用未知图片，请重新生成')
   let rendered:Asset|undefined
   if(step.action==='region'){
   if(pictures.value.length>=6)throw new Error('最多引用 6 张图片，请先移除一张')
   const payload=step.payload as {data:string;width:number;height:number;imageId?:string}
   const region:Asset={...stepPicture!.source,...payload,id:payload.imageId||'region-'+crypto.randomUUID(),name:'截图区域 '+(pictures.value.length+1)}
   if(assets.reduce((n,a)=>n+a.data.length,0)+region.data.length>36_000_000)throw new Error('图片总量过大')
   await assetCanvas(region);if(signal.aborted||disposed)return
   pictures.value.push({source:region,rendered:region,annotations:[],undo:[]});selectedId.value=region.id
  }
   if(stepPicture&&step.action!=='region'){
   const picture=stepPicture,before={source:picture.source,rendered:picture.rendered,annotations:picture.annotations}
   const original=picture.source
   if(step.action==='annotate'){const next=annotationEdits(picture.annotations,step.payload as AiAnnotationResult);rendered=await renderAnnotations(original,next);picture.annotations=next}
   else rendered=await applyImageResult(original,step)
   if(signal.aborted||disposed)return
   if(rendered){if(step.action==='restore_image')picture.undo.pop();else picture.undo.push(before);if(picture.undo.length>20)picture.undo.shift();picture.rendered=rendered;if(step.action!=='annotate'){picture.source=rendered;picture.annotations=step.action==='restore_image'?(step.payload as {annotations?:AiExisting[]}).annotations||[]:[];if(picture.annotations.length)picture.rendered=await renderAnnotations(rendered,picture.annotations)}}
  }
   if(props.applyResult)await props.applyResult(step,rendered,signal)
   if(signal.aborted||disposed)return
   emit('result',step,rendered)
  }
  const completed=activeAnswer!;completed.action=response.action;completed.output={...response,answer:response.answer||'没有识别到可确认的内容。'};completed.assetId=id||undefined
  if(!await revealAnswer(completed,response.answer||'没有识别到可确认的内容。')||disposed)return
  liveFollowupId.value=retryUser?undefined:completed.id
  for(const step of imageSteps(response)){if(step.action==='table')completed.tables=(step.payload as {tables:ExtractedTable[]}).tables;if(step.action==='entities')completed.entities=(step.payload as ImageUtility).entities;if(step.action==='qr')completed.codes=(step.payload as ImageUtility).codes}
  if(draftSubmission){prompt.value='';textAttachments.value=[];attachedImageIds.value=[]}return response
 }catch(e){if(!controller.signal.aborted&&!disposed){error.value=e instanceof Error?e.message:'处理失败，请重试';if(activeAnswer)activeAnswer.failed=true}if(toolCall&&!controller.signal.aborted)throw e}
 finally{if(run===controller){if(activeAnswer&&!activeAnswer.text)activeAnswer.text=error.value||'处理失败，请重试';activeAnswer=undefined;run=undefined;busy.value=false;pending.value='';persist();makeTitle();await nextTick();body.value?.scrollTo({top:body.value.scrollHeight});input.value?.focus()}}
}
async function addFiles(files:File[]){if(busy.value)return;error.value='';try{if(files.some(f=>!['image/png','image/jpeg','image/webp'].includes(f.type)))throw new Error('仅接受 PNG、JPEG 和 WebP 图片');if(pictures.value.length+files.length>6)throw new Error('最多引用 6 张图片');const assets=await Promise.all(files.map(readCaptureFile));if(disposed)return;if([...pictures.value.map(p=>p.source),...assets].reduce((n,a)=>n+a.data.length,0)>36_000_000)throw new Error('图片总量过大');for(const asset of assets){pictures.value.push({source:asset,rendered:asset,annotations:[],undo:[]});attachedImageIds.value.push(asset.id)};selectedId.value=assets.at(-1)?.id}catch(e){error.value=e instanceof Error?e.message:'无法读取图片'}}
function upload(e:Event){const el=e.target as HTMLInputElement;addFiles(Array.from(el.files||[]));el.value=''}
function paste(e:ClipboardEvent){
 const files=Array.from(e.clipboardData?.items||[]).filter(i=>i.kind==='file').map(i=>i.getAsFile()).filter((f):f is File=>!!f)
 if(files.length){e.preventDefault();e.stopPropagation();addFiles(files);return}
 const text=e.clipboardData?.getData('text/plain')||''
 if(Array.from(text).length<=800)return
 e.preventDefault();e.stopPropagation();if(busy.value||voiceRunning.value)return
 if(textAttachments.value.length>=6||Array.from(text).length>100000||textAttachments.value.reduce((n,a)=>n+Array.from(a.content).length,0)+Array.from(text).length>200000){error.value='最多添加 6 个文本附件，单个不超过 10 万字符，总计不超过 20 万字符';return}
 textAttachments.value.push(pastedAttachment(text));error.value='';focusComposer()
}
function key(e:KeyboardEvent){
 if(e.isComposing||e.keyCode===229)return
 if(toolMenuOpen.value){
  if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();stepTool(e.key==='ArrowDown'?1:-1);return}
  if((e.key==='Enter'&&!e.shiftKey)||e.key==='Tab'){e.preventDefault();if(activeTool.value)chooseTool(activeTool.value);return}
  if(e.key==='Escape'){e.preventDefault();closeToolMenu();return}
 }
 if(e.key==='Backspace'&&chosenTool.value&&!prompt.value&&caret.value===0){e.preventDefault();clearTool();return}
 if(e.key==='Escape'){e.preventDefault();emit('close')}else if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();submit()}
}
function selectPicture(id:string){if(busy.value)return;selectedId.value=id;imagePreview.value=selected.value?.rendered}
async function copy(text:string){try{if(native)await desktop.copyText(text);else await navigator.clipboard.writeText(text);emit('toast','已复制结果');return true}catch{error.value='复制失败，请重试';return false}}
async function copySheet(table:ExtractedTable,format:'excel'|'csv'|'markdown'='excel'){try{await copyTable(table,format);emit('toast','已复制表格')}catch{error.value='复制失败，请重试'}}
function openUrl(url:string){if(native)desktop.openEntity(url).catch(e=>error.value=String(e));else if(/^(https?:\/\/|mailto:|tel:)/.test(url))window.open(url,'_blank','noopener,noreferrer')}
onMounted(async()=>{
 loadTools();document.addEventListener('pointerdown',outsideComposer,true)
 composerObserver=new ResizeObserver(()=>{const width=input.value?.clientWidth||0;if(width!==draftWidth){draftWidth=width;resizeDraft()}if(conversationRoot.value&&composer.value)menuHeight.value=Math.max(130,Math.min(520,conversationRoot.value.clientHeight-composer.value.offsetHeight-65))});if(conversationRoot.value)composerObserver.observe(conversationRoot.value);if(composer.value)composerObserver.observe(composer.value)
 document.fonts.ready.then(()=>{if(!disposed)resizeDraft()})
 try{for(const a of (props.initial?[props.initial]:[]).slice(0,6)){const c=await assetCanvas(a),asset=canvasAsset(c,a);if(disposed)return;pictures.value.push({source:asset,rendered:asset,annotations:[],undo:[]});attachedImageIds.value.push(asset.id)}selectedId.value=pictures.value[0]?.source.id;await nextTick();input.value?.focus()}catch{error.value='无法读取引用图片，请重新粘贴'}
})
onBeforeUnmount(()=>{disposed=true;stop();clearTimeout(copiedAnswerTimer);reader.stop();composerObserver?.disconnect();document.removeEventListener('pointerdown',outsideComposer,true)})
async function callTool(call:ImageToolCall){
 if(!isImageTool(call.name))throw new Error('请直接在 AI 对话中提出这个需求')
 if(busy.value||disposed)throw new Error('对话正在处理，请稍后调用工具')
 if(call.arguments.imageId){if(!pictures.value.some(p=>p.source.id===call.arguments.imageId))throw new Error('引用图片不存在');selectedId.value=call.arguments.imageId}
 if(!selected.value)throw new Error('请先粘贴、上传或引用截图')
 return send(call.name,call.arguments.prompt||'调用图片工具：'+call.name,call)
}
defineExpose({stop,send,callTool,showHistory})
</script>
<template>
 <section ref="conversationRoot" class="image-conversation" aria-label="图片连续对话" :aria-busy="busy" @paste="paste" @dragover.prevent @drop.prevent.stop="addFiles(Array.from($event.dataTransfer?.files||[]))" @pointerdown.stop @contextmenu.stop @keydown.esc.stop.prevent="emit('close')">
  <ImageConversationHistory v-if="historyOpen" :ready="historyReady" :active-id="sessionId" :active-title="sessionTitle" @close="historyOpen=false" @open="restoreHistory" @changed="historyChanged" @deleted="historyDeleted"/>
  <template v-else>
  <div ref="body" class="image-chat-body" role="log" aria-live="polite">
   <template v-for="(turn,index) in turns" :key="turn.id||index">
   <div v-if="turn.id===voiceCall?.startMessageId" class="chat-call-divider" role="separator" aria-label="语音通话开始"><span><Icon name="voiceCall" :size="14"/>语音通话开始</span></div>
   <article class="image-chat-turn" :class="turn.role">
    <span class="chat-avatar" :aria-label="turn.role==='user'?'用户':'SnapMind'"><Icon v-if="turn.role==='user'" name="user" :size="18"/><SnapMindLogo v-else :size="28"/></span>
    <div class="chat-message-content"><strong v-if="turn.role==='assistant'" class="chat-author">SnapMind</strong>
     <VoiceMessage v-if="turn.role==='user'&&turn.voice" ref="voicePlayers" :voice="turn.voice" :text="turn.text" @error="error=$event" @play="stopVoicePlayback();reader.stop()"/><p v-else-if="turn.role==='user'" class="chat-user-bubble">{{visibleTurn(turn)}}</p>
     <div v-if="turn.role==='user'&&turn.images?.length" class="sent-image-attachments"><button v-for="image in turn.images" :key="image.id" type="button" :aria-label="'查看 '+image.name" @click="imagePreview=image"><img :src="image.data" alt=""/></button></div>
     <div v-if="turn.role==='user'&&turn.textAttachments?.length" class="sent-text-attachments"><button v-for="a in turn.textAttachments" :key="a.id" type="button" @click="textPreview=a"><Icon name="file" :size="16"/><span>{{a.name}}</span></button></div>
     <template v-if="turn.role==='assistant'">
      <div class="chat-assistant-bubble" :class="{'is-loading':!turn.text}"><StudyText v-if="turn.text" :text="turn.text"/><div v-else class="capture-annotation-loading" role="status"><div class="capture-wait-dots" aria-hidden="true"><i/><i/><i/></div><span>{{agentStatus||'正在处理图片'}}</span></div><p v-if="turn.paused&&turn.text!=='已暂停输出'" class="chat-output-paused" role="status">已暂停输出</p>
       <div v-if="turn.tables" class="image-chat-tables"><section v-for="(table,ti) in turn.tables" :key="ti"><strong>{{table.title||'表格 '+(ti+1)}}</strong><div class="chat-table-scroll"><table><tbody><tr v-for="(row,ri) in table.rows" :key="ri"><td v-for="(cell,ci) in row" :key="ci">{{cell}}</td></tr></tbody></table></div><div class="chat-table-actions"><button @click="copySheet(table)">复制到 Excel</button><button @click="copySheet(table,'csv')">CSV</button><button @click="copySheet(table,'markdown')">Markdown</button></div></section></div>
       <div v-for="(entity,ei) in turn.entities||turn.codes||[]" :key="ei" class="image-chat-entity"><span>{{entity.text}}</span><button @click="copy(entity.text)">复制</button><button v-if="entity.url" @click="openUrl(entity.url)">打开</button></div>
      </div>
      <div v-if="turn.text" class="chat-answer-actions"><button type="button" aria-label="复制消息" :data-tooltip="copiedAnswerId===turn.id?'消息已复制':'复制消息'" :class="{copied:copiedAnswerId===turn.id}" @click="copyAnswer(turn)"><Icon :name="copiedAnswerId===turn.id?'check':'copy'" :size="17"/></button><button type="button" aria-label="重新生成" data-tooltip="重新生成" :disabled="busy||outputPaused" @click="regenerate(turn)"><Icon name="rotateLeft" :size="18"/></button><button v-if="!turn.paused" type="button" :aria-label="readingLabel(turn)" :data-tooltip="readingLabel(turn)" :class="{reading:speakingId===turn.id&&reader.state.value==='playing','reading-loading':speakingId===turn.id&&reader.state.value==='loading'}" @click="readAnswer(turn)"><span v-if="speakingId===turn.id&&reader.state.value==='loading'" class="chat-reading-loader" aria-hidden="true"><i/><i/><i/></span><Icon v-else :name="speakingId===turn.id&&!readingPaused?'pause':'speaker'" :size="18"/></button></div>
     </template>
    </div>
   </article>
   <div v-if="turn.id===voiceCall?.endMessageId" class="chat-call-divider" role="separator" aria-label="语音通话结束"><span><Icon name="voiceCall" :size="14"/>语音通话结束</span></div>
   </template>
   <nav v-if="followups.length" class="chat-followups" aria-label="下一步操作示例"><span class="chat-followups-caption">你还可以这样问</span><div class="chat-followup-grid"><button v-for="example in followups" :key="example.query" type="button" class="chat-followup-card" :disabled="busy||outputPaused||voiceRunning||restoring" :aria-label="example.label" @click="sendFollowup(example.query)"><span class="chat-followup-icon"><Icon :name="example.icon" :size="18"/></span><span class="chat-followup-copy"><strong>{{example.label}}</strong><small>{{example.detail}}</small></span><Icon name="right" :size="15" class="chat-followup-arrow"/></button></div></nav>
   <p v-if="error" class="capture-annotation-error" role="alert">{{error}}</p>
  </div>
  <footer ref="composer" class="image-chat-composer">
   <nav v-if="!turns.length&&!busy&&!toolMenuOpen&&recommendedTools.length" class="image-chat-recommendations" aria-label="推荐图片功能"><span>为你推荐</span><button v-for="tool in recommendedTools" :key="tool.name" type="button" :data-recommended-tool="tool.name" :class="{selected:chosenTool?.name===tool.name}" :aria-pressed="chosenTool?.name===tool.name" @click="chooseTool(tool,'example')"><Icon :name="tool.icon" :size="18"/><strong>{{tool.label}}</strong><small>{{tool.summary||tool.description}}</small><Icon v-if="chosenTool?.name===tool.name" name="check" :size="16"/></button></nav>
   <input ref="fileInput" type="file" accept="image/png,image/jpeg,image/webp" multiple hidden @change="upload"/>
   <div class="image-chat-input-box" :class="{'tool-list-open':toolMenuOpen}"><ImageToolMenu v-if="toolMenuOpen" :id="toolListId" :tools="matchingTools" :active="activeTool?.name" :loading="toolLoading" :error="toolError" :max-height="menuHeight" @choose="chooseTool" @hover="name=>activeToolIndex=matchingTools.findIndex(t=>t.name===name)" @retry="loadTools"/>
    <div v-if="draftPictures.length||textAttachments.length" class="image-chat-attachments"><div v-for="a in textAttachments" :key="a.id" class="chat-image-chip text-attachment-chip"><button type="button" :aria-label="a.name" @click="textPreview=a"><span class="text-attachment-icon"><Icon name="file" :size="24"/></span><span><strong>{{a.name}}</strong><small>{{attachmentBytes(a.content)}}</small></span></button><button type="button" :disabled="busy||outputPaused" :aria-label="'移除 '+a.name" @click="removeText(a.id)"><Icon name="close" :size="16"/></button></div><div v-for="p in draftPictures" :key="p.source.id" class="chat-image-chip" :class="{active:selectedId===p.source.id}"><button :disabled="busy||outputPaused" :aria-label="'引用 '+p.source.name" @click="selectPicture(p.source.id)"><img :src="p.rendered.data" alt=""/><span><strong>{{p.source.name}}</strong><small>{{attachmentSize(p.rendered)}}</small></span></button></div></div>
    <div v-if="!voiceMode" class="image-chat-draft" :style="{'--draft-indent':chosenTool?(31+chosenTool.label.length*13)+'px':'0px'}"><span v-if="chosenTool" class="image-tool-selection" :style="{transform:'translateY(-'+draftScroll+'px)'}"><Icon :name="chosenTool.icon" :size="18"/><span>{{chosenTool.label}}</span></span><textarea ref="input" v-model="prompt" :disabled="voiceRunning||busy||outputPaused" aria-label="图片对话输入" :aria-expanded="toolMenuOpen" :aria-controls="toolMenuOpen?toolListId:undefined" :aria-activedescendant="toolMenuOpen&&activeTool?toolListId+'-'+activeTool.name:undefined" aria-autocomplete="list" :placeholder="chosenTool?'写下要让「'+chosenTool.label+'」处理的内容':'输入问题直接提问，也可选择功能或输入 / 查看能力列表'" rows="1" maxlength="3000" @scroll="draftScroll=($event.target as HTMLTextAreaElement).scrollTop" @input="syncComposer" @click="syncComposer" @keyup="syncComposer" @select="syncComposer" @keydown.stop="key"/></div>
    <div v-if="requiresTarget||requiresBox" class="image-tool-arguments">
     <label v-if="requiresTarget"><span>截图原文</span><input v-model="targetText" :disabled="busy||outputPaused" aria-label="功能目标原文" placeholder="输入需要处理的具体原文" maxlength="300" @keydown.enter="submitArgument"/></label>
     <label v-if="requiresBox"><span>区域坐标</span><input v-model="bboxText" :disabled="busy||outputPaused" aria-label="功能区域坐标" placeholder="左, 上, 右, 下（图片像素）" maxlength="150" @keydown.enter="submitArgument"/></label>
    </div>
    <button v-if="voiceMode" type="button" class="image-chat-hold" :class="{recording:voiceRunning}" :disabled="busy||outputPaused" aria-label="按住说话" :aria-pressed="voiceRunning" @pointerdown.prevent="beginHold" @pointerup="speech.stop" @pointercancel="speech.cancel" @lostpointercapture="speech.stop" @keydown.stop="holdKey" @keyup.stop="releaseHoldKey" @blur="speech.stop"><span class="image-chat-hold-icon"><Icon name="microphone" :size="24"/></span><span><strong>{{voiceFinishing?'正在识别…':voiceStarting?'正在连接…':voiceActive?'正在聆听 '+voiceSeconds+'s':'按住说话'}}</strong><small>{{voiceFinishing?'识别完成后发送':voiceRunning?'松开后识别并发送':'按住开始录音'}}</small></span><span class="image-chat-wave" aria-hidden="true"><i v-for="n in 12" :key="n" :style="{height:(8+(n*7)%22)+'px',animationDelay:n*.07+'s'}"/></span></button>
    <p v-if="voiceRunning&&!voiceMode" class="image-chat-voice-status" role="status">{{voiceFinishing?'正在完成识别…':voiceStarting?'正在连接语音识别…':'正在聆听 · '+voiceSeconds+'s'}}</p>
    <p v-if="voiceError" class="image-chat-voice-error" role="alert">{{voiceError}}</p>
    <div class="image-chat-input-toolbar"><div class="image-chat-input-tools">
     <button type="button" :disabled="busy||outputPaused||pictures.length>=6" aria-label="粘贴／上传图片" title="粘贴或上传图片" @click="fileInput?.click()"><Icon name="attach" :size="21"/></button>
     <button type="button" :disabled="busy||outputPaused" :aria-label="voiceMode?'切换文字输入':'语音输入'" :aria-pressed="voiceMode" :title="voiceMode?'切换文字输入':'语音输入'" @click="toggleVoiceMode"><Icon :name="voiceMode?'keyboard':'voice'" :size="23"/></button>
    </div><div v-if="!voiceMode" class="image-chat-input-send"><button type="button" class="image-chat-microphone" :class="{recording:voiceRunning}" :disabled="busy||outputPaused" :aria-pressed="voiceRunning" :aria-label="voiceFinishing?'取消语音识别':voiceRunning?'停止语音转文字':'语音转文字'" :title="voiceFinishing?'取消语音识别':voiceRunning?'停止语音转文字':'语音转文字'" @click="toggleDictation"><Icon name="microphone" :size="22"/></button><button class="image-chat-submit" :class="{stopping:busy}" :disabled="!busy&&!outputPaused&&!canSubmit" :aria-label="outputPaused?'继续输出':busy?'暂停输出':'发送图片对话'" :data-tooltip="outputPaused?'继续输出':busy?'暂停输出':'发送'" @click="outputPaused?resumeOutput():busy?pauseOutput():submit()"><Icon v-if="outputPaused" name="play" :size="22" class="chat-output-resume"/><span v-else-if="busy" class="chat-stop-square" aria-hidden="true"/><Icon v-else name="paperSend" :size="23"/></button></div></div>
   </div>
   <div class="image-chat-composer-meta"><small>Enter 发送 · Shift+Enter 换行 · Ctrl+V 粘贴图片</small></div>
  </footer>
  <ImageAttachmentPreview v-if="imagePreview" :asset="imagePreview" @close="imagePreview=undefined"/>
  <TextAttachmentPreview v-if="textPreview" :attachment="textPreview" @close="textPreview=undefined"/>
  </template>
 </section>
</template>
