<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount,nextTick} from 'vue'
import {desktop} from '../desktop'
import type {Asset} from '../types'
import Icon from './Icon.vue'
const asset=ref<Asset>(),error=ref(''),selected=ref(false),editing=ref(false)
const dispose:(()=>void)[]=[]
let dragStart:{x:number;y:number}|undefined,zoomFrame=0,zoomFactor=1,zoomBusy=false
function down(e:PointerEvent){if(e.button!==0||editing.value)return;selected.value=true;dragStart={x:e.clientX,y:e.clientY}}
function move(e:PointerEvent){if(dragStart&&(e.buttons&1)&&Math.hypot(e.clientX-dragStart.x,e.clientY-dragStart.y)>4){dragStart=undefined;desktop.drag().catch(e=>error.value=String(e))}}
async function context(){dragStart=undefined;if(!asset.value||editing.value)return;editing.value=true;try{await desktop.edit()}catch{error.value='无法打开图片编辑，请重试。'}finally{editing.value=false}}
function wheel(e:WheelEvent){if(!selected.value||editing.value||!e.deltaY)return;zoomFactor*=e.deltaY<0?1.12:1/1.12;if(!zoomFrame&&!zoomBusy)zoomFrame=requestAnimationFrame(applyZoom)}
async function applyZoom(){zoomFrame=0;const factor=zoomFactor;zoomFactor=1;zoomBusy=true;try{await desktop.zoomImage(factor)}catch(e){error.value=String(e)}finally{zoomBusy=false;if(zoomFactor!==1)zoomFrame=requestAnimationFrame(applyZoom)}}
function key(e:KeyboardEvent){if(e.key==='Escape'){e.preventDefault();desktop.hide()}}
async function imageReady(e:Event){const image=e.target as HTMLImageElement,id=asset.value?.id;if(!id)return;try{await image.decode();await nextTick();await new Promise<void>(resolve=>{let frame=0;const finish=()=>{clearTimeout(timer);cancelAnimationFrame(frame);resolve()};const timer=setTimeout(finish,100);frame=requestAnimationFrame(()=>{frame=requestAnimationFrame(finish)})});if(asset.value?.id===id)await desktop.contentReady(id)}catch(e){error.value=String(e)}}
onMounted(async()=>{document.addEventListener('keydown',key);dispose.push(await desktop.listen<Asset|undefined>('desktop:asset-ready',a=>{asset.value=a;error.value='';selected.value=false}));dispose.push(await desktop.onFocus(focused=>{if(!focused)selected.value=false}));asset.value=(await desktop.state()).asset})
onBeforeUnmount(()=>{dispose.forEach(fn=>fn());cancelAnimationFrame(zoomFrame);document.removeEventListener('keydown',key)})
</script>
<template>
 <section class="native-image-window pin-image-only" :class="{'pin-selected':selected}" @pointerdown="down" @pointermove="move" @pointerup="dragStart=undefined" @pointercancel="dragStart=undefined" @contextmenu.prevent="context" @wheel.prevent="wheel" tabindex="0" aria-label="浮动截图">
  <div class="native-image"><img v-if="asset" :key="asset.data" :src="asset.data" @load="imageReady" :alt="asset.name" draggable="false"/></div>
  <button class="pin-close-button" aria-label="关闭贴图" data-tooltip-disabled @pointerdown.stop @click.stop="desktop.hide()"><Icon name="close" :size="16"/></button>
  <div class="native-image-notice" v-if="error" @click="error=''">{{error}}</div>
 </section>
</template>
