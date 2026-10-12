<script setup lang="ts">
import {ref,computed,onMounted,onBeforeUnmount,nextTick} from 'vue'
import type {Asset} from '../types'
import Icon from './Icon.vue'
const props=defineProps<{asset:Asset}>(),emit=defineEmits<{close:[]}>()
const dialog=ref<HTMLElement>(),viewport=ref<HTMLElement>(),zoom=ref(1),size=ref({width:0,height:0})
const imageStyle=computed(()=>({width:props.asset.width*zoom.value+'px',height:props.asset.height*zoom.value+'px'}))
const stageStyle=computed(()=>({width:Math.max(size.value.width,props.asset.width*zoom.value)+'px',height:Math.max(size.value.height,props.asset.height*zoom.value)+'px'}))
let observer:ResizeObserver|undefined,previousFocus:HTMLElement|null=null,drag:{x:number;y:number;left:number;top:number;pointer:number}|undefined
function changeZoom(value:number){zoom.value=Math.max(.1,Math.min(4,value))}
function startDrag(e:PointerEvent){if(e.button!==0||!viewport.value)return;drag={x:e.clientX,y:e.clientY,left:viewport.value.scrollLeft,top:viewport.value.scrollTop,pointer:e.pointerId};viewport.value.setPointerCapture(e.pointerId)}
function moveDrag(e:PointerEvent){if(!drag||drag.pointer!==e.pointerId||!viewport.value)return;viewport.value.scrollLeft=drag.left+drag.x-e.clientX;viewport.value.scrollTop=drag.top+drag.y-e.clientY}
function endDrag(){drag=undefined}
function key(e:KeyboardEvent){
 if(e.key==='Escape'){e.preventDefault();emit('close')}
 if(e.key!=='Tab')return
 const buttons=Array.from(dialog.value?.querySelectorAll<HTMLButtonElement>('button:not(:disabled)')||[]),first=buttons[0],last=buttons.at(-1)
 if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}
}
onMounted(async()=>{previousFocus=document.activeElement as HTMLElement;await nextTick();const field=viewport.value;if(!field)return;const fit=()=>{size.value={width:field.clientWidth,height:field.clientHeight}};fit();zoom.value=Math.min(1,(field.clientWidth-32)/props.asset.width,(field.clientHeight-32)/props.asset.height);observer=new ResizeObserver(fit);observer.observe(field);dialog.value?.querySelector<HTMLButtonElement>('[aria-label="关闭图片预览"]')?.focus()})
onBeforeUnmount(()=>{observer?.disconnect();previousFocus?.focus()})
</script>
<template>
 <Teleport to="body"><div class="image-chat-lightbox" @pointerdown.self="emit('close')" @pointerdown.stop @contextmenu.prevent.stop @wheel.stop @keydown.stop="key">
  <section ref="dialog" class="image-chat-lightbox-dialog" role="dialog" aria-modal="true" :aria-label="'图片预览 '+asset.name">
   <header><Icon name="image" :size="21"/><strong>{{asset.name}}</strong><div><button aria-label="缩小图片" :disabled="zoom<=.1" @click="changeZoom(zoom/1.25)"><Icon name="zoomOut" :size="21"/></button><button aria-label="图片原始大小" @click="changeZoom(1)">{{Math.round(zoom*100)}}%</button><button aria-label="放大图片" :disabled="zoom>=4" @click="changeZoom(zoom*1.25)"><Icon name="zoomIn" :size="21"/></button><button aria-label="关闭图片预览" @click="emit('close')"><Icon name="close" :size="23"/></button></div></header>
   <div ref="viewport" class="image-chat-lightbox-viewport" @wheel.prevent="changeZoom(zoom*($event.deltaY<0?1.12:1/1.12))" @pointerdown.prevent="startDrag" @pointermove="moveDrag" @pointerup="endDrag" @pointercancel="endDrag"><div class="image-chat-lightbox-stage" :style="stageStyle"><img :src="asset.data" :alt="asset.name" :style="imageStyle" draggable="false"/></div></div>
  </section>
 </div></Teleport>
</template>
