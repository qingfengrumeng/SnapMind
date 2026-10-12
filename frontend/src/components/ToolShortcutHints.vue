<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref} from 'vue'
import ToolShortcutPicker from './ToolShortcutPicker.vue'
import {toolShortcutCatalog,type CaptureToolId} from '../tool-shortcuts'
const toolId=ref<CaptureToolId>(),panel=ref<HTMLElement>(),position=ref({left:0,top:0,below:false,ready:false}),label=computed(()=>toolShortcutCatalog.find(t=>t.id===toolId.value)?.label||'')
let anchor:HTMLButtonElement|undefined,timer:ReturnType<typeof setTimeout>|undefined,leaveTimer:ReturnType<typeof setTimeout>|undefined,title:string|null=null
function clearTimer(){clearTimeout(timer);clearTimeout(leaveTimer)}
function hide(){clearTimer();toolId.value=undefined;if(anchor&&title!==null&&!anchor.hasAttribute('title'))anchor.setAttribute('title',title);anchor=undefined;title=null}
function keep(){clearTimeout(leaveTimer)}
function leave(){clearTimeout(leaveTimer);leaveTimer=setTimeout(()=>{if(panel.value?.querySelector('.recording')||panel.value?.matches(':hover')||anchor?.matches(':hover')||anchor===document.activeElement||panel.value?.contains(document.activeElement))return;hide()},240)}
async function place(){await nextTick();if(!anchor||!panel.value)return;const a=anchor.getBoundingClientRect(),r=panel.value.getBoundingClientRect(),below=a.top<r.height+18;position.value={left:Math.max(8,Math.min(innerWidth-r.width-8,a.left+a.width/2-r.width/2)),top:Math.max(8,below?Math.min(innerHeight-r.height-8,a.bottom+10):a.top-r.height-10),below,ready:true}}
function queue(button:HTMLButtonElement){if(anchor===button||panel.value?.querySelector('.recording')){keep();return}hide();anchor=button;title=button.getAttribute('title');button.removeAttribute('title');timer=setTimeout(()=>{if(!button.isConnected){hide();return}toolId.value=button.dataset.captureTool as CaptureToolId;position.value.ready=false;place()},220)}
function candidate(node:EventTarget|null){if(!(node instanceof Element))return;const button=node.closest<HTMLButtonElement>('button[data-capture-tool]');if(button&&toolShortcutCatalog.some(t=>t.id===button.dataset.captureTool))return button}
function over(e:PointerEvent){if((e.target as Element)?.closest('.tool-shortcut-popup,.shortcut-menu')){keep();return}const b=candidate(e.target);if(b)queue(b);else if(anchor)leave()}
function out(e:PointerEvent){if(anchor&&!anchor.contains(e.relatedTarget as Node)&&!panel.value?.contains(e.relatedTarget as Node))leave()}
function focus(e:FocusEvent){const b=candidate(e.target);if(b)queue(b)}
function down(e:PointerEvent){if((e.target as Element)?.closest('.tool-shortcut-popup,.shortcut-menu'))return;hide()}
function scroll(e:Event){if((e.target as Element)?.closest?.('.tool-shortcut-popup'))return;if(anchor===document.activeElement||panel.value?.querySelector('.recording')||panel.value?.contains(document.activeElement)){place();return}hide()}
function key(e:KeyboardEvent){if(e.key==='Escape'&&toolId.value&&!(e.target as Element)?.closest('.capture-dropdown,.tool-shortcut-picker'))hide()}
onMounted(()=>{document.addEventListener('pointerover',over);document.addEventListener('pointerout',out);document.addEventListener('focusin',focus);document.addEventListener('pointerdown',down,true);document.addEventListener('keydown',key,true);window.addEventListener('resize',hide);window.addEventListener('scroll',scroll,true);window.addEventListener('blur',hide)})
onBeforeUnmount(()=>{hide();document.removeEventListener('pointerover',over);document.removeEventListener('pointerout',out);document.removeEventListener('focusin',focus);document.removeEventListener('pointerdown',down,true);document.removeEventListener('keydown',key,true);window.removeEventListener('resize',hide);window.removeEventListener('scroll',scroll,true);window.removeEventListener('blur',hide)})
</script>
<template>
 <Teleport to="body"><div v-if="toolId" ref="panel" class="tool-shortcut-popup" role="dialog" :aria-label="label+'快捷键配置'" data-tooltip-disabled :data-below="position.below" :style="{left:position.left+'px',top:position.top+'px',visibility:position.ready?'visible':'hidden'}" @pointerenter="keep" @pointerleave="leave" @pointerdown.stop @contextmenu.stop><strong>{{label}}</strong><i/><ToolShortcutPicker :key="toolId" :tool-id="toolId" @resize="place"/></div></Teleport>
</template>
