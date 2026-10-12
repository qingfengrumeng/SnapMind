<script setup lang="ts">
import {computed} from 'vue'
import type {ImageToolCommand} from '../image-tool-commands'
import Icon from './Icon.vue'
const props=defineProps<{id:string;tools:ImageToolCommand[];active:string|undefined;loading:boolean;error:string;maxHeight:number}>()
const emit=defineEmits<{choose:[tool:ImageToolCommand];hover:[name:string];retry:[]}>()
const groups=computed(()=>Array.from(new Set(props.tools.map(t=>t.group))).map(title=>({title,tools:props.tools.filter(t=>t.group===title)})))
</script>
<template>
 <aside class="image-tool-menu" aria-label="图片功能列表" :style="{maxHeight:maxHeight+'px'}" @pointerdown.stop @contextmenu.stop>
  <div v-if="loading" class="image-tool-menu-message" role="status"><Icon name="loading" :size="18"/>正在加载功能</div>
  <div v-else-if="error" class="image-tool-menu-message" role="alert"><span>{{error}}</span><button type="button" @click="emit('retry')">重试</button></div>
  <div v-else :id="id" class="image-tool-menu-list" role="listbox" aria-label="可调用的图片功能">
   <p v-if="!tools.length" class="image-tool-menu-empty">没有匹配的功能，试试“翻译”“表格”或“标注”</p>
   <section v-for="group in groups" :key="group.title" role="group" :aria-label="group.title"><h4>{{group.title}} <span>{{group.tools.length}}</span></h4>
    <button v-for="tool in group.tools" :id="id+'-'+tool.name" :key="tool.name" type="button" role="option" :aria-selected="active===tool.name" :class="{active:active===tool.name}" :data-tool="tool.name" @pointerdown.prevent @mouseenter="emit('hover',tool.name)" @click="emit('choose',tool)"><span class="image-tool-menu-icon"><Icon :name="tool.icon" :size="20"/></span><span class="image-tool-menu-copy"><strong>{{tool.label}}</strong><small>{{tool.summary||tool.description}}</small></span><Icon v-if="active===tool.name" name="right" :size="15"/></button>
   </section>
  </div>
  <footer><span>输入 / 后搜索功能</span><span>↑ ↓ 选择 · Enter 确认 · Esc 收起</span></footer>
 </aside>
</template>
