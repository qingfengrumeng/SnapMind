<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import Icon from './Icon.vue'
import type { Asset } from '../types'
const props=defineProps<{asset:Asset;x:number;y:number;width:number;workspaceOpen:boolean}>()
const emit=defineEmits<{geometry:[rect:{x:number;y:number;width:number}];close:[];edit:[];copy:[];save:[];ai:[action:string];toast:[message:string]}>()
const position=ref({x:props.x,y:props.y,width:props.width}),dragging=ref(false),resizing=ref(false),showAi=ref(false)
const height=computed(()=>Math.min(position.value.width*props.asset.height/props.asset.width,Math.max(150,innerHeight-position.value.y-115)))
let start={x:0,y:0},origin={x:0,y:0,width:0},corner=''
function down(e:PointerEvent){if((e.target as Element).closest('button'))return;origin={...position.value};start={x:e.clientX,y:e.clientY};dragging.value=true;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}
function resizeDown(e:PointerEvent,c:string){origin={...position.value};start={x:e.clientX,y:e.clientY};corner=c;resizing.value=true;(e.currentTarget as HTMLElement).setPointerCapture(e.pointerId)}
function move(e:PointerEvent){if(dragging.value){position.value.x=Math.max(0,Math.min(innerWidth-80,origin.x+e.clientX-start.x));position.value.y=Math.max(8,Math.min(innerHeight-60,origin.y+e.clientY-start.y))}if(resizing.value){const sign=corner.includes('w')?-1:1,delta=(e.clientX-start.x)*sign;const available=corner.includes('w')?origin.x+origin.width:innerWidth-origin.x-12;const limit=Math.min(available,(innerHeight-position.value.y-100)*props.asset.width/props.asset.height);const width=Math.max(200,Math.min(limit,origin.width+delta));position.value={...position.value,width,x:corner.includes('w')?origin.x+origin.width-width:origin.x};if(corner.includes('n'))position.value.y=origin.y+(origin.width-width)*props.asset.height/props.asset.width} }
function stop(){dragging.value=false;resizing.value=false;emit('geometry',{...position.value})}
function zoom(n:number){const max=Math.min(innerWidth-position.value.x-12,(innerHeight-position.value.y-100)*props.asset.width/props.asset.height);position.value.width=Math.max(200,Math.min(max,position.value.width*n));emit('geometry',{...position.value})}
function fit(){position.value={x:props.x,y:props.y,width:props.width};emit('geometry',{...position.value})}
watch(()=>[props.asset.id,props.x,props.y,props.width],()=>{position.value={x:props.x,y:props.y,width:props.width};showAi.value=false})
function viewport(){position.value.x=Math.max(8,Math.min(position.value.x,innerWidth-position.value.width-12));position.value.y=Math.max(8,Math.min(position.value.y,innerHeight-height.value-100));emit('geometry',{...position.value})}
onMounted(()=>window.addEventListener('resize',viewport))
onBeforeUnmount(()=>window.removeEventListener('resize',viewport))
</script>
<template>
 <section class="floating-screenshot" :class="{moving:dragging}" :style="{left:position.x+'px',top:position.y+'px',width:position.width+'px'}" aria-label="浮动截图">
  <header class="floating-image-titlebar" @pointerdown="down" @pointermove="move" @pointerup="stop" @pointercancel="stop"><span><Icon name="images" :size="14"/>截图 {{asset.width}} × {{asset.height}}</span><div><span class="float-drag-hint">拖动</span><button title="关闭浮动截图" aria-label="关闭浮动截图" @click="emit('close')"><Icon name="close" :size="16"/></button></div></header>
  <div class="floating-image-body" :style="{height:height+'px'}" @pointerdown="down" @pointermove="move" @pointerup="stop" @pointercancel="stop"><img :src="asset.data" :alt="asset.name" draggable="false"/><button v-for="c in ['nw','ne','se','sw']" :key="c" class="float-resize" :class="'float-resize-'+c" :aria-label="'缩放浮动截图 '+c" @pointerdown.stop="resizeDown($event,c)" @pointermove="move" @pointerup="stop" @pointercancel="stop"/></div>
  <div class="floating-image-toolbar"><button title="缩小截图" aria-label="缩小浮动截图" @click="zoom(.85)"><Icon name="zoomOut" :size="17"/></button><span>{{Math.round(position.width/asset.width*100)}}%</span><button title="放大截图" aria-label="放大浮动截图" @click="zoom(1.15)"><Icon name="zoomIn" :size="17"/></button><button title="恢复截图大小与位置" aria-label="恢复浮动截图" @click="fit"><Icon name="fit" :size="16"/></button><i/><button title="继续标注" aria-label="标注浮动截图" @click="emit('edit')"><Icon name="pen" :size="18"/></button><button title="复制截图" aria-label="复制浮动截图" @click="emit('copy')"><Icon name="copy" :size="17"/></button><button title="保存截图" aria-label="保存浮动截图" @click="emit('save')"><Icon name="download" :size="18"/></button><button class="float-ai-button" :class="{active:workspaceOpen}" title="打开右侧内容工作区" aria-label="浮动截图 AI 工作区" @click="emit('ai','open')"><Icon name="sparkles" :size="16"/><span>AI</span></button></div>
 </section>
</template>
