<script setup lang="ts">
import {ref,onMounted,onBeforeUnmount} from 'vue'
import type {TextAttachment} from '../types'
import Icon from './Icon.vue'
defineProps<{attachment:TextAttachment}>()
const emit=defineEmits<{close:[]}>(),dialog=ref<HTMLElement>()
let previousFocus:HTMLElement|null=null
function key(e:KeyboardEvent){
 if(e.key==='Escape'){e.preventDefault();emit('close')}
 if(e.key==='Tab'){const targets=Array.from(dialog.value?.querySelectorAll<HTMLElement>('button,[tabindex="0"]')||[]),first=targets[0],last=targets.at(-1);if(e.shiftKey&&document.activeElement===first){e.preventDefault();last?.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first?.focus()}}
}
onMounted(()=>{previousFocus=document.activeElement as HTMLElement;dialog.value?.querySelector<HTMLButtonElement>('button')?.focus()})
onBeforeUnmount(()=>previousFocus?.focus())
</script>
<template>
 <Teleport to="body"><div class="image-chat-lightbox text-attachment-lightbox" @pointerdown.self="emit('close')" @pointerdown.stop @contextmenu.stop @wheel.stop @keydown.stop="key"><section ref="dialog" class="image-chat-lightbox-dialog" role="dialog" aria-modal="true" :aria-label="'文本预览 '+attachment.name"><header><Icon name="file" :size="21"/><strong>{{attachment.name}}</strong><button type="button" aria-label="关闭文本预览" @click="emit('close')"><Icon name="close" :size="23"/></button></header><pre class="text-attachment-content" tabindex="0">{{attachment.content}}</pre></section></div></Teleport>
</template>
