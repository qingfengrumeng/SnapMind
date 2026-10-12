<script setup lang="ts">
import {tx} from '../preferences'
import {Keyboard,RotateCcw} from 'lucide-vue-next'
import {captureShortcut,saveCaptureShortcut,shortcutFromEvent} from '../shortcut'
import {toolShortcutCatalog,toolShortcuts,normalizeToolShortcut} from '../tool-shortcuts'
import {useShortcutRecorder} from '../use-shortcut-recorder'
const {recording,starting,saving,error,saved,preview,start,stop,save,record,release}=useShortcutRecorder({
 parse:shortcutFromEvent,invalidMessage:'请使用 Ctrl、Alt 或 Win 搭配字母、数字或功能键。',
 async save(value){
  const key=normalizeToolShortcut(value.replace('Super','Meta')),owner=toolShortcutCatalog.find(t=>toolShortcuts.value[t.id]===key)
  if(owner)throw Error(`这个组合键已用于“${owner.label}”，请先修改该功能的快捷键。`)
  await saveCaptureShortcut(value)
 }
})
</script>
<template>
 <section class="shortcut-setting" aria-label="截图快捷键设置">
  <div class="shortcut-setting-heading"><Keyboard :size="17"/><strong>{{tx('截图快捷键')}}</strong><span role="status">{{saving?tx('保存中'):recording?'录制中':saved?tx('已保存'):tx('自定义')}}</span></div>
  <p>点击快捷键框，按下新的组合键即可自动保存。</p>
  <div class="shortcut-setting-controls">
   <button type="button" class="shortcut-recorder" :class="{recording}" aria-label="录制截图快捷键" :aria-pressed="recording" :aria-busy="saving||starting" :aria-describedby="recording||error?'capture-shortcut-help':undefined" @click="start" @keydown.stop="record" @keyup.stop="release" @blur="stop"><kbd>{{saving?'保存中…':starting?'准备录制…':recording?(preview?preview+' + …':'请按下组合键…'):captureShortcut}}</kbd></button>
   <button type="button" class="shortcut-reset" :disabled="saving||starting||recording||captureShortcut==='Alt+Z'" aria-label="恢复默认截图快捷键" data-tooltip="恢复默认快捷键" @click="save('Alt+Z')"><RotateCcw :size="16"/></button>
  </div>
  <p v-if="error||recording" id="capture-shortcut-help" :class="error?'shortcut-setting-error':'shortcut-setting-help'" :role="error?'alert':'status'">{{error||'按住 Ctrl、Alt 或 Win，再按字母、数字或功能键；Esc 取消。'}}</p>
 </section>
</template>
