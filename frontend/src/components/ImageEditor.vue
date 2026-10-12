<script setup lang="ts">
import { computed, ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue'
import Icon from './Icon.vue'
import type { Asset } from '../types'
const props=defineProps<{asset?: Asset}>()
const emit=defineEmits<{change:[data:string,width:number,height:number]; upload:[]; toast:[message:string]}>()
const canvas=ref<HTMLCanvasElement>(),stage=ref<HTMLDivElement>(), tool=ref('cursor'),zoom=ref(1),baseScale=ref(1),color=ref('#e66b58'),text=ref('重点'),undo=ref<string[]>([]),crop=ref<{x:number;y:number;w:number;h:number}>(),isDrawing=ref(false)
const tools=[{id:'cursor',label:'选择'},{id:'rect',label:'矩形'},{id:'arrow',label:'箭头'},{id:'pen',label:'画笔'},{id:'text',label:'文字'},{id:'mosaic',label:'马赛克'},{id:'crop',label:'裁剪'}]
const scale=computed(()=>baseScale.value*zoom.value)
let original: HTMLImageElement|undefined,start={x:0,y:0},previous={x:0,y:0},snapshot:ImageData|undefined,observer:ResizeObserver|undefined
function fit(){if(!stage.value||!props.asset)return; baseScale.value=Math.min((stage.value.clientWidth-64)/props.asset.width,(stage.value.clientHeight-62)/props.asset.height,1);baseScale.value=Math.max(.05,baseScale.value)}
async function load(){await nextTick(); if(!canvas.value||!props.asset)return;const img=new Image();img.src=props.asset.data;await img.decode();if(img.src!==props.asset?.data)return;original=img;canvas.value.width=props.asset.width;canvas.value.height=props.asset.height;canvas.value.getContext('2d')!.drawImage(img,0,0);fit()}
watch(()=>props.asset?.id,()=>{undo.value=[];zoom.value=1;crop.value=undefined;tool.value='cursor'})
watch(()=>props.asset?.data,load,{immediate:true})
function point(e:PointerEvent){const r=canvas.value!.getBoundingClientRect();return {x:(e.clientX-r.left)/scale.value,y:(e.clientY-r.top)/scale.value}}
function down(e:PointerEvent){if(tool.value==='cursor'||!canvas.value)return;const c=canvas.value,g=c.getContext('2d')!; start=point(e);previous=start;snapshot=g.getImageData(0,0,c.width,c.height);c.setPointerCapture(e.pointerId);isDrawing.value=true
 if(tool.value==='text'){undo.value.push(c.toDataURL());g.font=`${Math.max(22,c.width/30)}px Arial`;g.fillStyle=color.value;g.fillText(text.value||'重点',start.x,start.y);commit();isDrawing.value=false}
}
function move(e:PointerEvent){if(!isDrawing.value||!canvas.value||!snapshot)return;const p=point(e),g=canvas.value.getContext('2d')!,w=canvas.value.width;g.lineWidth=Math.max(3,w/240);g.strokeStyle=color.value;g.fillStyle=color.value;g.lineCap='round'
 if(tool.value==='pen'){g.beginPath();g.moveTo(previous.x,previous.y);g.lineTo(p.x,p.y);g.stroke();previous=p;return}
 g.putImageData(snapshot,0,0)
 if(tool.value==='rect')g.strokeRect(start.x,start.y,p.x-start.x,p.y-start.y)
 if(tool.value==='arrow'){g.beginPath();g.moveTo(start.x,start.y);g.lineTo(p.x,p.y);g.stroke();const a=Math.atan2(p.y-start.y,p.x-start.x),n=Math.max(16,w/45);g.beginPath();g.moveTo(p.x,p.y);g.lineTo(p.x-n*Math.cos(a-.45),p.y-n*Math.sin(a-.45));g.lineTo(p.x-n*Math.cos(a+.45),p.y-n*Math.sin(a+.45));g.closePath();g.fill()}
 const box={x:Math.round(Math.max(0,Math.min(start.x,p.x))),y:Math.round(Math.max(0,Math.min(start.y,p.y))),w:Math.round(Math.min(w,Math.max(start.x,p.x))-Math.max(0,Math.min(start.x,p.x))),h:Math.round(Math.min(canvas.value.height,Math.max(start.y,p.y))-Math.max(0,Math.min(start.y,p.y)))}
 if(tool.value==='crop'){crop.value=box;g.strokeStyle='#21856d';g.setLineDash([10,5]);g.strokeRect(box.x,box.y,box.w,box.h);g.setLineDash([])}
 if(tool.value==='mosaic'){const size=Math.max(12,Math.round(w/50));for(let y=box.y;y<box.y+box.h;y+=size)for(let x=box.x;x<box.x+box.w;x+=size){const pixel=g.getImageData(x,y,1,1).data;g.fillStyle=`rgb(${pixel[0]},${pixel[1]},${pixel[2]})`;g.fillRect(x,y,Math.min(size,box.x+box.w-x),Math.min(size,box.y+box.h-y))}}
}
function up(){if(!isDrawing.value||!canvas.value||!snapshot)return;isDrawing.value=false;if(tool.value==='crop')return;const temp=document.createElement('canvas');temp.width=canvas.value.width;temp.height=canvas.value.height;temp.getContext('2d')!.putImageData(snapshot,0,0);undo.value.push(temp.toDataURL());if(undo.value.length>15)undo.value.shift();commit()}
function commit(){const c=canvas.value!;emit('change',c.toDataURL('image/png'),c.width,c.height)}
async function undoLast(){const data=undo.value.pop();if(!data)return;const img=new Image();img.src=data;await img.decode();canvas.value!.width=img.width;canvas.value!.height=img.height;canvas.value!.getContext('2d')!.drawImage(img,0,0);commit()}
function applyCrop(){if(!crop.value||!canvas.value||!snapshot||crop.value.w<5||crop.value.h<5){emit('toast','请拖动框选要保留的区域');return}const c=canvas.value,g=c.getContext('2d')!;g.putImageData(snapshot,0,0);undo.value.push(c.toDataURL());const b=crop.value,data=g.getImageData(b.x,b.y,b.w,b.h);c.width=b.w;c.height=b.h;c.getContext('2d')!.putImageData(data,0,0);crop.value=undefined;tool.value='cursor';commit()}
function cancelCrop(){if(canvas.value&&snapshot)canvas.value.getContext('2d')!.putImageData(snapshot,0,0);crop.value=undefined;tool.value='cursor'}
function changeTool(id:string){if(crop.value)cancelCrop();tool.value=id}
async function copy(){if(!canvas.value)return;try{const blob=await new Promise<Blob|null>(resolve=>canvas.value!.toBlob(resolve));if(blob)await navigator.clipboard.write([new ClipboardItem({'image/png':blob})]);emit('toast','截图已复制到剪贴板')}catch{emit('toast','浏览器未允许复制图片，请使用下载保存')}}
function download(){if(!canvas.value)return;const a=document.createElement('a');a.href=canvas.value.toDataURL();a.download=(props.asset?.name||'截图')+'.png';a.click();emit('toast','已保存 PNG 截图')}
onMounted(()=>{observer=new ResizeObserver(fit);if(stage.value)observer.observe(stage.value);load()})
onBeforeUnmount(()=>observer?.disconnect())
</script>
<template>
 <div class="image-editor">
  <div class="canvas-stage" ref="stage" :class="{'drawing':tool!=='cursor'}">
   <template v-if="asset"><div class="canvas-paper" :style="{width:asset.width*scale+'px',height:asset.height*scale+'px'}"><canvas ref="canvas" :style="{width:asset.width*scale+'px',height:asset.height*scale+'px'}" @pointerdown="down" @pointermove="move" @pointerup="up" @pointercancel="up" aria-label="截图标注画布"/></div><div class="capture-dimensions">{{asset.width}} × {{asset.height}} px <span>·</span> {{Math.round(scale*100)}}%</div></template>
   <div class="empty-canvas" v-else><div class="empty-icon"><Icon name="scan" :size="35"/></div><h3>从一张截图开始</h3><p>导入、粘贴，或截取屏幕中的一个区域</p><button class="primary" @click="emit('upload')"><Icon name="upload"/>导入图片</button><small>支持 PNG、JPG、WebP · 单张不超过 8 MB</small></div>
  </div>
  <div v-if="asset" class="editing-controls">
   <div v-if="crop" class="crop-confirm"><span>保留框选区域</span><button @click="cancelCrop">取消</button><button class="primary small" @click="applyCrop">确认裁剪</button></div>
   <div v-if="tool==='text'" class="annotation-options"><label>标注文字<input v-model="text" maxlength="100" placeholder="输入后点击截图"/></label></div>
   <div class="annotation-bar"><button v-for="t in tools" :key="t.id" :class="{selected:tool===t.id}" :title="t.label" :aria-label="t.label" @click="changeTool(t.id)"><Icon :name="t.id" :size="18"/></button><span class="tool-separator"/><label class="color-picker" title="标注颜色"><input type="color" v-model="color" aria-label="标注颜色"/></label><button title="撤销标注" aria-label="撤销标注" @click="undoLast" :disabled="!undo.length"><Icon name="undo"/></button></div>
   <div class="image-bottom"><div class="zoom-controls"><button aria-label="缩小" @click="zoom=Math.max(.4,zoom-.2)"><Icon name="zoomOut" :size="16"/></button><button class="zoom-value" @click="zoom=1">{{Math.round(zoom*100)}}%</button><button aria-label="放大" @click="zoom=Math.min(3,zoom+.2)"><Icon name="zoomIn" :size="16"/></button><button aria-label="适应画布" title="适应画布" @click="zoom=1;fit()"><Icon name="fit" :size="16"/></button></div><div class="image-export"><button @click="copy" title="复制图片"><Icon name="copy" :size="16"/><span>复制</span></button><button @click="download" title="保存图片"><Icon name="download" :size="16"/><span>保存</span></button></div></div>
  </div>
 </div>
</template>
