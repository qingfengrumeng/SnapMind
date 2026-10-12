<script setup lang="ts">
import {computed,nextTick,watch,useId} from 'vue'
import {Keyboard,Check} from 'lucide-vue-next'
import {toolShortcuts,setToolShortcut,toolShortcutFromEvent,toolShortcutCatalog,type CaptureToolId} from '../tool-shortcuts'
import {useShortcutRecorder} from '../use-shortcut-recorder'
const props=defineProps<{toolId:CaptureToolId}>()
const emit=defineEmits<{resize:[]}>()
const helpId=useId()
const label=computed(()=>toolShortcutCatalog.find(t=>t.id===props.toolId)!.label)
const {recording,starting,saving,error,saved,preview,start,stop,record,release}=useShortcutRecorder({
 parse:toolShortcutFromEvent,save:value=>setToolShortcut(props.toolId,value),
 allowEscape:props.toolId==='cancel',invalidMessage:'请按字母、数字或功能键，也可以搭配组合键。',
 errorMessage:e=>e instanceof Error&&/[\u3400-\u9fff]/.test(e.message)&&!/[{}]/.test(e.message)?e.message:'快捷键保存失败，请重试。'
})
const displayed=computed(()=>saving.value?'保存中…':starting.value?'准备录制…':recording.value?(preview.value?preview.value+' + …':'请按键…'):toolShortcuts.value[props.toolId]?.replace('Escape','Esc').replace('Meta','Win')||'未设置')
watch([recording,starting,saving,error],async()=>{await nextTick();emit('resize')})
</script>
<template>
 <div class="tool-shortcut-picker" data-tooltip-disabled @keydown.stop>
  <div class="tool-shortcut-controls">
   <button type="button" class="tool-shortcut-record" :class="{recording}" :aria-label="label+'快捷键'" :aria-pressed="recording" :aria-busy="saving||starting" :aria-describedby="recording||error?helpId:undefined" title="点击后按下新快捷键，自动保存" @click="start" @keydown="record" @keyup="release" @blur="stop"><Check v-if="saved&&!recording" :size="16"/><Keyboard v-else :size="16"/><kbd>{{displayed}}</kbd></button>
  </div>
  <p v-if="recording||error" :id="helpId" :class="error?'tool-shortcut-error':'tool-shortcut-recording'" :role="error?'alert':'status'">{{error||(toolId==='cancel'?'按下新快捷键；点击快捷键框或其他位置取消。':'按下新快捷键；Esc 或点击其他位置取消。')}}</p>
  <span v-else-if="saved" class="shortcut-sr-status" role="status">快捷键已保存</span>
 </div>
</template>
