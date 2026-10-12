<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Circle, Check, X, RectangleHorizontal, Square, Droplet, Pipette, MousePointer2, RefreshCw,Eye,EyeOff } from 'lucide-vue-next'
import Icon from './Icon.vue'
import CaptureDropdown from './CaptureDropdown.vue'
import CaptureToolGlyph from './CaptureToolGlyph.vue'
import ImageConversation from './ImageConversation.vue'
import VoiceSpirit from './VoiceSpirit.vue'
import type {VoiceCallRequest} from '../voice-call'
import {toolShortcuts,shortcutTool,liveScrollKeys,type CaptureToolId} from '../tool-shortcuts'
import {assetCanvas,applyImageResult,annotationEdits,renderAnnotations} from '../image-actions'
import {imageSteps} from '../agent-results'
import type {ImageConversationResult,AiAnnotationResult,ObjectDetection,AiExisting} from '../api'
import type { Asset } from '../types'
import type { CaptureResult } from '../capture'
import {native,desktop} from '../desktop'
import {api,type LocatedText} from '../api'
import {paintObject} from '../capture-analysis'
import {captureControls} from '../capture-controls'
import {paintAi,moveBubble,aiAnchor,type AiPaint} from '../ai-callouts'
import {paintTranslation,translationRows,translationPlainText,translationFont,type PaintedTranslationLine} from '../inline-translation'
import {scrollOffset} from '../scroll-stitch'
import {paintBrush,type BrushShape} from '../capture-brush'
import {observePreviewRegions} from '../floating-preview-regions'
import {afterPaint,canvasPng} from '../ui-response'
const props=defineProps<{source:Asset;closing?:boolean;initialSelection?:boolean;floatingPreview?:boolean}>()
const emit=defineEmits<{finish:[result:CaptureResult];cancel:[];toast:[text:string];ready:[];edit:[asset:Asset]}>()
type Rect={x:number;y:number;w:number;h:number}
// Immutable transparent layers keep source pixels intact; undo snapshots only copy positions.
type Mark=Rect&{id:number;image:HTMLCanvasElement;movable:boolean;kind:string;ai?:AiPaint;textInfo?:{value:string;size:number;color:string;anchor:{x:number;y:number}}}
type TranslationScene={markId:number;rect:Rect;lines:PaintedTranslationLine[];language:string}
type SceneUndo={marks:Mark[];number:number;translation?:TranslationScene}
let marks:Mark[]=[],markId=0,baseImage:HTMLCanvasElement|undefined,inkLayer:HTMLCanvasElement|undefined,markBefore:Mark[]=[],dragMark:Mark|undefined,dragAiTarget=false
const selectedMark=ref<number>(),hoverMark=ref<number>(),sceneVersion=ref(0)
function sceneSnapshot(){return marks.map(mark=>({...mark}))}
function paintMark(g:CanvasRenderingContext2D,mark:Mark){g.save();if(mark.kind==='highlight')g.globalCompositeOperation='multiply';g.drawImage(mark.image,mark.x,mark.y);g.restore()}
function redraw(){const g=canvas.value!.getContext('2d')!;g.clearRect(0,0,props.source.width,props.source.height);if(baseImage)g.drawImage(baseImage,0,0);for(const mark of marks)if(mark.kind!=='translation'||translationVisible.value)paintMark(g,mark);if(inkLayer){g.save();if(tool.value==='highlight')g.globalCompositeOperation='multiply';if(['heal','lift'].includes(tool.value))g.globalAlpha=.35;g.drawImage(inkLayer,0,0);g.restore()}sceneVersion.value++}
function beginInk(){markBefore=sceneSnapshot();inkLayer=document.createElement('canvas');inkLayer.width=props.source.width;inkLayer.height=props.source.height;before=ctx().getImageData(0,0,props.source.width,props.source.height)}
function finishInk(){
 const layer=inkLayer,r=selection.value;if(!layer||!r)return false
 const x=Math.max(0,Math.floor(r.x)),y=Math.max(0,Math.floor(r.y)),w=Math.min(layer.width-x,Math.ceil(r.w)),h=Math.min(layer.height-y,Math.ceil(r.h));if(w<1||h<1){inkLayer=undefined;redraw();return false}
 const data=layer.getContext('2d')!.getImageData(x,y,w,h).data;let left=w,top=h,right=-1,bottom=-1
 for(let py=0;py<h;py++)for(let px=0;px<w;px++)if(data[(py*w+px)*4+3]){left=Math.min(left,px);right=Math.max(right,px);top=Math.min(top,py);bottom=Math.max(bottom,py)}
 inkLayer=undefined;before=undefined
 if(right<left){redraw();return false}
 const image=document.createElement('canvas');image.width=right-left+1;image.height=bottom-top+1;image.getContext('2d')!.drawImage(layer,x+left,y+top,image.width,image.height,0,0,image.width,image.height)
 marks.push({id:++markId,image,x:x+left,y:y+top,w:image.width,h:image.height,movable:!['mosaic','blur'].includes(tool.value),kind:tool.value});redraw();return true
}
function hitMark(p:{x:number;y:number}){
 if(!selection.value||!inside(p,selection.value))return undefined
 const pad=6/scale.value
 for(let i=marks.length-1;i>=0;i--){const mark=marks[i]!;if(!mark.movable||!inside(p,{x:mark.x-pad,y:mark.y-pad,w:mark.w+pad*2,h:mark.h+pad*2}))continue
  if(['text','number'].includes(mark.kind))return mark
  const x=Math.max(0,Math.floor(p.x-mark.x-pad)),y=Math.max(0,Math.floor(p.y-mark.y-pad)),w=Math.min(mark.w-x,Math.ceil(pad*2+1)),h=Math.min(mark.h-y,Math.ceil(pad*2+1));if(w<=0||h<=0)continue
  const pixels=mark.image.getContext('2d')!.getImageData(x,y,w,h).data;for(let n=3;n<pixels.length;n+=4)if(pixels[n])return mark
 }
}
const selectedMarkStyle=computed(()=>{sceneVersion.value;const mark=marks.find(m=>m.id===selectedMark.value);return mark?{left:(mark.x*scale.value+imagePos.value.x-3)+'px',top:(mark.y*scale.value+imagePos.value.y-3)+'px',width:(mark.w*scale.value+6)+'px',height:(mark.h*scale.value+6)+'px'}:undefined})

const root=ref<HTMLElement>(),canvas=ref<HTMLCanvasElement>(),selection=ref<Rect>(),tool=ref('select'),color=ref('#f05252'),stroke=ref(3),annotation=ref(''),undoStack=ref<SceneUndo[]>([]),drawing=ref(false),ready=ref(false),number=ref(1),showAi=ref(false),showOptions=ref(false),completing=ref(false)
const viewport=ref({w:window.innerWidth,h:window.innerHeight})
const palette=['#f05252','#2d7df2','#37a575','#f5bd42','#333333','#999999','#ffffff']
const highlightPalette=['#fff1a8','#cceeff','#d6f4cb','#ffe0e8','#e6dcff','#ffe7c6']
const highlightColor=ref(highlightPalette[0]!),highlightShape=ref<BrushShape>('square'),highlightSize=ref(24),repairShape=ref<BrushShape>('circle'),repairSize=ref(32)
type ProcessAction='ocr'|'translate'
const processing=ref(false),resultText=ref(''),resultError=ref(''),resultAction=ref<ProcessAction>(),resultLanguage=ref('zh-CN'),rgbMode=ref(false)
const conversationOpen=ref(false),conversationAsset=ref<Asset>(),conversationPanel=ref<InstanceType<typeof ImageConversation>>()
const voiceOpen=ref(false),voiceAsset=ref<Asset>(),voiceRendered=ref<Asset>(),voiceAnnotations=ref<AiExisting[]>([]),voicePanel=ref<InstanceType<typeof VoiceSpirit>>()
let conversationBounds:Rect|undefined
let conversationMarkIds=new Map<string,number>()
const openingPanel=ref<'chat'|'voice'>()
let panelGeneration=0
function cancelOpening(){panelGeneration++;openingPanel.value=undefined}
function closeConversation(){if(openingPanel.value==='chat')cancelOpening();if(!conversationOpen.value)return;conversationPanel.value?.stop();conversationOpen.value=false;if(tool.value==='chat')tool.value='select'}
function closeVoice(){if(openingPanel.value==='voice')cancelOpening();voicePanel.value?.stop();voiceOpen.value=false}
let voiceUndo:{asset:Asset;annotations:AiExisting[];bounds:{x:number;y:number;w:number;h:number}|undefined;marks:ReturnType<typeof sceneSnapshot>;ids:Map<string,number>}[]=[]
async function openVoice(){
 if(openingPanel.value)return
 voiceUndo=[]
 closeConversation();commitText();closeResult();cancelTranslation();const c=output();if(!c||!selection.value)return
 const bounds={...selection.value},generation=++panelGeneration;openingPanel.value='voice';showOptions.value=false
 try{await afterPaint();if(disposed||generation!==panelGeneration)return;const data=await canvasPng(c);if(disposed||generation!==panelGeneration)return
 conversationBounds=bounds;voiceAsset.value={id:'voice-'+crypto.randomUUID(),name:'截图',data,width:c.width,height:c.height,scenario:'custom'};conversationAsset.value=voiceAsset.value;voiceAnnotations.value=[];voiceRendered.value=undefined;conversationMarkIds=new Map();voiceOpen.value=true;tool.value='select';pointer.value=undefined
 }catch{if(!disposed&&generation===panelGeneration)emit('toast','无法准备截图，请重试')}finally{if(generation===panelGeneration)openingPanel.value=undefined}
}
async function executeVoice(request:VoiceCallRequest,signal:AbortSignal,onChunk?:(text:string)=>void){
 const asset=voiceAsset.value;if(!asset||!voiceOpen.value||signal.aborted)throw new Error('语音通话已结束')
 const existing=JSON.parse(JSON.stringify(voiceAnnotations.value)) as AiExisting[],controls=await conversationControls(asset,request.prompt)
 if(signal.aborted||!voiceOpen.value)throw new Error('操作已中断')
 const previous=voiceUndo.at(-1)
 const result=await api.imageConversation([asset],asset.id,request.prompt,request.history,existing,signal,undefined,'zh-CN',controls,request.sessionId,request.turnId,onChunk,undefined,request.turnId,previous?{asset:previous.asset,annotations:previous.annotations}:undefined)
 if(signal.aborted||!voiceOpen.value)throw new Error('操作已中断')
 const working=new Map<string,Asset>([[asset.id,asset]]),bounds=new Map([[asset.id,conversationBounds?{...conversationBounds}:undefined]])
 for(const step of imageSteps(result)){
  if(step.action==='restore_image'&&voiceUndo.length){
   const saved=voiceUndo.pop()!,p=step.payload as {data:string;width:number;height:number;annotations:AiExisting[]}
   pushSceneUndo();marks=saved.marks;conversationBounds=saved.bounds;conversationMarkIds=saved.ids
   voiceAsset.value={...saved.asset,data:p.data,width:p.width,height:p.height};conversationAsset.value=voiceAsset.value;voiceAnnotations.value=p.annotations
   if(saved.bounds)selection.value={...saved.bounds};redraw();continue
  }
  if(step.action==='restore_image'&&step.assetId){
   const restored=working.get(step.assetId);if(!restored)throw new Error('撤销结果引用未知截图')
   voiceAsset.value=restored;conversationAsset.value=restored;conversationBounds=bounds.get(step.assetId)
  }
  const current=voiceAsset.value!
  if(step.assetId!==current.id)throw new Error('工具结果与截图不一致，请重新提问')
  const snapshot={asset:current,annotations:JSON.parse(JSON.stringify(voiceAnnotations.value)) as AiExisting[],bounds:conversationBounds?{...conversationBounds}:undefined,marks:sceneSnapshot(),ids:new Map(conversationMarkIds)}
  if(step.action==='region'){
   const p=step.payload as {data:string;width:number;height:number;imageId:string;bbox:number[]}
   voiceAsset.value={...current,id:p.imageId,data:p.data,width:p.width,height:p.height}
   if(conversationBounds)conversationBounds={...conversationBounds,x:conversationBounds.x+p.bbox[0]!,y:conversationBounds.y+p.bbox[1]!,w:p.width,h:p.height}
   conversationAsset.value=voiceAsset.value;voiceAnnotations.value=[];voiceUndo.push(snapshot);working.set(p.imageId,voiceAsset.value);bounds.set(p.imageId,conversationBounds?{...conversationBounds}:undefined);continue
  }
  const annotations=step.action==='annotate'?annotationEdits(voiceAnnotations.value,step.payload as AiAnnotationResult):voiceAnnotations.value
  let rendered=step.action==='annotate'?undefined:await applyImageResult(current,step)
  const restoredAnnotations=step.action==='restore_image'?(step.payload as {annotations?:AiExisting[]}).annotations||[]:[]
  if(rendered&&restoredAnnotations.length)rendered=await renderAnnotations(rendered,restoredAnnotations)
  if(signal.aborted||!voiceOpen.value)throw new Error('操作已中断')
  await applyConversation(step,rendered,signal)
  if(rendered||step.action==='annotate')voiceUndo.push(snapshot);if(voiceUndo.length>20)voiceUndo.shift()
  voiceAnnotations.value=annotations
  if(rendered&&step.action!=='detect'){voiceAsset.value=rendered;conversationAsset.value=rendered;voiceAnnotations.value=restoredAnnotations}
  working.set(voiceAsset.value!.id,voiceAsset.value!);if(!bounds.has(voiceAsset.value!.id))bounds.set(voiceAsset.value!.id,conversationBounds?{...conversationBounds}:undefined)
 }
 const c=output();if(c)voiceRendered.value={...voiceAsset.value!,data:c.toDataURL('image/png'),width:c.width,height:c.height}
 return result
}
async function openConversation(){
 if(openingPanel.value)return
 closeVoice()
 commitText();closeResult();cancelTranslation(); const c=output();if(!c||!selection.value)return
 const bounds={...selection.value},generation=++panelGeneration;openingPanel.value='chat';showOptions.value=false
 try{await afterPaint();if(disposed||generation!==panelGeneration)return;const data=await canvasPng(c);if(disposed||generation!==panelGeneration)return
 conversationBounds=bounds;conversationAsset.value={id:'conversation-'+Date.now(),name:'当前截图',data,width:c.width,height:c.height,scenario:'custom'}
 conversationMarkIds=new Map()
 conversationOpen.value=true;tool.value='chat';showOptions.value=false;pointer.value=undefined
 }catch{if(!disposed&&generation===panelGeneration)emit('toast','无法准备截图，请重试')}finally{if(generation===panelGeneration)openingPanel.value=undefined}
}
async function conversationControls(asset:Asset,prompt:string){if(!conversationBounds||asset.id!==conversationAsset.value?.id||asset.data!==conversationAsset.value.data||!/按钮|输入框|控件|菜单|button|input|control/i.test(prompt))return [];return captureControls(props.source.id,conversationBounds,marks.filter(m=>!m.ai))}
async function applyConversation(result:ImageConversationResult,rendered?:Asset,signal?:AbortSignal){
 if(signal?.aborted)return
 if(!conversationBounds||result.assetId!==conversationAsset.value?.id){if(rendered||['annotate','detect'].includes(result.action))throw new Error('该会话引用的图片不是当前截图，请关闭历史会话后重新打开当前截图对话');return}
 const r=conversationBounds
 if(result.action==='detect'){
  const detection=result.payload as ObjectDetection
  if(detection.width!==r.w||detection.height!==r.h||detection.coordinateSpace!=='image-pixels')throw new Error('物体坐标与截图尺寸不一致')
  const layers=detection.objects.map((object,i)=>paintObject(object,r.w,r.h,scale.value,i))
  pushSceneUndo();marks=marks.filter(m=>m.kind!=='conversation-detection')
  for(const layer of layers)marks.push({...layer,x:r.x+layer.x,y:r.y+layer.y,id:++markId,movable:true,kind:'conversation-detection'})
  redraw();return
 }
 if(result.action==='annotate'){
  const edits=(result.payload as AiAnnotationResult).annotations
  if(!edits.length)return
  let next=sceneSnapshot(),nextId=markId,localId=Math.max(0,...Array.from(conversationMarkIds.keys()).map(id=>Number(id.slice(3)))),ids=new Map(conversationMarkIds)
  for(const edit of edits){
   const local=edit.operation==='add'?'ai-'+(++localId):edit.id!,id=ids.get(local),index=next.findIndex(m=>m.id===id)
   if(edit.operation==='remove'){if(index>=0)next.splice(index,1);ids.delete(local);continue}
   const spec:AiPaint={...edit,bbox:edit.bbox.map((v,i)=>v+(i%2===0?r.x:r.y)) as [number,number,number,number],edgeAnchor:['ocr','uia'].includes(edit.locationSource||'')},layer=paintAi(spec,r,scale.value,next.filter(m=>m.ai?.bubble).map(m=>m.ai!.bubble!)),mark:Mark={...layer,id:index>=0?id!:++nextId,movable:true,kind:'conversation-ai'}
   if(index>=0)next[index]=mark;else next.push(mark);ids.set(local,mark.id)
  }
  pushSceneUndo();marks=next;markId=nextId;conversationMarkIds=ids;redraw();return
 }
 if(rendered){const c=await assetCanvas(rendered);if(disposed||signal?.aborted||(!conversationOpen.value&&!voiceOpen.value))return;pushSceneUndo();marks=marks.filter(m=>!['conversation','conversation-ai','conversation-study','conversation-study-'+result.assetId].includes(m.kind));conversationMarkIds.clear();marks.push({id:++markId,image:c,x:r.x,y:r.y,w:c.width,h:c.height,movable:false,kind:'conversation'});if(result.action==='crop'){selection.value={...r,w:c.width,h:c.height};conversationBounds={...selection.value}}redraw()}
}
const redoStack=ref<SceneUndo[]>([]),repairBusy=ref(false)
let repairMask:HTMLCanvasElement|undefined,repairController:AbortController|undefined
let editingTextMark:number|undefined
function redo(){if(drawing.value||repairBusy.value)return;const next=redoStack.value.pop();if(!next)return;undoStack.value.push({marks:sceneSnapshot(),number:number.value,translation:translationScene.value});marks=next.marks.map(m=>({...m}));number.value=next.number;translationScene.value=next.translation;selectedMark.value=undefined;redraw()}
function clearMarks(){if(drawing.value||repairBusy.value||!marks.length)return;pushSceneUndo();marks=[];translationScene.value=undefined;selectedMark.value=undefined;redraw()}
function prepareRepair(){repairMask=document.createElement('canvas');repairMask.width=props.source.width;repairMask.height=props.source.height;const g=repairMask.getContext('2d')!;g.fillStyle='#000';g.fillRect(0,0,repairMask.width,repairMask.height);if(tool.value==='heal')repairStroke(start)}
function repairStroke(p:{x:number;y:number}){if(!repairMask||!selection.value)return;const r=selection.value;for(const [layer,color] of [[repairMask,'#fff'],[inkLayer!,'#af68ff']] as const){const g=layer.getContext('2d')!;g.save();g.beginPath();g.rect(r.x,r.y,r.w,r.h);g.clip();paintBrush(g,previous,p,repairSize.value/scale.value,repairShape.value,color);g.restore()}previous=p;redraw()}
async function completeRepair(extract:boolean){
 const r=selection.value,mask=repairMask;if(!r||!mask)return
 const source=output();inkLayer=undefined;before=undefined;repairMask=undefined;redraw();if(!source)return
 // Do not send the purple preview to the repair engine.
 source.getContext('2d')!.clearRect(0,0,source.width,source.height);source.getContext('2d')!.drawImage(canvas.value!,r.x,r.y,r.w,r.h,0,0,r.w,r.h)
 const croppedMask=document.createElement('canvas');croppedMask.width=source.width;croppedMask.height=source.height;croppedMask.getContext('2d')!.drawImage(mask,r.x,r.y,r.w,r.h,0,0,r.w,r.h)
 const controller=new AbortController();repairController=controller;repairBusy.value=true
 try{await afterPaint();if(controller.signal.aborted||disposed)return;const asset:Asset={id:'repair-'+Date.now(),name:'截图',data:await canvasPng(source),width:source.width,height:source.height,scenario:'custom'},result=await api.repairImage(asset,await canvasPng(croppedMask),extract,AbortSignal.any([controller.signal,AbortSignal.timeout(60000)]));if(controller.signal.aborted||disposed)return;const fixed=await assetCanvas({...asset,...result}),layer=result.layer?await assetCanvas({...asset,data:result.layer.data,width:result.layer.bbox[2]-result.layer.bbox[0],height:result.layer.bbox[3]-result.layer.bbox[1]}):undefined;if(controller.signal.aborted||disposed)return;maskRepair(fixed,croppedMask);pushSceneUndo();marks.push({id:++markId,image:fixed,x:r.x,y:r.y,w:fixed.width,h:fixed.height,movable:false,kind:'repair'});if(layer&&result.layer){const [l,t,right,bottom]=result.layer.bbox;marks.push({id:++markId,image:layer,x:r.x+l,y:r.y+t,w:right-l,h:bottom-t,movable:true,kind:'lift'});selectedMark.value=markId;tool.value='objects';showOptions.value=false}redraw();emit('toast',extract?'已提取透明图层，可拖动、缩放或删除':'已修补涂抹区域，可撤销')}catch(e){if(!controller.signal.aborted)emit('toast',e instanceof Error?e.message:'修补失败')}finally{if(repairController===controller){repairBusy.value=false;repairController=undefined}}
}
function maskRepair(image:HTMLCanvasElement,mask:HTMLCanvasElement){const g=image.getContext('2d')!,pixels=g.getImageData(0,0,image.width,image.height),maskPixels=mask.getContext('2d')!.getImageData(0,0,mask.width,mask.height).data;for(let i=3;i<pixels.data.length;i+=4)if(maskPixels[i-3]!<=127)pixels.data[i]=0;g.putImageData(pixels,0,0)}
let markResize:{id:number;x:number;y:number;w:number;h:number;startX:number;startY:number;image:HTMLCanvasElement}|undefined
function beginMarkResize(e:PointerEvent){const mark=marks.find(m=>m.id===selectedMark.value);if(!mark||mark.ai||!mark.movable)return;markBefore=sceneSnapshot();markResize={id:mark.id,x:mark.x,y:mark.y,w:mark.w,h:mark.h,startX:e.clientX,startY:e.clientY,image:mark.image};(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}
function moveMarkResize(e:PointerEvent){const initial=markResize,r=selection.value;if(!initial||!r)return;const mark=marks.find(m=>m.id===initial.id)!;mark.w=Math.max(4,Math.min(r.x+r.w-mark.x,initial.w+(e.clientX-initial.startX)/scale.value));mark.h=Math.max(4,Math.min(r.y+r.h-mark.y,initial.h+(e.clientY-initial.startY)/scale.value));const c=document.createElement('canvas');c.width=mark.w;c.height=mark.h;c.getContext('2d')!.drawImage(initial.image,0,0,c.width,c.height);mark.image=c;redraw()}
function endMarkResize(){if(!markResize)return;pushSceneUndo(markBefore);markResize=undefined}

function requestCancel(){cancelOpening();emit('cancel')}
const translationScene=ref<TranslationScene>(),translationVisible=ref(true),translationBusy=ref(false),translationPhase=ref(''),translationError=ref(''),translationTextLayer=ref<HTMLElement>()
let translationController:AbortController|undefined,translationCache:{data:string;location:LocatedText}|undefined
const visibleTranslationLines=computed(()=>{const scene=translationScene.value,r=selection.value;if(!scene||!r||!translationVisible.value||translationBusy.value)return [];return scene.lines.filter(l=>l.x+scene.rect.x+l.width>r.x&&l.x+scene.rect.x<r.x+r.w&&l.y+scene.rect.y+l.height>r.y&&l.y+scene.rect.y<r.y+r.h)})
const selectableTranslationRows=computed(()=>translationRows(visibleTranslationLines.value))
const allTranslatedText=computed(()=>translationPlainText(visibleTranslationLines.value))
function translationLineStyle(line:PaintedTranslationLine){const scene=translationScene.value!,r=selection.value!;return {left:(scene.rect.x+line.x-r.x)*scale.value+'px',top:(scene.rect.y+line.y-r.y)*scale.value+'px',width:line.width*scale.value+'px',height:line.height*scale.value+'px',fontSize:line.fontSize*scale.value+'px',lineHeight:line.fontSize*scale.value+'px',fontFamily:translationFont}}
function cancelTranslation(){translationController?.abort();translationController=undefined;translationBusy.value=false;translationPhase.value=''}
function toggleOriginal(){translationVisible.value=!translationVisible.value;window.getSelection()?.removeAllRanges();redraw()}
function pushSceneUndo(m=sceneSnapshot(),sequence=number.value){redoStack.value=[];undoStack.value.push({marks:m,number:sequence,translation:translationScene.value});if(undoStack.value.length>50)undoStack.value.shift()}
async function startTranslation(){
 
 if(!selection.value||completing.value||disposed)return
 commitText();closeResult();cancelTranslation();tool.value='translate';showOptions.value=false;selectedMark.value=undefined;pointer.value=undefined
 const bounds={...selection.value},source=output(false);if(!source)return
 const controller=new AbortController();translationController=controller;const signal=AbortSignal.any([controller.signal,AbortSignal.timeout(240000)])
 translationBusy.value=true;translationError.value='';translationVisible.value=false;translationPhase.value='正在定位文字';redraw()
 try{
  await afterPaint();if(signal.aborted||disposed)return
  const data=await canvasPng(source);if(signal.aborted||disposed)return
  const asset:Asset={id:'translate-'+Date.now(),name:'截图',data,width:source.width,height:source.height,scenario:'custom'}
  const location=translationCache?.data===data?translationCache.location:await api.locateCapture(asset,signal,'line')
  if(signal.aborted||disposed)return
  if(location.width!==asset.width||location.height!==asset.height)throw new Error('文字坐标与截图尺寸不一致，请重新翻译')
  const lines=location.regions.filter(r=>r.granularity==='line'&&r.text.trim())
  if(!lines.length){translationPhase.value='未找到可翻译的文字';emit('toast',translationPhase.value);return}
  if(lines.length!==location.regions.length)throw new Error('未获取到完整的文字行位置，请重新翻译')
  translationCache={data,location};translationPhase.value='正在翻译'
  const result=await api.translateInline(asset,lines,resultLanguage.value,signal)
  if(signal.aborted||disposed)return
  if(result.width!==source.width||result.height!==source.height||result.lines.length!==lines.length)throw new Error('译文与截图不完整对应，请重新翻译')
  const painted=paintTranslation(source,result);pushSceneUndo();marks=marks.filter(m=>m.kind!=='translation')
  const id=++markId;marks.push({id,image:painted.layer,x:bounds.x,y:bounds.y,w:source.width,h:source.height,movable:false,kind:'translation'})
  translationScene.value={markId:id,rect:bounds,lines:painted.lines,language:result.language};translationVisible.value=true;redraw()
  translationPhase.value='';emit('toast',location.fallback?'已完成原位翻译（本地 OCR 定位）':'已完成原位翻译')
 }catch(error){if(!controller.signal.aborted&&!disposed){translationError.value=signal.aborted?'翻译等待超时，请重新翻译':error instanceof Error?error.message:'翻译失败，请重试';emit('toast',translationError.value)}}
 finally{if(translationController===controller){translationController=undefined;translationBusy.value=false;translationPhase.value=''}}
}
const resultPanelPosition=ref<{x:number;y:number;width:number;height:number}>(),resultPanelDragging=ref(false),resultPanelResizing=ref(false)
let resultPanelDrag:{pointerId:number;x:number;y:number;left:number;top:number}|undefined
let resultPanelResize:{pointerId:number;x:number;y:number;left:number;top:number;width:number;height:number;edge:string}|undefined
function beginResultDrag(e:PointerEvent){
 if(e.button!==0||resultPanelResizing.value||(e.target as Element).closest('button'))return
 const header=e.currentTarget as HTMLElement,bounds=header.closest('aside')!.getBoundingClientRect()
 resultPanelPosition.value={x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height}
 resultPanelDrag={pointerId:e.pointerId,x:e.clientX,y:e.clientY,left:bounds.x,top:bounds.y};resultPanelDragging.value=true
 header.setPointerCapture(e.pointerId);e.preventDefault()
}
function moveResultDrag(e:PointerEvent){
 const drag=resultPanelDrag,position=resultPanelPosition.value;if(!drag||!position||drag.pointerId!==e.pointerId)return
 resultPanelPosition.value={...position,x:Math.max(8,Math.min(viewport.value.w-position.width-8,drag.left+e.clientX-drag.x)),y:Math.max(8,Math.min(viewport.value.h-position.height-8,drag.top+e.clientY-drag.y))}
}
function endResultDrag(e:PointerEvent){if(resultPanelDrag?.pointerId!==e.pointerId)return;resultPanelDrag=undefined;resultPanelDragging.value=false;const header=e.currentTarget as HTMLElement;if(header.hasPointerCapture(e.pointerId))header.releasePointerCapture(e.pointerId)}
function beginResultResize(e:PointerEvent,edge:string){
 if(e.button!==0||resultPanelDragging.value||resultPanelResizing.value)return
 const handle=e.currentTarget as HTMLElement,bounds=handle.closest('aside')!.getBoundingClientRect()
 resultPanelPosition.value={x:bounds.x,y:bounds.y,width:bounds.width,height:bounds.height}
 resultPanelResize={pointerId:e.pointerId,x:e.clientX,y:e.clientY,left:bounds.x,top:bounds.y,width:bounds.width,height:bounds.height,edge};resultPanelResizing.value=true
 handle.setPointerCapture(e.pointerId);e.preventDefault()
}
function moveResultResize(e:PointerEvent){
 const start=resultPanelResize;if(!start||start.pointerId!==e.pointerId)return
 const dx=e.clientX-start.x,dy=e.clientY-start.y,minWidth=Math.min(280,viewport.value.w-16),minHeight=Math.min(220,viewport.value.h-16)
 let left=start.left,top=start.top,right=left+start.width,bottom=top+start.height
 if(start.edge.includes('w'))left=Math.max(8,Math.min(right-minWidth,left+dx))
 if(start.edge.includes('e'))right=Math.min(viewport.value.w-8,Math.max(left+minWidth,right+dx))
 if(start.edge.includes('n'))top=Math.max(8,Math.min(bottom-minHeight,top+dy))
 if(start.edge.includes('s'))bottom=Math.min(viewport.value.h-8,Math.max(top+minHeight,bottom+dy))
 resultPanelPosition.value={x:left,y:top,width:right-left,height:bottom-top}
}
function endResultResize(e:PointerEvent){if(resultPanelResize?.pointerId!==e.pointerId)return;resultPanelResize=undefined;resultPanelResizing.value=false;const handle=e.currentTarget as HTMLElement;if(handle.hasPointerCapture(e.pointerId))handle.releasePointerCapture(e.pointerId)}
const shortcuts=toolShortcuts
const arrowOptions=[{value:'outline',label:'\u7a7a\u5fc3'},{value:'solid',label:'\u5b9e\u5fc3'},{value:'double',label:'\u53cc\u5411'},{value:'line',label:'\u76f4\u7ebf'}]
const lineOptions=[{value:'solid',label:'\u5b9e\u7ebf'},{value:'dashed',label:'\u865a\u7ebf'},{value:'dotted',label:'\u70b9\u7ebf'}]
const languageOptions=[{value:'zh-CN',label:'\u7b80\u4f53\u4e2d\u6587'},{value:'zh-TW',label:'\u7e41\u4f53\u4e2d\u6587'},{value:'en',label:'English'}]
const actionLabels:Record<string,string>={ocr:'提取文字',translate:'翻译',chat:'AI对话',save:'保存'}
const colorValue=computed(()=>rgbMode.value?'RGB('+[1,3,5].map(i=>parseInt(pixelHex.value.slice(i,i+2),16)).join(', ')+')':pixelHex.value)
let processController:AbortController|undefined
const scrollBusy=ref(false),scrollHeight=ref(0),scrollError=ref('')
const scrollPreviewData=ref('')
let stitched:HTMLCanvasElement|undefined,scrollPrevious:ImageData|undefined,scrollPosition=0,scrollStart=0,scrollEnd=0
let scrollTimer:ReturnType<typeof setTimeout>|undefined,liveUnlisten:(()=>void)|undefined,scrollSampling:Promise<void>|undefined
const scrollLive=ref(false)
function scrollThumbnail(){if(!stitched)return;const c=document.createElement('canvas'),factor=Math.min(1,180/stitched.width,330/stitched.height);c.width=Math.max(1,Math.round(stitched.width*factor));c.height=Math.max(1,Math.round(stitched.height*factor));c.getContext('2d')!.drawImage(stitched,0,0,c.width,c.height);scrollPreviewData.value=c.toDataURL('image/png')}
async function scrollNext(){
 if(!selection.value||scrollBusy.value)return
 scrollBusy.value=true
 try{const data=await desktop.scrollFrame(selection.value),image=new Image();image.src=data;await image.decode();if(disposed||tool.value!=='scroll')return
  const frame=document.createElement('canvas');frame.width=selection.value.w;frame.height=selection.value.h;frame.getContext('2d')!.drawImage(image,0,0);const pixels=frame.getContext('2d')!.getImageData(0,0,frame.width,frame.height);if(!scrollLive.value)ctx().drawImage(frame,selection.value.x,selection.value.y)
  if(!stitched){stitched=frame;scrollPrevious=pixels;scrollEnd=frame.height;scrollHeight.value=frame.height;scrollThumbnail();return}
  const offset=scrollOffset(scrollPrevious!,pixels);if(offset===null){scrollError.value='滚动过快或选区含固定内容，当前帧尚未拼接；请慢慢回滚到上一位置。';return}if(!offset)return
  const position=scrollPosition+offset,start=Math.min(scrollStart,position),end=Math.max(scrollEnd,position+frame.height),height=end-start
  if(height>20000||frame.width*height>40_000_000){scrollError.value='已达到长图尺寸上限，请完成当前截图。';return}
  if(height!==stitched.height){const joined=document.createElement('canvas');joined.width=frame.width;joined.height=height;const g=joined.getContext('2d')!;g.drawImage(stitched,0,scrollStart-start);if(position<scrollStart)g.drawImage(frame,0,0,frame.width,scrollStart-position,0,0,frame.width,scrollStart-position);if(position+frame.height>scrollEnd){const extra=position+frame.height-scrollEnd;g.drawImage(frame,0,frame.height-extra,frame.width,extra,0,scrollEnd-start,frame.width,extra)}stitched=joined}
  scrollPosition=position;scrollStart=start;scrollEnd=end;scrollPrevious=pixels;scrollHeight.value=height;scrollError.value='';scrollThumbnail()
 }catch(error){scrollError.value=error instanceof Error?error.message:String(error)}finally{scrollBusy.value=false}
}
function liveButtons(){return Array.from(captureToolbar.value?.querySelectorAll('button')||[]).map(b=>{const r=b.getBoundingClientRect(),d=devicePixelRatio;return{x:Math.round(r.x*d),y:Math.round(r.y*d),width:Math.round(r.width*d),height:Math.round(r.height*d)}})}
function pollScroll(){if(disposed||!scrollLive.value)return;scrollSampling=scrollNext();scrollSampling.finally(()=>{scrollSampling=undefined;if(scrollLive.value&&!disposed)scrollTimer=setTimeout(pollScroll,40)})}
async function stopScroll(finalFrame=true){clearTimeout(scrollTimer);scrollLive.value=false;await scrollSampling;if(finalFrame&&!disposed)await scrollNext();liveUnlisten?.();liveUnlisten=undefined;await desktop.liveScroll(false)}
async function startScroll(){
 try{await nextTick();liveUnlisten=await desktop.listen<number>('desktop:scroll-action',async action=>{if(completing.value)return;if(action===2){requestCancel();return}if(action===0)await editLong();else await finish(action===1?'save':'copy')});await desktop.liveScroll(true,liveButtons(),liveScrollKeys());await scrollNext();if(disposed||tool.value!=='scroll'){await stopScroll(false);return}if(!stitched)throw new Error(scrollError.value||'无法开始滚动截图，请重新框选正文区域');const r=selection.value!;ctx().clearRect(r.x,r.y,r.w,r.h);scrollLive.value=true;pollScroll()}
 catch(error){await stopScroll(false).catch(()=>{});tool.value='select';emit('toast',error instanceof Error?error.message:String(error))}
}
function resetScroll(){stitched=undefined;scrollPrevious=undefined;scrollPosition=0;scrollStart=0;scrollEnd=0;scrollHeight.value=0;scrollError.value='';scrollPreviewData.value=''}
async function editLong(){if(!stitched||completing.value)return;completing.value=true;try{await stopScroll();emit('edit',{id:props.source.id+'-edit',name:'长图编辑',data:stitched.toDataURL('image/png'),width:stitched.width,height:stitched.height,scenario:'custom'})}finally{completing.value=false}}
function closeResult(){if(['ocr','translate'].includes(tool.value)){tool.value='select';showOptions.value=false}processController?.abort();processController=undefined;processing.value=false;resultAction.value=undefined;resultText.value='';resultError.value='';resultPanelPosition.value=undefined;resultPanelDrag=undefined;resultPanelDragging.value=false;resultPanelResize=undefined;resultPanelResizing.value=false}
async function copyText(text:string){try{if(native)await desktop.copyText(text);else await navigator.clipboard.writeText(text);emit('toast','已复制到剪贴板')}catch{emit('toast','复制失败，请重试')}}
async function processSelection(action:ProcessAction){
 
  if(action==='translate'){await startTranslation();return}
 cancelTranslation(); commitText();const c=stitched||output();if(!c||completing.value)return
 processController?.abort();tool.value=action;showOptions.value=false;selectedMark.value=undefined;pointer.value=undefined
 resultAction.value=action;resultText.value='';resultError.value='';processing.value=true;const controller=new AbortController();processController=controller
 try{await afterPaint();if(controller.signal.aborted||disposed)return;const data=await canvasPng(c);if(controller.signal.aborted||disposed)return;const asset:Asset={id:'process-'+Date.now(),name:'截图',data,width:c.width,height:c.height,scenario:'custom'},signal=AbortSignal.any([controller.signal,AbortSignal.timeout(240000)]);const result=await api.processCapture(asset,action,resultLanguage.value,signal);if(!controller.signal.aborted)resultText.value=result.text}

 catch(error){if(!controller.signal.aborted)resultError.value=error instanceof Error?error.message:'处理失败，请重试'}
 finally{if(processController===controller){processController=undefined;processing.value=false}}
}
const rectRounded=ref(false),rectFilled=ref(false),ellipseFilled=ref(false),arrowStyle=ref('outline'),lineStyle=ref('solid')
const shapeFilled=computed({get:()=>tool.value==='rect'?rectFilled.value:ellipseFilled.value,set:(v:boolean)=>{if(tool.value==='rect')rectFilled.value=v;else ellipseFilled.value=v}})
const mosaicPixels=ref(12),mosaicEffect=ref('pixel'),blurShape=ref('round'),blurOpacity=ref(50),blurRadius=ref(5)
let blurLayer:HTMLCanvasElement|undefined,lastInkTool='select'
function makeBlurLayer(radius:number){const layer=document.createElement('canvas');layer.width=props.source.width;layer.height=props.source.height;const g=layer.getContext('2d')!;g.filter=`blur(${radius/scale.value}px)`;g.drawImage(canvas.value!,0,0);return layer}
function shapePath(g:CanvasRenderingContext2D,x:number,y:number,w:number,h:number,shape:string){const left=Math.min(x,x+w),top=Math.min(y,y+h),width=Math.abs(w),height=Math.abs(h);g.beginPath();if(shape==='ellipse')g.ellipse(left+width/2,top+height/2,width/2,height/2,0,0,Math.PI*2);else if(shape==='round')g.roundRect(left,top,width,height,Math.min(12/scale.value,width/2,height/2));else g.rect(left,top,width,height)}
const captureToolbar=ref<HTMLElement>(),toolbarHeight=ref(56)
const heldToolbarStyle=ref<{left:string;top:string;width:string}>()
let toolbarObserver:ResizeObserver|undefined
watch(captureToolbar,element=>{toolbarObserver?.disconnect();if(!element)return;const measure=()=>{toolbarHeight.value=element.getBoundingClientRect().height;if(scrollLive.value)desktop.liveScroll(true,liveButtons(),liveScrollKeys()).catch(()=>{})};measure();toolbarObserver=new ResizeObserver(measure);toolbarObserver.observe(element)})
watch(shortcuts,()=>{if(scrollLive.value)desktop.liveScroll(true,liveButtons(),liveScrollKeys()).catch(()=>{})})
const mosaicShape=ref<'circle'|'square'>('circle'),mosaicSize=ref(32),mosaicMode=ref<'brush'|'area'>('brush'),mosaicArea=ref<Rect>()
let mosaicLayer:HTMLCanvasElement|undefined
function prepareMosaic(){
 if(mosaicEffect.value==='blur'){mosaicLayer=makeBlurLayer(mosaicPixels.value);return}
 const tile=Math.max(3,Math.round(mosaicPixels.value/scale.value)),sample=document.createElement('canvas');sample.width=Math.ceil(props.source.width/tile);sample.height=Math.ceil(props.source.height/tile)
 sample.getContext('2d')!.drawImage(canvas.value!,0,0,sample.width,sample.height)
 mosaicLayer=document.createElement('canvas');mosaicLayer.width=props.source.width;mosaicLayer.height=props.source.height;const g=mosaicLayer.getContext('2d')!;g.imageSmoothingEnabled=false;g.drawImage(sample,0,0,mosaicLayer.width,mosaicLayer.height)
}
function paintMosaic(p:{x:number;y:number}){
 if(!mosaicLayer||!selection.value)return;const radius=mosaicSize.value/scale.value/2,g=ctx();g.save();clip();g.beginPath();if(mosaicShape.value==='circle')g.arc(p.x,p.y,radius,0,Math.PI*2);else g.rect(p.x-radius,p.y-radius,radius*2,radius*2);g.clip()
 const x=Math.max(0,Math.floor(p.x-radius)),y=Math.max(0,Math.floor(p.y-radius)),w=Math.min(props.source.width-x,Math.ceil(radius*2+2)),h=Math.min(props.source.height-y,Math.ceil(radius*2+2));if(w>0&&h>0)g.drawImage(mosaicLayer,x,y,w,h,x,y,w,h);g.restore()
}
function strokeMosaic(p:{x:number;y:number}){const length=Math.hypot(p.x-previous.x,p.y-previous.y),steps=Math.max(1,Math.ceil(length/(mosaicSize.value/scale.value/5)));for(let n=1;n<=steps;n++)paintMosaic({x:previous.x+(p.x-previous.x)*n/steps,y:previous.y+(p.y-previous.y)*n/steps});previous=p}
const mosaicCursorStyle=computed(()=>pointer.value?{left:pointer.value.clientX-mosaicSize.value/2+'px',top:pointer.value.clientY-mosaicSize.value/2+'px',width:mosaicSize.value+'px',height:mosaicSize.value+'px'}:{})
const contentBrushSize=computed(()=>tool.value==='highlight'?highlightSize.value:repairSize.value)
const contentBrushShape=computed(()=>tool.value==='highlight'?highlightShape.value:repairShape.value)
const contentBrushColor=computed(()=>tool.value==='highlight'?highlightColor.value+'55':'transparent')
const contentBrushVisible=computed(()=>['highlight','heal'].includes(tool.value)&&pointerInsideSelection.value&&!repairBusy.value&&!props.closing&&!completing.value&&!resultAction.value&&!conversationOpen.value)
const contentBrushStyle=computed(()=>pointer.value?{left:pointer.value.clientX-contentBrushSize.value/2+'px',top:pointer.value.clientY-contentBrushSize.value/2+'px',width:contentBrushSize.value+'px',height:contentBrushSize.value+'px',background:contentBrushColor.value}:{} )
function highlightStroke(p:{x:number;y:number}){if(!selection.value||!inkLayer)return;const g=ctx();g.save();clip();paintBrush(g,previous,p,highlightSize.value/scale.value,highlightShape.value,highlightColor.value);g.restore();previous=p;redraw()}
const mosaicAreaStyle=computed(()=>{const r=mosaicArea.value;return r?{left:r.x*scale.value+imagePos.value.x+'px',top:r.y*scale.value+imagePos.value.y+'px',width:r.w*scale.value+'px',height:r.h*scale.value+'px'}:{}})
const textEditor=ref<HTMLTextAreaElement>(),textAnchor=ref<{x:number;y:number}>(),textSize=ref(24)
const textEditorStyle=computed(()=>{
 const p=textAnchor.value,r=selection.value;if(!p||!r)return {}
 const maxWidth=Math.max(1,(r.x+r.w-p.x)*scale.value),maxHeight=Math.max(1,(r.y+r.h-p.y)*scale.value)
 const g=ctx();g.save();g.font=`${textSize.value}px "Microsoft YaHei", Arial`;const lines=annotation.value.split('\n');const width=Math.max(textSize.value*4+4,...lines.map(line=>g.measureText(line).width+8));g.restore()
 return {left:p.x*scale.value+imagePos.value.x+'px',top:p.y*scale.value+imagePos.value.y+'px',width:Math.min(maxWidth,width)+'px',height:Math.min(maxHeight,lines.length*textSize.value*1.3+4)+'px',fontSize:textSize.value+'px',color:color.value}
})
async function editText(e:MouseEvent){if(tool.value!=='objects'||conversationOpen.value||resultAction.value)return;const mark=hitMark(point(e as unknown as PointerEvent));if(!mark?.textInfo)return;selectedMark.value=mark.id;editingTextMark=mark.id;textAnchor.value={x:mark.x,y:mark.y};annotation.value=mark.textInfo.value;textSize.value=mark.textInfo.size;color.value=mark.textInfo.color;tool.value='text';await nextTick();textEditor.value?.focus()}
async function beginText(p:{x:number;y:number}){textAnchor.value={x:Math.round(p.x),y:Math.round(p.y)};annotation.value='';drawing.value=false;await nextTick();textEditor.value?.focus()}
function commitText(){
 const p=textAnchor.value;if(!p)return;textAnchor.value=undefined
 const textMeta={value:annotation.value,size:textSize.value,color:color.value,anchor:{...p}}
 if(annotation.value.trim()&&selection.value){beginInk();if(editingTextMark!==undefined)marks=marks.filter(m=>m.id!==editingTextMark);const g=ctx();g.save();clip();g.fillStyle=color.value;const size=textSize.value/scale.value,lineHeight=size*1.3;g.font=`${size}px "Microsoft YaHei", Arial`;g.textBaseline='alphabetic';const metrics=g.measureText('Mg'),ascent=metrics.fontBoundingBoxAscent||size*.9,descent=metrics.fontBoundingBoxDescent||size*.2;annotation.value.split('\n').forEach((line,index)=>g.fillText(line,p.x,p.y+(lineHeight-ascent-descent)/2+ascent+index*lineHeight));g.restore();remember();const mark=marks.at(-1);if(mark?.kind==='text')mark.textInfo=textMeta}
 editingTextMark=undefined;annotation.value=''
}
function cancelText(){editingTextMark=undefined;textAnchor.value=undefined;annotation.value='';root.value?.focus()}
function textKey(e:KeyboardEvent){if(e.isComposing||e.keyCode===229)return;if(e.key==='Escape'){e.preventDefault();cancelText()}else if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();commitText();if(e.ctrlKey||e.metaKey)finish('copy');else root.value?.focus()}else if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'){e.preventDefault();finish('save')}}
const loupe=ref<HTMLCanvasElement>(),pointer=ref<{x:number;y:number;clientX:number;clientY:number}>(),pixelHex=ref('#000000')
const loupeVisible=computed(()=>ready.value&&pointer.value&&!props.closing&&!completing.value&&(tool.value==='eyedropper'||tool.value==='select'&&(!selection.value||drawing.value&&mode==='new')))
const loupeStyle=computed(()=>{const p=pointer.value;if(!p)return {};const width=199,height=247,gap=24;let x=p.clientX+gap,y=p.clientY+gap;if(x+width>viewport.value.w-12)x=p.clientX-width-gap;if(y+height>viewport.value.h-12)y=p.clientY-height-gap;return {left:Math.max(12,Math.min(x,viewport.value.w-width-12))+'px',top:Math.max(12,Math.min(y,viewport.value.h-height-12))+'px'}})
let loupeFrame=0
function trackPointer(e:PointerEvent){
 if(!ready.value||props.closing||(e.target as Element).closest('.capture-toolbar,.capture-tool-options,.capture-function-menu,.capture-top-controls,.capture-ai-menu,.capture-process-result')){pointer.value=undefined;return}
 const p=point(e);pointer.value={x:Math.min(props.source.width-1,Math.floor(p.x)),y:Math.min(props.source.height-1,Math.floor(p.y)),clientX:e.clientX,clientY:e.clientY}
 if(!loupeFrame)loupeFrame=requestAnimationFrame(paintLoupe)
}
function paintLoupe(){
 loupeFrame=0;const p=pointer.value,g=loupe.value?.getContext('2d');if(!p||!g||!canvas.value||!loupeVisible.value)return
 const rgb=ctx().getImageData(p.x,p.y,1,1).data;pixelHex.value='#'+Array.from(rgb.slice(0,3),v=>v.toString(16).padStart(2,'0')).join('').toUpperCase()
 // A wider 57x57 sample gives a gentler 3x magnification.
 g.imageSmoothingEnabled=false;g.fillStyle='#eee9fb';g.fillRect(0,0,171,171)
 g.drawImage(canvas.value,p.x-28,p.y-28,57,57,0,0,171,171)
}
const physicalDesktop=computed(()=>native&&props.source.data.startsWith('http://snapmind-frame.localhost/'))
const floatingOffset=ref({x:0,y:0}),floatingZoom=ref(1)
let imageDrag:{x:number;y:number;offset:{x:number;y:number}}|undefined,stopPreviewRegions=()=>{}
const fitScale=computed(()=>Math.max(.001,Math.min(1,(viewport.value.w-48)/props.source.width,(viewport.value.h-150)/props.source.height)))
const scale=computed(()=>props.floatingPreview?fitScale.value*floatingZoom.value:props.initialSelection?Math.min((viewport.value.w-48)/props.source.width,(viewport.value.h-190)/props.source.height):physicalDesktop.value?1/window.devicePixelRatio:Math.min(viewport.value.w/props.source.width,viewport.value.h/props.source.height))
const imagePos=computed(()=>{
 if(props.floatingPreview){const w=props.source.width*scale.value,h=props.source.height*scale.value;return {x:Math.max(12,Math.min(viewport.value.w-w-12,(viewport.value.w-w)/2+floatingOffset.value.x)),y:Math.max(36,Math.min(viewport.value.h-h-85,(viewport.value.h-h-85)/2+floatingOffset.value.y))}}
 return props.initialSelection?{x:(viewport.value.w-props.source.width*scale.value)/2,y:30}:physicalDesktop.value?{x:0,y:0}:{x:(viewport.value.w-props.source.width*scale.value)/2,y:(viewport.value.h-props.source.height*scale.value)/2}
})
function zoomFloating(e:WheelEvent){if(!props.floatingPreview||!e.deltaY||drawing.value||processing.value||textAnchor.value||(e.target as Element).closest('.capture-toolbar,.capture-process-result'))return;if(!(e.target as Element).closest('.capture-screen,.capture-selection')&&!e.ctrlKey)return;e.preventDefault();floatingZoom.value=Math.max(.2,Math.min(Math.min((viewport.value.w-24)/props.source.width,(viewport.value.h-125)/props.source.height)/fitScale.value,floatingZoom.value*(e.deltaY<0?1.12:1/1.12)))}
const display=computed(()=>{const r=selection.value;return r?{x:r.x*scale.value+imagePos.value.x,y:r.y*scale.value+imagePos.value.y,w:r.w*scale.value,h:r.h*scale.value}:undefined})
const pointerInsideSelection=computed(()=>{const p=pointer.value,d=display.value;return !!(p&&d&&p.clientX>=d.x&&p.clientX<=d.x+d.w&&p.clientY>=d.y&&p.clientY<=d.y+d.h)})
const captureCursor=computed(()=>{
 if(resultAction.value||conversationOpen.value||repairBusy.value||translationBusy.value||['translate'].includes(tool.value))return 'default'
 if(!selection.value)return 'crosshair'
 if(tool.value==='select')return drawing.value&&['move','image-move'].includes(mode)?'grabbing':pointerInsideSelection.value?'grab':'default'
 if(tool.value==='objects')return drawing.value&&mode==='object'?'grabbing':pointerInsideSelection.value&&hoverMark.value!==undefined?'grab':'default'
 if(tool.value==='eraser')return pointerInsideSelection.value&&hoverMark.value!==undefined?'pointer':'default'
 if(!pointerInsideSelection.value||['save','scroll'].includes(tool.value))return 'default'
 return tool.value==='mosaic'&&mosaicMode.value==='brush'||['highlight','heal'].includes(tool.value)?'none':'crosshair'
})
const resultPanelStyle=computed(()=>{
 const d=display.value,{w:vw,h:vh}=viewport.value,gap=16,margin=12;let width=Math.min(380,vw-margin*2),height=Math.min(420,vh-margin*2),left=vw-width-margin,top=margin
 if(resultPanelPosition.value){const p=resultPanelPosition.value;width=Math.min(p.width,vw-16);height=Math.min(p.height,vh-16);return {left:Math.max(8,Math.min(p.x,vw-width-8))+'px',top:Math.max(8,Math.min(p.y,vh-height-8))+'px',width:width+'px',height:height+'px'}}
 if(conversationOpen.value){
  width=Math.min(440,vw-margin*2);height=Math.min(760,vh-margin*2);top=(vh-height)/2
  if(d){const right=vw-(d.x+d.w)-gap-margin,roomLeft=d.x-gap-margin,useRight=right>=roomLeft,room=useRight?right:roomLeft
   if(room>=280){width=Math.min(width,room);left=useRight?d.x+d.w+gap:d.x-gap-width}
   else left=useRight?vw-width-margin:margin
  }else left=vw-width-margin
  return {left:left+'px',top:top+'px',width:width+'px',height:height+'px'}
 }
 if(d){const right=vw-(d.x+d.w)-gap-margin,roomLeft=d.x-gap-margin
  if(right>=280){width=Math.min(width,right);left=d.x+d.w+gap;top=Math.max(margin,Math.min(d.y,vh-height-margin))}
  else if(roomLeft>=280){width=Math.min(width,roomLeft);left=d.x-gap-width;top=Math.max(margin,Math.min(d.y,vh-height-margin))}
  else{left=Math.max(margin,Math.min(d.x,vw-width-margin));const above=d.y-gap-margin,below=vh-(d.y+d.h)-gap-margin
   if(above>=220){height=Math.min(height,above);top=d.y-gap-height}else if(below>=220){height=Math.min(height,below);top=d.y+d.h+gap}else top=Math.max(margin,Math.min(d.y,vh-height-margin))}
 }
 // Keep the result clear of the persistent toolbar whenever the viewport has room.
 const bar=captureToolbar.value?.getBoundingClientRect()
 if(bar&&left<bar.right&&left+width>bar.left&&top<bar.bottom&&top+height>bar.top){if(bar.top-top-gap>=200)height=Math.min(height,bar.top-top-gap);else if(vh-bar.bottom-gap-margin>=200){top=bar.bottom+gap;height=Math.min(height,vh-top-margin)}else if(bar.top-gap-margin>=200){top=margin;height=Math.min(height,bar.top-gap-margin)}}
 return {left:left+'px',top:top+'px',width:width+'px',height:height+'px'}
})
const scrollPreviewStyle=computed(()=>{const d=display.value;if(!d)return {};const width=180,left=d.x+d.w+20+width<viewport.value.w?d.x+d.w+20:d.x-width-20>=12?d.x-width-20:viewport.value.w-width-20;return {left:left+'px',top:Math.max(60,Math.min(d.y,viewport.value.h-420))+'px'}})
const mask=computed(()=>{const d=display.value;return `M0 0H${viewport.value.w}V${viewport.value.h}H0Z`+(d?` M${d.x} ${d.y}V${d.y+d.h}H${d.x+d.w}V${d.y}Z`:'')})
const toolbarStyle=computed(()=>{if(heldToolbarStyle.value)return heldToolbarStyle.value;const d=display.value;if(!d)return {};const width=Math.min(tool.value==='scroll'?240:['translate'].includes(tool.value)?1530:1330,viewport.value.w-24),height=tool.value==='scroll'?Math.max(56,toolbarHeight.value):showOptions.value?Math.max(120,toolbarHeight.value):56,below=d.y+d.h+14;const top=below+height<=viewport.value.h-12?below:d.y-height-14>=12?d.y-height-14:Math.max(12,viewport.value.h-height-12);return {left:Math.max(12,Math.min(tool.value==='scroll'?d.x+(d.w-width)/2:d.x,viewport.value.w-width-12))+'px',top:top+'px',width:width+'px'}})
const handles=['nw','n','ne','e','se','s','sw','w']
const annotationTools=[{id:'objects',label:'移动标注'},{id:'rect',label:'矩形'},{id:'ellipse',label:'圆形'},{id:'arrow',label:'箭头'},{id:'pen',label:'画笔'},{id:'mosaic',label:'马赛克'},{id:'text',label:'文字'},{id:'blur',label:'模糊遮罩'},{id:'number',label:'序号'},{id:'eyedropper',label:'取色'},{id:'highlight',label:'荧光笔'},{id:'eraser',label:'橡皮擦'},{id:'heal',label:'涂抹消除'},{id:'lift',label:'无痕提取'}]
let start={x:0,y:0},previous={x:0,y:0},originalRect:Rect|undefined,mode='',before:ImageData|undefined
function point(e:PointerEvent){return {x:Math.max(0,Math.min(props.source.width,(e.clientX-imagePos.value.x)/scale.value)),y:Math.max(0,Math.min(props.source.height,(e.clientY-imagePos.value.y)/scale.value))}}
function ctx(){return (inkLayer||canvas.value!).getContext('2d')!}
function remember(sequence=number.value){if(finishInk())pushSceneUndo(markBefore,sequence)}
function inside(p:{x:number;y:number},r:Rect){return p.x>=r.x&&p.x<=r.x+r.w&&p.y>=r.y&&p.y<=r.y+r.h}
function down(e:PointerEvent,handle=''){
 trackPointer(e)
 if(!ready.value||completing.value||props.closing||openingPanel.value||e.button!==0||scrollHeight.value||resultAction.value||conversationOpen.value||repairBusy.value||translationBusy.value)return
 stroke.value=Math.max(1,Math.min(30,Number(stroke.value)||3))
 if((e.target as HTMLElement).closest('.capture-toolbar,.capture-tool-options,.capture-top-controls,.capture-ai-menu,.capture-text-editor,.capture-process-result'))return
 commitText()
 selectedMark.value=undefined
 showAi.value=false;start=point(e);previous=start;originalRect=selection.value?{...selection.value}:undefined
 if(props.floatingPreview&&!handle&&selection.value&&inside(start,selection.value)&&['select','objects'].includes(tool.value)&&!hitMark(start)){
  if(!(e.target as Element).closest('.capture-screen,.capture-selection'))return
  mode='image-move';imageDrag={x:e.clientX,y:e.clientY,offset:{...floatingOffset.value}};root.value!.setPointerCapture(e.pointerId);drawing.value=true;return
 }
 if(props.floatingPreview&&!handle&&!(e.target as Element).closest('.capture-screen,.capture-selection'))return
 if(tool.value==='eyedropper'){const p=ctx().getImageData(Math.min(props.source.width-1,Math.floor(start.x)),Math.min(props.source.height-1,Math.floor(start.y)),1,1).data;color.value='#'+Array.from(p.slice(0,3),v=>v.toString(16).padStart(2,'0')).join('');tool.value=lastInkTool;showOptions.value=tool.value!=='select';return}
 if(tool.value==='eraser'&&!handle){selectedMark.value=hitMark(start)?.id;root.value?.focus();return}
 if(tool.value==='objects'&&!handle){const mark=hitMark(start);selectedMark.value=mark?.id;if(!mark)return;dragMark={...mark};const anchor=mark.ai?aiAnchor(mark.ai):start;dragAiTarget=!!(mark.ai?.kind==='callout'&&Math.hypot(start.x-anchor.x,start.y-anchor.y)<=7/scale.value);markBefore=sceneSnapshot();mode='object';root.value!.setPointerCapture(e.pointerId);drawing.value=true;return}
 mode=handle?handle:tool.value==='select'&&selection.value&&inside(start,selection.value)?'move':tool.value==='select'||!selection.value?'new':'draw'
 if(mode==='draw'&&['ocr','translate','explain','detect','scroll'].includes(tool.value))return
 if(mode==='draw'&&tool.value==='text'&&selection.value){e.preventDefault();if(inside(start,selection.value))beginText(start);return}
 if(selection.value&&mode!=='new'){const bounds=captureToolbar.value?.getBoundingClientRect();if(bounds)heldToolbarStyle.value={left:bounds.left+'px',top:bounds.top+'px',width:bounds.width+'px'}}
 root.value!.setPointerCapture(e.pointerId);drawing.value=true
 if(mode==='new'){tool.value='select';selection.value={x:start.x,y:start.y,w:0,h:0};return}
 if(mode!=='draw')return
 beginInk()
 if(tool.value==='heal'||tool.value==='lift'){prepareRepair();return}
 if(tool.value==='highlight'){highlightStroke(start);return}
 if(tool.value==='mosaic'){prepareMosaic();if(mosaicMode.value==='brush'){paintMosaic(start);redraw()}else mosaicArea.value={x:start.x,y:start.y,w:0,h:0};return}
 if(tool.value==='blur'){blurLayer=makeBlurLayer(blurRadius.value);return}
 if(tool.value==='number'){
  const g=ctx();g.save();clip();g.fillStyle=color.value;const radius=12/scale.value;g.beginPath();g.arc(start.x,start.y,radius,0,Math.PI*2);g.fill();const rgb=[1,3,5].map(i=>parseInt(color.value.slice(i,i+2),16));g.fillStyle=(rgb[0]!*299+rgb[1]!*587+rgb[2]!*114)/1000>180?'#242128':'#fff';g.font=`${15/scale.value}px Arial`;g.textAlign='center';g.textBaseline='middle';g.fillText(String(number.value++),start.x,start.y);g.restore();remember(number.value-1);drawing.value=false;heldToolbarStyle.value=undefined
 }
}
function clip(){const r=selection.value!;const g=ctx();g.beginPath();g.rect(r.x,r.y,r.w,r.h);g.clip()}
function move(e:PointerEvent){trackPointer(e);if(mode==='image-move'&&drawing.value&&imageDrag){floatingOffset.value={x:imageDrag.offset.x+e.clientX-imageDrag.x,y:imageDrag.offset.y+e.clientY-imageDrag.y};return}if(['objects','eraser'].includes(tool.value)&&!drawing.value)hoverMark.value=hitMark(point(e))?.id;if(!drawing.value)return;const p=point(e);let dx=p.x-start.x,dy=p.y-start.y;if(e.shiftKey&&mode==='draw'){if(['rect','ellipse','blur','lift'].includes(tool.value)){const length=Math.max(Math.abs(dx),Math.abs(dy));dx=length*(dx<0?-1:1);dy=length*(dy<0?-1:1);p.x=start.x+dx;p.y=start.y+dy}else if(tool.value==='arrow'){const angle=Math.round(Math.atan2(dy,dx)/(Math.PI/4))*Math.PI/4,length=Math.hypot(dx,dy);dx=length*Math.cos(angle);dy=length*Math.sin(angle);p.x=start.x+dx;p.y=start.y+dy}}
 if(mode==='object'&&dragMark?.ai?.kind==='callout'&&selection.value){const r=selection.value,box=dragMark.ai.bbox,anchor=aiAnchor(dragMark.ai),tx=Math.max(r.x-Math.min(box[0],anchor.x),Math.min(r.x+r.w-Math.max(box[2],anchor.x),dx)),ty=Math.max(r.y-Math.min(box[1],anchor.y),Math.min(r.y+r.h-Math.max(box[3],anchor.y),dy)),spec=dragAiTarget?{...dragMark.ai,bbox:box.map((v,i)=>v+(i%2===0?tx:ty)) as [number,number,number,number],anchor:dragMark.ai.anchor?{x:anchor.x+tx,y:anchor.y+ty}:undefined}:moveBubble(dragMark.ai,dx,dy,r),index=marks.findIndex(m=>m.id===dragMark!.id),layer=paintAi(spec,r,scale.value);marks[index]={...marks[index]!,...layer};redraw();return}
 if(mode==='object'&&dragMark&&selection.value){const r=selection.value,mark=marks.find(m=>m.id===dragMark!.id)!,box=dragMark.ai?.bbox,left=box?Math.min(box[0],dragMark.x):dragMark.x,top=box?Math.min(box[1],dragMark.y):dragMark.y,right=box?Math.max(box[2],dragMark.x+dragMark.w):dragMark.x+dragMark.w,bottom=box?Math.max(box[3],dragMark.y+dragMark.h):dragMark.y+dragMark.h;mark.x=dragMark.x+Math.round(Math.max(r.x-left,Math.min(r.x+r.w-right,dx)));mark.y=dragMark.y+Math.round(Math.max(r.y-top,Math.min(r.y+r.h-bottom,dy)));if(dragMark.ai)mark.ai={...dragMark.ai,bbox:dragMark.ai.bbox.map((v,i)=>v+(i%2===0?mark.x-dragMark!.x:mark.y-dragMark!.y)) as [number,number,number,number]};redraw();return}
 if(mode==='new'){selection.value={x:Math.min(p.x,start.x),y:Math.min(p.y,start.y),w:Math.abs(dx),h:Math.abs(dy)};return}
 if(mode==='move'&&originalRect){selection.value={...originalRect,x:Math.max(0,Math.min(props.source.width-originalRect.w,originalRect.x+dx)),y:Math.max(0,Math.min(props.source.height-originalRect.h,originalRect.y+dy))};return}
 if(mode!=='draw'&&originalRect){let {x,y,w,h}=originalRect;let right=x+w,bottom=y+h;if(mode.includes('w'))x=p.x;if(mode.includes('e'))right=p.x;if(mode.includes('n'))y=p.y;if(mode.includes('s'))bottom=p.y;selection.value={x:Math.min(x,right),y:Math.min(y,bottom),w:Math.abs(right-x),h:Math.abs(bottom-y)};return}
 if(!before||!selection.value)return
 if(tool.value==='heal'){repairStroke(p);return}
 if(tool.value==='highlight'){highlightStroke(p);return}
 if(tool.value==='lift'){const g=repairMask!.getContext('2d')!;g.fillStyle='#000';g.fillRect(0,0,repairMask!.width,repairMask!.height);g.fillStyle='#fff';g.fillRect(Math.min(start.x,p.x),Math.min(start.y,p.y),Math.abs(dx),Math.abs(dy));const preview=inkLayer!.getContext('2d')!;preview.clearRect(0,0,inkLayer!.width,inkLayer!.height);preview.fillStyle='#af68ff';preview.fillRect(Math.min(start.x,p.x),Math.min(start.y,p.y),Math.abs(dx),Math.abs(dy));redraw();return}
 if(tool.value==='mosaic'){
  if(mosaicMode.value==='brush')strokeMosaic(p)
  else{ctx().putImageData(before,0,0);const r={x:Math.min(start.x,p.x),y:Math.min(start.y,p.y),w:Math.abs(dx),h:Math.abs(dy)};mosaicArea.value=r;if(mosaicLayer&&r.w>0&&r.h>0){const g=ctx();g.save();clip();g.drawImage(mosaicLayer,r.x,r.y,r.w,r.h,r.x,r.y,r.w,r.h);g.restore()}}
  redraw();return
 }
 const g=ctx();if(!['pen','highlight'].includes(tool.value))g.putImageData(before,0,0);g.save();clip();g.strokeStyle=color.value;g.fillStyle=color.value;g.lineWidth=stroke.value/scale.value;g.lineCap='round';g.lineJoin='round'
 if(tool.value==='rect'||tool.value==='ellipse'){shapePath(g,start.x,start.y,dx,dy,tool.value==='ellipse'?'ellipse':rectRounded.value?'round':'rect');if(shapeFilled.value)g.fill();else g.stroke()}
 if(tool.value==='blur'&&blurLayer){shapePath(g,start.x,start.y,dx,dy,blurShape.value);g.clip();g.globalAlpha=blurOpacity.value/100;g.drawImage(blurLayer,0,0)}
 if(tool.value==='pen'){g.beginPath();g.moveTo(previous.x,previous.y);g.lineTo(p.x,p.y);g.stroke();previous=p}
 if(tool.value==='arrow'){const angle=Math.atan2(dy,dx),len=Math.max(12,stroke.value*4)/scale.value;g.setLineDash(lineStyle.value==='dashed'?[g.lineWidth*4,g.lineWidth*3]:lineStyle.value==='dotted'?[g.lineWidth,g.lineWidth*2]:[]);g.beginPath();g.moveTo(start.x,start.y);g.lineTo(p.x,p.y);g.stroke();g.setLineDash([]);const head=(x:number,y:number,a:number)=>{g.beginPath();g.moveTo(x-len*Math.cos(a-.45),y-len*Math.sin(a-.45));g.lineTo(x,y);g.lineTo(x-len*Math.cos(a+.45),y-len*Math.sin(a+.45));if(arrowStyle.value==='solid'){g.closePath();g.fill()}else g.stroke()};if(arrowStyle.value!=='line')head(p.x,p.y,angle);if(arrowStyle.value==='double')head(start.x,start.y,angle+Math.PI)}

 g.restore();redraw()
}
function up(){heldToolbarStyle.value=undefined;if(!drawing.value)return;drawing.value=false;if(mode==='image-move'){imageDrag=undefined;mode='';return}if(mode==='object'&&dragMark){const mark=marks.find(m=>m.id===dragMark!.id);if(mark&&(mark.x!==dragMark.x||mark.y!==dragMark.y||mark.ai?.bubble?.x!==dragMark.ai?.bubble?.x||mark.ai?.bubble?.y!==dragMark.ai?.bubble?.y||mark.ai?.bbox[0]!==dragMark.ai?.bbox[0]||mark.ai?.bbox[1]!==dragMark.ai?.bbox[1]))pushSceneUndo(markBefore);dragMark=undefined;return}if(mode==='draw'&&['heal','lift'].includes(tool.value)){completeRepair(tool.value==='lift');return}if(mode==='draw')remember();mosaicArea.value=undefined;mosaicLayer=undefined;blurLayer=undefined;if(selection.value&&(selection.value.w<4||selection.value.h<4)){selection.value=undefined;return}if(selection.value){const r=selection.value,x=Math.round(r.x),y=Math.round(r.y);selection.value={x,y,w:Math.min(props.source.width,Math.round(r.x+r.w))-x,h:Math.min(props.source.height,Math.round(r.y+r.h))-y}}}
function selectTool(id:string){
 if(openingPanel.value){const same=id===(openingPanel.value==='chat'?'chat':'voiceCall');cancelOpening();if(same)return}
 if(repairBusy.value)return
 if(id==='voiceCall'){if(voiceOpen.value)closeVoice();else openVoice();return}
 if(id==='chat'){if(conversationOpen.value)closeConversation();else openConversation();return}
 closeConversation()
  if(id==='redo'){redo();return}
 if(id==='clear'){clearMarks();return}

 
   if(id!==tool.value)cancelTranslation()
 if(tool.value===id){cancelTranslation();if(resultAction.value)closeResult();commitText();tool.value='select';showOptions.value=false;showAi.value=false;selectedMark.value=undefined;hoverMark.value=undefined;pointer.value=undefined;window.getSelection()?.removeAllRanges();return}
 if(['ocr','translate'].includes(id)){processSelection(id as ProcessAction);return}
 if(resultAction.value)closeResult();commitText();selectedMark.value=undefined;hoverMark.value=undefined
 if(id==='scroll'){if(!native){emit('toast','滚动截图请在桌面端使用');return}resetScroll();tool.value='scroll';showOptions.value=false;pointer.value=undefined;startScroll();return}
 if(id==='eyedropper')lastInkTool=['select','objects','eyedropper','blur','mosaic'].includes(tool.value)?'select':tool.value
 tool.value=id;showOptions.value=!['select','eyedropper','objects'].includes(tool.value);showAi.value=false
}
function undo(){if(drawing.value||repairBusy.value)return;cancelTranslation();const previous=undoStack.value.pop();if(previous){redoStack.value.push({marks:sceneSnapshot(),number:number.value,translation:translationScene.value});inkLayer=undefined;marks=previous.marks.map(mark=>({...mark}));number.value=previous.number;translationScene.value=previous.translation;translationVisible.value=true;selectedMark.value=undefined;redraw()}}
function output(includeTranslation=true){if(!selection.value)return;const r=selection.value,c=document.createElement('canvas');c.width=r.w;c.height=r.h;const g=c.getContext('2d')!;if(includeTranslation)g.drawImage(canvas.value!,r.x,r.y,r.w,r.h,0,0,r.w,r.h);else{g.translate(-r.x,-r.y);if(baseImage)g.drawImage(baseImage,0,0);for(const mark of marks)if(mark.kind!=='translation')paintMark(g,mark)}return c}
async function finish(action:CaptureResult['action']){
 closeVoice();closeConversation();repairController?.abort();
  cancelTranslation();processController?.abort()
 commitText()
 if(completing.value||props.closing)return;completing.value=true;let copied=false
 try {
  if(tool.value==='scroll')await stopScroll();const c=stitched||output();if(!c)return
  if(!native){try{const blob=await new Promise<Blob|null>(r=>c.toBlob(r,'image/png'));if(blob){await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);copied=true}}catch{emit('toast','截图已保留；浏览器限制了复制，可在相册中保存。')}}
  const data=await canvasPng(c);if(disposed||props.closing)return
  if(action==='save'&&!native){const a=document.createElement('a');a.href=data;a.download='SnapMind-'+new Date().toISOString().replace(/[:.]/g,'-')+'.png';a.click()}
  emit('finish',{data,width:c.width,height:c.height,action,copied})
 }finally{completing.value=false}
}
function resize(){viewport.value={w:window.innerWidth,h:window.innerHeight}}
function key(e:KeyboardEvent){if((e.target as HTMLElement)?.closest('.tool-shortcut-picker,.tool-shortcut-popup,.image-chat-lightbox,.voice-spirit'))return;const dropdown=(e.target as HTMLElement)?.closest('.capture-dropdown');if(dropdown&&(e.key!=='Escape'||dropdown.matches('.is-open,.capture-dropdown-menu')))return;if(e.isComposing||e.keyCode===229||(e.target as HTMLElement)?.closest('input,textarea,select,[contenteditable="true"]'))return;
 if(openingPanel.value&&e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();cancelOpening();return}
 if(voiceOpen.value&&e.key==='Escape'){e.preventDefault();e.stopImmediatePropagation();closeVoice();return}
 if(conversationOpen.value){if(e.key==='Escape'||shortcutTool(e)==='chat'){e.preventDefault();e.stopImmediatePropagation();if(!e.repeat)closeConversation()}return}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='c'){const chosen=window.getSelection(),layer=translationTextLayer.value;if(chosen&&!chosen.isCollapsed&&chosen.anchorNode&&layer?.contains(chosen.anchorNode)){e.preventDefault();e.stopImmediatePropagation();const range=chosen.getRangeAt(0),all=range.startContainer===layer&&range.startOffset===0&&range.endContainer===layer&&range.endOffset===layer.childNodes.length;copyText(all?allTranslatedText.value:chosen.toString());return}}
 if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='a'&&tool.value==='translate'&&translationTextLayer.value){e.preventDefault();e.stopImmediatePropagation();const range=document.createRange();range.selectNodeContents(translationTextLayer.value);const chosen=window.getSelection();chosen?.removeAllRanges();chosen?.addRange(range);return}
 if(e.key==='Escape'&&tool.value==='translate'){e.preventDefault();e.stopImmediatePropagation();cancelTranslation();tool.value='select';window.getSelection()?.removeAllRanges();return}
 if(e.key==='Escape'&&resultAction.value){e.preventDefault();e.stopImmediatePropagation();closeResult();return}
 if(tool.value==='eyedropper'&&e.key==='Shift'){e.preventDefault();rgbMode.value=!rgbMode.value;return}
 if(tool.value==='eyedropper'&&!e.ctrlKey&&!e.metaKey&&!e.altKey&&!e.shiftKey&&e.key.toLowerCase()==='q'){e.preventDefault();copyText(colorValue.value);return}
 if(e.key==='Escape'&&['objects','eraser'].includes(tool.value)&&selectedMark.value!==undefined){e.preventDefault();e.stopImmediatePropagation();selectedMark.value=undefined;return}
 const action=shortcutTool(e)
 if(action==='cancel'&&props.floatingPreview&&!completing.value&&!props.closing){e.preventDefault();e.stopImmediatePropagation();if(!e.repeat)requestCancel();return}
 if(action&&!drawing.value&&!repairBusy.value&&!completing.value&&!props.closing&&(!scrollBusy.value||action==='cancel')){
  const button=root.value?.querySelector<HTMLButtonElement>(`button[data-capture-tool="${action}"]`)
  if(button&&!button.disabled){e.preventDefault();e.stopImmediatePropagation();if(!e.repeat)button.click();return}
 }
 if(scrollBusy.value||resultAction.value)return
 if(!drawing.value&&!repairBusy.value&&['objects','eraser'].includes(tool.value)&&selectedMark.value!==undefined&&e.key==='Backspace'){e.preventDefault();pushSceneUndo();marks=marks.filter(m=>m.id!==selectedMark.value);selectedMark.value=undefined;redraw();return}
 const r=selection.value;if(!['scroll','objects','detect'].includes(tool.value)&&r&&['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(e.key)){e.preventDefault();const n=e.shiftKey?10:1;selection.value={...r,x:Math.max(0,Math.min(props.source.width-r.w,r.x+(e.key==='ArrowLeft'?-n:e.key==='ArrowRight'?n:0))),y:Math.max(0,Math.min(props.source.height-r.h,r.y+(e.key==='ArrowUp'?-n:e.key==='ArrowDown'?n:0)))}}
}
let disposed=false
watch(selection,r=>{if(voiceOpen.value&&conversationBounds&&(!r||r.x!==conversationBounds.x||r.y!==conversationBounds.y||r.w!==conversationBounds.w||r.h!==conversationBounds.h))closeVoice()})
onMounted(async()=>{window.addEventListener('resize',resize);document.addEventListener('keydown',key,true);await nextTick();const img=new Image();if(/^https?:/.test(props.source.data))img.crossOrigin='anonymous';img.src=props.source.data;try{await img.decode();if(disposed||!canvas.value)return;canvas.value.width=props.source.width;canvas.value.height=props.source.height;ctx().drawImage(img,0,0);baseImage=document.createElement('canvas');baseImage.width=props.source.width;baseImage.height=props.source.height;baseImage.getContext('2d')!.drawImage(img,0,0);if(props.initialSelection||props.floatingPreview)selection.value={x:0,y:0,w:props.source.width,h:props.source.height};ready.value=true;await nextTick();if(disposed)return;performance.mark('snapmind-capture-ready');if(props.floatingPreview)stopPreviewRegions=observePreviewRegions(props.source.id);emit('ready');root.value?.focus()}catch{if(!disposed)emit('toast','截图画面加载失败，请重新截图')}})
onBeforeUnmount(()=>{disposed=true;stopPreviewRegions();closeVoice();closeConversation();repairController?.abort();cancelTranslation();clearTimeout(scrollTimer);scrollLive.value=false;liveUnlisten?.();if(tool.value==='scroll')desktop.liveScroll(false).catch(()=>{});processController?.abort();toolbarObserver?.disconnect();cancelAnimationFrame(loupeFrame);window.removeEventListener('resize',resize);document.removeEventListener('keydown',key,true)})
</script>
<template>
 <div v-if="openingPanel" class="capture-panel-preparing" role="status"><RefreshCw :size="15"/>{{openingPanel==='voice'?'正在打开语音通话':'正在打开截图对话'}}</div>
 <section ref="root" class="capture-overlay" :style="{cursor:captureCursor}" :data-source-id="source.id" :data-ready="ready" :class="{'floating-preview-editor':floatingPreview,'scroll-live':scrollLive,'has-selection':selection,'has-process-result':!!resultAction||conversationOpen,'annotating':tool!=='select','moving-annotations':tool==='objects','annotation-hover':hoverMark!==undefined,'annotation-dragging':drawing&&mode==='object','mosaic-brushing':tool==='mosaic'&&mosaicMode==='brush'}" tabindex="-1" aria-label="区域截图" @pointerdown="down($event)" @pointermove="move" @pointerleave="pointer=undefined" @pointerup="up" @pointercancel="up" @dblclick="editText" @contextmenu.prevent="!floatingPreview&&requestCancel()" @wheel="zoomFloating">
  <canvas ref="canvas" class="capture-screen" :style="{left:imagePos.x+'px',top:imagePos.y+'px',width:source.width*scale+'px',height:source.height*scale+'px'}" aria-label="待截取的屏幕"/>
  <svg v-if="!floatingPreview" class="capture-shade" :width="viewport.w" :height="viewport.h"><path :d="mask" fill="rgba(0,0,0,.38)" fill-rule="evenodd"/></svg>
  <button v-if="floatingPreview&&ready" class="floating-editor-close" aria-label="关闭图片编辑" data-tooltip-disabled :style="{left:(imagePos.x+source.width*scale-34)+'px',top:(imagePos.y+6)+'px'}" @pointerdown.stop @click.stop="requestCancel()"><X :size="18"/></button>
  <div v-if="tool==='mosaic'&&mosaicMode==='brush'&&pointer&&pointerInsideSelection&&!closing" class="mosaic-brush-cursor" :class="{'is-square':mosaicShape==='square'}" :style="mosaicCursorStyle"/>
  <div v-if="contentBrushVisible" class="capture-content-brush-cursor" :class="{'is-square':contentBrushShape==='square'}" :style="contentBrushStyle" :aria-label="(tool==='highlight'?'荧光笔':'涂抹消除')+'画刷预览'"/>
  <div v-if="mosaicArea" class="mosaic-area-preview" :style="mosaicAreaStyle"/>
  <div v-if="['objects','eraser'].includes(tool)&&selectedMarkStyle" class="capture-mark-selection" :style="selectedMarkStyle" aria-label="已选中的标注"><button v-if="tool==='objects'" class="capture-mark-resize" aria-label="缩放标注" style="right:-4px;bottom:-4px;cursor:nwse-resize" @pointerdown.stop="beginMarkResize" @pointermove.stop="moveMarkResize" @pointerup.stop="endMarkResize" @pointercancel.stop="endMarkResize"/></div>
  <textarea v-if="textAnchor" ref="textEditor" v-model="annotation" class="capture-text-editor" :style="textEditorStyle" aria-label="截图文字标注" placeholder="输入文字" wrap="off" maxlength="500" spellcheck="false" @pointerdown.stop @keydown.stop="textKey" @contextmenu.stop/>
  <aside v-if="loupeVisible&&pointer" class="capture-loupe" :style="loupeStyle" aria-label="截图像素放大镜">
   <div class="capture-loupe-image"><canvas ref="loupe" width="171" height="171"/><i class="capture-loupe-crosshair"/><i class="capture-loupe-pixel"/></div>
   <div class="capture-loupe-coordinates"><span>坐标：{{pointer.x}}, {{pointer.y}}</span><small>3×</small></div>
   <div class="capture-loupe-color"><span>色值：</span><i :style="{background:pixelHex}"/><strong>{{colorValue}}</strong></div>
   <small v-if="tool==='eyedropper'" class="capture-loupe-hints">Q 复制色值 · Shift 切换 RGB/HEX</small>
  </aside>
  <div v-if="tool!=='scroll'&&!floatingPreview" class="capture-top-controls"><span><Icon name="scan" :size="17"/>SnapMind · 区域截图<i/>{{selection?'拖动选区或边缘调整大小':'按住鼠标，拖动选择截图区域'}}</span><button @click="requestCancel()">Esc 取消<Icon name="close" :size="15"/></button></div>
  <div v-if="display" class="capture-selection" :style="{left:display.x+'px',top:display.y+'px',width:display.w+'px',height:display.h+'px'}">
   <div v-if="tool==='translate'&&visibleTranslationLines.length" ref="translationTextLayer" class="capture-translation-text" aria-label="截图原位译文" @pointerdown.stop @pointermove.stop @pointerup.stop @contextmenu.stop>
    <div v-for="(row,index) in selectableTranslationRows" :key="index" class="capture-translation-row"><template v-for="(line,column) in row" :key="line.id"><span v-if="column" class="capture-translation-separator">{{'\t'}}</span><span class="capture-translated-line" :data-line-id="line.id" :style="translationLineStyle(line)">{{line.text}}</span></template><span class="capture-translation-separator">{{'\n'}}</span></div>
   </div>
   <button v-for="edge in tool==='select'&&!resultAction?['n','e','s','w']:[]" :key="'edge-'+edge" class="capture-crop-edge" :class="'crop-edge-'+edge" :aria-label="'拉伸选区 '+edge" @pointerdown.stop="down($event,edge)"/>
   <span class="capture-size" :class="{'size-inside':display.y<40}">{{selection?selection.w:0}} × {{selection?selection.h:0}}</span>
   <button v-for="h in ['scroll','objects','eraser','translate'].includes(tool)?[]:handles" :key="h" class="capture-handle" :class="'handle-'+h" :aria-label="'调整选区 '+h" @pointerdown.stop="down($event,h)"/>
  </div>
  <div v-if="selection&&!conversationOpen&&!(drawing&&mode==='new')&&tool!=='scroll'" v-show="!voiceOpen" ref="captureToolbar" class="capture-toolbar" :style="toolbarStyle" @pointerdown.stop>
   <div class="capture-tools-scroll"><button v-for="t in annotationTools" :key="t.id" :data-capture-tool="t.id" :data-shortcut="shortcuts[t.id as CaptureToolId]" :aria-keyshortcuts="shortcuts[t.id as CaptureToolId]?.replace('Ctrl','Control')" :disabled="scrollHeight>0" :title="t.id==='eraser'?'点击选中标注，按 Backspace 删除':t.id==='objects'?'\u79fb\u52a8\u6807\u6ce8\uff1a\u62d6\u52a8\u8c03\u6574\u4f4d\u7f6e\uff0cBackspace \u5220\u9664':t.label" :aria-label="'截图'+t.label" :class="{active:tool===t.id}" @click="selectTool(t.id)"><MousePointer2 v-if="t.id==='objects'" :size="22" :stroke-width="1.7"/><Circle v-else-if="t.id==='ellipse'" :size="22" :stroke-width="1.7"/><svg v-else-if="t.id==='blur'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><rect x="3" y="3" width="18" height="18" rx="4"/><rect x="8" y="8" width="8" height="8" rx="1.5"/></svg><Pipette v-else-if="t.id==='eyedropper'" :size="24" :stroke-width="1.7"/><CaptureToolGlyph v-else-if="t.id==='number'" name="sequence"/><Icon v-else :name="t.id" :size="22"/></button><span class="capture-separator"/><button v-for="id in ['ocr', 'translate'] as const" :key="id" :data-capture-tool="id" :data-shortcut="shortcuts[id]" :aria-keyshortcuts="shortcuts[id]?.replace('Ctrl','Control')" :aria-label="actionLabels[id]" :title="actionLabels[id]+(shortcuts[id]?' '+shortcuts[id]:'')" :class="{active:tool===id}" @click="selectTool(id)"><CaptureToolGlyph v-if="id==='translate'" name="translate"/><Icon v-else :name="id==='ocr'?'ocr':'chat'" :size="23"/></button>
   <div v-if="tool==='translate'" class="capture-inline-translation-controls">
    <span v-if="translationBusy" class="capture-inline-translation-progress" role="status"><span class="capture-wait-dots" aria-hidden="true"><i/><i/><i/></span>{{translationPhase}}</span>
    <CaptureDropdown v-model="resultLanguage" label="翻译语言" kind="language" :options="languageOptions" @update:model-value="startTranslation"/>
    <button data-capture-tool="copyTranslation" :data-shortcut="shortcuts.copyTranslation" :aria-keyshortcuts="shortcuts.copyTranslation?.replace('Ctrl','Control')" aria-label="复制全部译文" title="复制全部译文" :disabled="!allTranslatedText||translationBusy" @click="copyText(allTranslatedText)"><Icon name="copy" :size="18"/></button>
    <button data-capture-tool="toggleOriginal" :data-shortcut="shortcuts.toggleOriginal" :aria-keyshortcuts="shortcuts.toggleOriginal?.replace('Ctrl','Control')" :aria-label="translationVisible?'查看原文':'查看译文'" :title="translationVisible?'查看原文':'查看译文'" :disabled="!translationScene||translationBusy" @click="toggleOriginal"><Eye v-if="translationVisible" :size="19"/><EyeOff v-else :size="19"/></button>
    <button data-capture-tool="retryTranslation" :data-shortcut="shortcuts.retryTranslation" :aria-keyshortcuts="shortcuts.retryTranslation?.replace('Ctrl','Control')" aria-label="重新翻译" title="重新翻译" :disabled="translationBusy" @click="startTranslation"><RefreshCw :size="18"/></button>
   </div>
   <button data-capture-tool="scroll" :data-shortcut="shortcuts.scroll" :aria-keyshortcuts="shortcuts.scroll?.replace('Ctrl','Control')" aria-label="滚动截图" title="滚动截图" :class="{active:tool==='scroll'}" @click="selectTool('scroll')"><Icon name="crop" :size="23"/></button><button data-capture-tool="pin" :data-shortcut="shortcuts.pin" :aria-keyshortcuts="shortcuts.pin?.replace('Ctrl','Control')" aria-label="截图贴图" title="贴图" @click="finish('pin')"><Icon name="pin" :size="21"/></button><span class="capture-separator"/><div class="capture-ai-tools" role="group" aria-label="AI 交互"><button class="capture-ai-chat-button" data-capture-tool="chat" :data-shortcut="shortcuts.chat" :aria-keyshortcuts="shortcuts.chat?.replace('Ctrl','Control')" aria-label="AI对话" title="AI对话" data-tooltip="AI对话" :class="{active:conversationOpen}" @click="selectTool('chat')"><Icon name="aiChat" :size="24"/></button><button type="button" class="capture-voice-call-button" data-capture-tool="voiceCall" :data-shortcut="shortcuts.voiceCall" :aria-keyshortcuts="shortcuts.voiceCall?.replace('Ctrl','Control')" aria-label="语音通话" title="语音通话" data-tooltip="语音通话" :class="{active:voiceOpen}" :aria-pressed="voiceOpen" @click="selectTool('voiceCall')"><Icon name="voiceCall" :size="23"/></button></div><span class="capture-separator"/><button data-capture-tool="undo" :data-shortcut="shortcuts.undo" :aria-keyshortcuts="shortcuts.undo?.replace('Ctrl','Control')" aria-label="撤销截图标注" :title="'撤销 '+shortcuts.undo" :disabled="!undoStack.length" @click="undo"><Icon name="undo" :size="22"/></button><button data-capture-tool="redo" :data-shortcut="shortcuts.redo" :aria-keyshortcuts="shortcuts.redo?.replace('Ctrl','Control')" aria-label="重做截图标注" :title="'重做 '+shortcuts.redo" :disabled="!redoStack.length" @click="redo"><Icon name="redo" :size="22"/></button><button data-capture-tool="clear" :data-shortcut="shortcuts.clear" :aria-keyshortcuts="shortcuts.clear?.replace('Ctrl','Control')" aria-label="清空截图标注" title="清空标注（可撤销）" :disabled="!marks.length" @click="clearMarks"><Icon name="trash" :size="21"/></button><span class="capture-separator"/><button data-capture-tool="save" :data-shortcut="shortcuts.save" :aria-keyshortcuts="shortcuts.save?.replace('Ctrl','Control')" aria-label="保存截图" :title="'保存 '+shortcuts.save" :disabled="completing" @click="finish('save')"><Icon name="download" :size="23"/></button><button v-if="!floatingPreview" data-capture-tool="cancel" :data-shortcut="shortcuts.cancel" :aria-keyshortcuts="shortcuts.cancel?.replace('Ctrl','Control')" aria-label="取消截图" title="取消 Esc" @click="requestCancel()"><X :size="24" :stroke-width="1.7"/></button><button class="capture-done" data-capture-tool="copy" :data-shortcut="shortcuts.copy" :aria-keyshortcuts="shortcuts.copy?.replace('Ctrl','Control')" aria-label="完成并复制截图" title="完成并复制 Enter" :disabled="completing" @click="finish('copy')"><Check :size="25" :stroke-width="1.8"/></button></div>
   <div class="capture-tool-options annotation-options" v-if="showOptions">
    <template v-if="tool==='mosaic'">
     <button class="annotation-icon-choice" :class="{chosen:mosaicEffect==='pixel'}" aria-label="像素马赛克" @click="mosaicEffect='pixel'"><Icon name="mosaic" :size="22"/></button><button class="annotation-icon-choice" :class="{chosen:mosaicEffect==='blur'}" aria-label="模糊画刷" @click="mosaicEffect='blur'"><Droplet :size="22"/></button>
     <span class="capture-separator"/><button class="mosaic-shape-choice" :class="{chosen:mosaicShape==='circle'&&mosaicMode==='brush'}" aria-label="圆形画刷" @click="mosaicShape='circle';mosaicMode='brush'"><Circle :size="18"/></button><button class="mosaic-shape-choice" :class="{chosen:mosaicShape==='square'&&mosaicMode==='brush'}" aria-label="正方形画刷" @click="mosaicShape='square';mosaicMode='brush'"><Square :size="18"/></button>
     <button v-for="(n,index) in [18,32,52]" :key="n" class="mosaic-size-choice" :class="{chosen:mosaicSize===n}" :aria-label="'马赛克画刷 '+n" @click="mosaicSize=n;mosaicMode='brush'"><i :class="{'is-square':mosaicShape==='square'}" :style="{width:(7+index*6)+'px',height:(7+index*6)+'px'}"/></button>
     <span class="capture-separator"/><button class="mosaic-area-button" :class="{chosen:mosaicMode==='area'}" aria-label="一键打码" @click="mosaicMode='area'"><Icon name="scan" :size="18"/>一键打码</button>
     <label class="annotation-slider"><span>{{mosaicEffect==='pixel'?'像素':'模糊'}}</span><input v-model.number="mosaicPixels" type="range" min="4" max="24" step="1" aria-label="马赛克强度"/><output>{{mosaicPixels}}</output></label>
    </template>
    <template v-else-if="tool==='eraser'">
     <strong class="capture-action-name">橡皮擦</strong><span class="capture-separator"/><span class="capture-brush-help">点击选中标注，按 Backspace 删除<span v-if="shortcuts.undo"> · {{shortcuts.undo}} 撤销</span></span>
    </template>
    <template v-else-if="tool==='highlight'||tool==='heal'">
     <strong class="capture-action-name">{{tool==='highlight'?'荧光笔':'涂抹消除'}}</strong><span class="capture-separator"/>
     <button v-for="shape in ['circle','square'] as const" :key="shape" class="mosaic-shape-choice" :class="{chosen:contentBrushShape===shape}" :aria-label="(tool==='highlight'?'荧光笔':'涂抹消除')+(shape==='circle'?'圆形画刷':'方形画刷')" @click="tool==='highlight'?highlightShape=shape:repairShape=shape"><Circle v-if="shape==='circle'" :size="18"/><Square v-else :size="18"/></button>
     <button v-for="(n,index) in [16,24,40]" :key="n" class="mosaic-size-choice" :class="{chosen:contentBrushSize===n}" :aria-label="(tool==='highlight'?'荧光笔':'涂抹消除')+'画刷 '+n" @click="tool==='highlight'?highlightSize=n:repairSize=n"><i :class="{'is-square':contentBrushShape==='square'}" :style="{width:(7+index*5)+'px',height:(7+index*5)+'px'}"/></button>
     <label class="annotation-slider"><span>大小</span><input :value="contentBrushSize" type="range" min="8" max="80" step="1" :aria-label="(tool==='highlight'?'荧光笔':'涂抹消除')+'画刷大小'" @input="tool==='highlight'?highlightSize=Number(($event.target as HTMLInputElement).value):repairSize=Number(($event.target as HTMLInputElement).value)"/><output>{{contentBrushSize}}</output></label>
     <template v-if="tool==='highlight'"><span class="capture-separator"/><button v-for="c in highlightPalette" :key="c" class="swatch" :class="{chosen:highlightColor===c}" :style="{background:c}" :aria-label="'高亮颜色 '+c" @click="highlightColor=c"><Check v-if="highlightColor===c" :size="15" style="color:#654787" :stroke-width="2.5"/></button></template>
     <span v-else class="capture-brush-help">涂抹后自动修补背景</span>
    </template>
    <template v-else-if="tool==='lift'"><strong class="capture-action-name">无痕提取</strong><span class="capture-separator"/><span class="capture-brush-help">拖动框选内容，提取为透明图层</span></template>
    <template v-else-if="tool==='blur'">
     <button class="annotation-icon-choice" :class="{chosen:blurShape==='rect'}" aria-label="矩形遮罩" @click="blurShape='rect'"><Square :size="23"/></button><button class="annotation-icon-choice" :class="{chosen:blurShape==='ellipse'}" aria-label="圆形遮罩" @click="blurShape='ellipse'"><Circle :size="23"/></button><button class="annotation-icon-choice" :class="{chosen:blurShape==='round'}" aria-label="圆角遮罩" @click="blurShape='round'"><RectangleHorizontal :size="23"/></button>
     <span class="capture-separator"/><label class="annotation-slider"><span>不透明度</span><input v-model.number="blurOpacity" type="range" min="10" max="100" step="5" aria-label="遮罩不透明度"/><output>{{blurOpacity}}%</output></label><span class="capture-separator"/><label class="annotation-slider"><span>高斯模糊</span><input v-model.number="blurRadius" type="range" min="1" max="24" step="1" aria-label="高斯模糊强度"/><output>{{blurRadius}}</output></label>
    </template>
    <template v-else>
     <template v-if="tool==='arrow'"><CaptureDropdown v-model="arrowStyle" label="箭头样式" kind="arrow" :options="arrowOptions"/><CaptureDropdown v-model="lineStyle" label="线条样式" kind="line" :options="lineOptions"/><span class="capture-separator"/></template>
     <template v-if="tool==='text'"><button v-for="(n,index) in [16,24,32]" :key="n" class="capture-font-choice" :class="{chosen:textSize===n}" :style="{color,fontSize:(12+index*4)+'px'}" :aria-label="'字号 '+n" @click="textSize=n;textEditor?.focus()">T</button><span class="capture-separator"/></template>
     <template v-else-if="tool!=='number'"><button v-for="n in [2,3,5]" :key="n" class="stroke-choice" :class="{chosen:stroke===n}" :aria-label="'线宽 '+n" @click="stroke=n"><i :style="{width:(n*3+1)+'px',height:(n*3+1)+'px',background:color}"/></button><span class="capture-separator"/></template>
     <button v-for="c in palette" :key="c" class="swatch" :class="{chosen:color===c}" :style="{background:c}" :aria-label="'颜色 '+c" @click="color=c;textEditor?.focus()"><Check v-if="color===c" :size="15" :style="{color:c==='#ffffff'?'#333':'#fff'}" :stroke-width="2.5"/></button>
     <template v-if="tool==='rect'"><span class="capture-separator"/><label class="annotation-check"><input v-model="rectRounded" type="checkbox" aria-label="矩形圆角"/>圆角</label></template>
     <template v-if="tool==='rect'||tool==='ellipse'"><span v-if="tool==='ellipse'" class="capture-separator"/><label class="annotation-check"><input v-model="shapeFilled" type="checkbox" aria-label="实心填充"/>实心</label></template>
     <template v-if="tool==='pen'"><span class="capture-separator"/><label class="annotation-pen-width">画笔<input v-model.number="stroke" type="number" min="1" max="30" aria-label="画笔宽度" @blur="stroke=Math.max(1,Math.min(30,Number(stroke)||3))"/></label></template>
    </template>
    <template v-if="tool==='number'"><span class="capture-separator"/><label class="annotation-pen-width">序号<input v-model.number="number" type="number" min="1" max="9999" aria-label="起始序号" @blur="number=Math.max(1,Math.min(9999,Math.round(Number(number)||1)))"/></label></template>
    <button class="annotation-options-close" @click="showOptions=false" aria-label="收起标注选项"><Icon name="close" :size="16"/></button>
   </div>
  </div>
  <template v-if="tool==='scroll'&&display">
   <div class="scroll-capture-hint" :style="{left:display.x+'px',top:Math.max(18,display.y-38)+'px'}">滚动页面截取更多内容</div>
   <aside v-if="scrollPreviewData" class="scroll-capture-preview" :style="scrollPreviewStyle" @pointerdown.stop @wheel.stop.prevent>
    <img :src="scrollPreviewData" alt="已拼接的长截图"/><span>{{selection!.w}} × {{scrollHeight}}</span>
   </aside>
   <div ref="captureToolbar" class="capture-toolbar scroll-capture-toolbar" :data-busy="scrollBusy" :data-height="scrollHeight" :style="toolbarStyle" @pointerdown.stop>
    <div class="capture-tools-scroll"><button data-capture-tool="longEdit" :data-shortcut="shortcuts.longEdit" :aria-keyshortcuts="shortcuts.longEdit?.replace('Ctrl','Control')" aria-label="编辑长截图" title="编辑长截图" :disabled="!scrollHeight" @click="editLong"><Icon name="edit" :size="23"/></button><button data-capture-tool="save" :data-shortcut="shortcuts.save" :aria-keyshortcuts="shortcuts.save?.replace('Ctrl','Control')" aria-label="保存长截图" title="保存长截图" :disabled="!scrollHeight" @click="finish('save')"><Icon name="download" :size="23"/></button><button v-if="!floatingPreview" class="scroll-capture-cancel" data-capture-tool="cancel" :data-shortcut="shortcuts.cancel" :aria-keyshortcuts="shortcuts.cancel?.replace('Ctrl','Control')" aria-label="取消滚动截图" title="取消 Esc" @click="requestCancel()"><X :size="24"/></button><button class="capture-done" data-capture-tool="copy" :data-shortcut="shortcuts.copy" :aria-keyshortcuts="shortcuts.copy?.replace('Ctrl','Control')" aria-label="完成并复制长截图" title="完成并复制 Enter" :disabled="!scrollHeight" @click="finish('copy')"><Check :size="25"/></button></div>
    <p v-if="scrollError" class="scroll-capture-message" role="status">{{scrollError}}</p>
   </div>
  </template>
  <VoiceSpirit v-if="voiceOpen&&voiceAsset&&display" ref="voicePanel" :asset="voiceAsset" :rendered="voiceRendered" :annotations="voiceAnnotations" :anchor="display" :execute="executeVoice" @close="closeVoice"/>
  <aside v-if="conversationOpen&&conversationAsset" class="capture-process-result capture-conversation-panel" :style="resultPanelStyle" aria-label="图片对话面板" @pointerdown.stop @contextmenu.stop><header @pointerdown="beginResultDrag" @pointermove.stop="moveResultDrag" @pointerup.stop="endResultDrag" @pointercancel.stop="endResultDrag"><Icon name="aiChat" :size="24"/><strong>AI 对话</strong><button type="button" class="capture-history-button" aria-label="历史对话" data-tooltip="历史对话" @pointerdown.stop @click="conversationPanel?.showHistory()"><Icon name="clock" :size="18"/></button><button type="button" title="关闭对话" aria-label="关闭截图对话" @click="closeConversation"><X :size="19"/></button></header><ImageConversation ref="conversationPanel" :key="conversationAsset.id" :initial="conversationAsset" :controls="conversationControls" :apply-result="applyConversation" @toast="emit('toast',$event)" @close="closeConversation"/><button v-for="edge in handles" :key="edge" class="capture-result-resize" :class="'resize-'+edge" :aria-label="'调整对话面板 '+edge" @pointerdown.stop="beginResultResize($event,edge)" @pointermove.stop="moveResultResize" @pointerup.stop="endResultResize"/></aside>
  <aside v-if="resultAction" class="capture-process-result" :class="{'is-dragging':resultPanelDragging,'is-resizing':resultPanelResizing}" :style="resultPanelStyle" :aria-label="actionLabels[resultAction]+'结果'" :aria-busy="processing" @pointerdown.stop @contextmenu.stop>
   <header title="拖动标题栏移动面板" @pointerdown="beginResultDrag" @pointermove.stop="moveResultDrag" @pointerup.stop="endResultDrag" @pointercancel.stop="endResultDrag" @lostpointercapture="endResultDrag"><Icon :name="resultAction==='ocr'?'ocr':'file'" :size="20"/><strong>{{actionLabels[resultAction]}}</strong><button aria-label="关闭处理结果" @click="closeResult"><X :size="19"/></button></header>
   <div v-if="processing" class="capture-process-loading" role="status"><div class="capture-wait-dots" aria-hidden="true"><i/><i/><i/></div><span>正在{{actionLabels[resultAction]}}</span></div>
   <p v-else-if="resultError" role="alert" class="capture-process-error">{{resultError}}</p>
   <textarea v-else v-model="resultText" aria-label="处理结果" spellcheck="false" wrap="soft"/>
   <footer><button :disabled="processing||!resultText" @click="copyText(resultText)"><Icon name="copy" :size="17"/>复制结果</button><button :disabled="processing" @click="processSelection(resultAction!)"><RefreshCw :size="17" :stroke-width="1.7"/>重新生成</button></footer>
   <button v-for="edge in handles" :key="edge" type="button" tabindex="-1" class="capture-result-resize" :class="'resize-'+edge" :aria-label="'调整结果面板 '+edge" title="拖动调整面板大小" @pointerdown.stop="beginResultResize($event,edge)" @pointermove.stop="moveResultResize" @pointerup.stop="endResultResize" @pointercancel.stop="endResultResize" @lostpointercapture="endResultResize"/>
  </aside>
 <div v-if="!selection" class="capture-instruction"><RectangleHorizontal :size="32" :stroke-width="1.4"/><span>拖动框选截图区域</span><small>Esc 取消 · 框选后标注、复制或保存</small></div>
 </section>
</template>
