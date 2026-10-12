<script setup lang="ts">
import {computed} from 'vue'
import {RotateCcw} from 'lucide-vue-next'
import {toolShortcutCatalog,resetToolShortcuts} from '../tool-shortcuts'
import ToolShortcutPicker from './ToolShortcutPicker.vue'
const groups=computed(()=>[...new Set(toolShortcutCatalog.map(t=>t.group))].map(name=>({name,items:toolShortcutCatalog.filter(t=>t.group===name)})))
</script>
<template>
 <section class="tool-shortcut-settings" aria-label="截图工具快捷键设置">
  <header><div><h3>工具快捷键</h3><p>点击右侧快捷键框，直接按下新的键位或组合键，自动保存。仅在截图选区内生效。</p></div><button type="button" aria-label="恢复默认工具快捷键" @click="resetToolShortcuts"><RotateCcw :size="15"/>恢复默认</button></header>
  <section v-for="group in groups" :key="group.name" class="tool-shortcut-group"><h4>{{group.name}}</h4><div v-for="item in group.items" :key="item.id" class="tool-shortcut-row"><strong>{{item.label}}</strong><ToolShortcutPicker :tool-id="item.id"/></div></section>
  <p class="tool-shortcut-note">Backspace 删除所选标注。取色时 Q 复制颜色、Shift 切换格式。输入文字或对话时不触发工具快捷键。</p>
 </section>
</template>
