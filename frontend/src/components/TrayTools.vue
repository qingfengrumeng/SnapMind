<script setup lang="ts">
import { onMounted, onBeforeUnmount, ref } from 'vue'
import ToolMenu from './ToolMenu.vue'
import { desktop } from '../desktop'
import type { ToolAction } from '../tool-actions'
const error=ref(''),pending=ref(false)
async function action(action:ToolAction){if(pending.value)return;pending.value=true;error.value='';try{await desktop.toolAction(action)}catch(e){error.value=String(e)}finally{pending.value=false}}
function escape(event:KeyboardEvent){if(event.key==='Escape')desktop.hide()}
onMounted(()=>document.addEventListener('keydown',escape))
onBeforeUnmount(()=>document.removeEventListener('keydown',escape))
</script>
<template><nav class="tray-tools-window" aria-label="SnapMind 托盘工具" :aria-busy="pending"><ToolMenu tray @action="action"/><p v-if="error" class="tray-tools-error" role="alert">{{error}}</p></nav></template>
