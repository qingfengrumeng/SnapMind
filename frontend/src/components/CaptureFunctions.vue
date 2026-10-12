<script setup lang="ts">
import {computed,ref} from 'vue'
import {Search,Keyboard,ChevronRight,SlidersHorizontal} from 'lucide-vue-next'
import {tr} from '../preferences'
import {toolShortcuts} from '../tool-shortcuts'
import {captureFunctionGuide,captureFunctionGroups,type GuideText} from '../capture-function-guide'
import CaptureFunctionIcon from './CaptureFunctionIcon.vue'
const emit=defineEmits<{'configure-shortcuts':[]}>()
const query=ref(''),category=ref('all')
const localize=(text:GuideText)=>tr(...text)
const groups=computed(()=>captureFunctionGroups.filter(group=>category.value==='all'||category.value===group.id).map(group=>({...group,items:captureFunctionGuide.filter(item=>{
 if(item.group!==group.id)return false
 const terms=[item.label,...item.name,...item.description,...item.steps,toolShortcuts.value[item.id]].join(' ').toLowerCase()
 return query.value.trim().toLowerCase().split(/\s+/).every(word=>terms.includes(word))
})})).filter(group=>group.items.length))
const count=computed(()=>groups.value.reduce((total,group)=>total+group.items.length,0))
function keys(value:string){return value.split('+').map(key=>key==='Escape'?'Esc':key==='Meta'?'Win':key)}
</script>
<template>
 <div class="capture-functions">
  <header class="functions-heading"><div><h3>{{tr('截图功能指南','擷取功能指南','Capture feature guide')}}</h3><p>{{tr('从标注到 AI 对话，了解工具栏中每个按钮的用途与操作。','從標註到 AI 對話，了解工具列中每個按鈕的用途與操作。','Explore each toolbar button, from drawing to AI chat.')}}</p></div><button type="button" class="functions-shortcut-link" @click="emit('configure-shortcuts')"><SlidersHorizontal :size="14"/>{{tr('配置快捷键','設定快捷鍵','Configure shortcuts')}}<ChevronRight :size="13"/></button></header>
  <div class="functions-search"><Search :size="16" aria-hidden="true"/><input v-model="query" type="search" :aria-label="tr('搜索功能','搜尋功能','Search features')" :placeholder="tr('搜索功能名称、用途或快捷键','搜尋功能名稱、用途或快捷鍵','Search names, uses or shortcuts')"/><span>{{count}} / {{captureFunctionGuide.length}}</span></div>
  <div class="functions-filters" role="group" :aria-label="tr('功能分类','功能分類','Feature categories')"><button type="button" :aria-pressed="category==='all'" @click="category='all'">{{tr('全部','全部','All')}}</button><button v-for="group in captureFunctionGroups" :key="group.id" type="button" :aria-pressed="category===group.id" @click="category=group.id">{{localize(group.title)}}</button></div>
  <p class="functions-key-note"><Keyboard :size="13" aria-hidden="true"/>{{tr('显示当前快捷键，仅在截图选区内使用；输入文字或对话时不触发。','顯示目前快捷鍵，僅在擷取選取區域內使用；輸入文字或對話時不會觸發。','Shortcuts reflect your settings and work in the capture area, except while typing text or chatting.')}}</p>
  <section v-for="group in groups" :key="group.id" class="functions-group" :aria-label="localize(group.title)">
   <header class="functions-group-heading"><h4>{{localize(group.title)}}<span>{{group.items.length}}</span></h4><p>{{localize(group.description)}}</p></header>
   <div class="functions-grid">
    <article v-for="item in group.items" :key="item.id" class="function-card" :data-function-id="item.id">
     <header><span class="function-icon"><CaptureFunctionIcon :tool="item.id"/></span><h5>{{tr(item.label,item.name[0],item.name[1])}}</h5><span class="function-shortcut" :aria-label="tr('当前快捷键：','目前快捷鍵：','Current shortcut: ')+(toolShortcuts[item.id]||tr('未设置','未設定','Not set'))"><template v-if="toolShortcuts[item.id]"><template v-for="(key,index) in keys(toolShortcuts[item.id])" :key="index"><i v-if="index" aria-hidden="true">+</i><kbd>{{key}}</kbd></template></template><span v-else>{{tr('未设置','未設定','Not set')}}</span></span></header>
     <p class="function-description">{{localize(item.description)}}</p>
     <div class="function-instructions"><span>{{tr('使用方法','使用方式','How to use')}}</span><p>{{localize(item.steps)}}</p></div>
    </article>
   </div>
  </section>
  <div v-if="!count" class="functions-empty" role="status"><Search :size="24"/><strong>{{tr('没有找到相关功能','找不到相關功能','No matching features')}}</strong><p>{{tr('试试其他关键词，或切换到“全部”。','試試其他關鍵字，或切換至「全部」。','Try another search or select All.')}}</p></div>
 </div>
</template>
<style scoped>
.capture-functions{padding-top:18px;color:var(--ink-soft)}
.functions-heading{display:flex;align-items:flex-start;justify-content:space-between;gap:16px;margin-bottom:17px}
.functions-heading h3{margin:0 0 7px;font-size:17px;font-weight:600;color:var(--ink)}
.functions-heading p{margin:0;font-size:13px;line-height:1.7;color:var(--ink-faint)}
.capture-functions .functions-shortcut-link{display:flex;align-items:center;justify-content:center;gap:6px;flex-shrink:0;width:auto;height:33px;margin:0;padding:0 10px;border:1px solid var(--line-strong);border-radius:8px;background:var(--surface);color:var(--ink-soft);font-size:12px;white-space:nowrap}
.capture-functions .functions-shortcut-link:hover{border-color:var(--accent-soft);color:var(--accent);background:var(--accent-wash)}
.functions-search{display:flex;align-items:center;gap:9px;padding:0 12px;min-height:40px;border:1px solid var(--line-strong);border-radius:10px;background:var(--surface);color:var(--ink-faint)}
.functions-search:focus-within{border-color:var(--accent);box-shadow:0 0 0 3px var(--accent-glow)}
.functions-search input{width:100%;min-width:0;height:38px;padding:0;border:0;border-radius:0;outline:none;box-shadow:none;background:transparent;color:var(--ink);font:inherit;font-size:13px}
.functions-search input::placeholder{color:var(--ink-faint)}
.functions-search>span{font-family:var(--font-mono);font-size:11px;white-space:nowrap}
.functions-filters{display:flex;flex-wrap:wrap;gap:6px;margin:12px 0}
.capture-functions .functions-filters button{width:auto;height:29px;justify-content:center;padding:0 11px;margin:0;border:1px solid transparent;border-radius:7px;background:transparent;color:var(--ink-faint);font-size:12px}
.capture-functions .functions-filters button[aria-pressed="true"]{background:var(--accent-wash);border-color:var(--accent-glow);color:var(--accent);font-weight:500}
.capture-functions .functions-filters button:hover{background:var(--accent-wash);color:var(--accent)}
.functions-key-note{display:flex;align-items:flex-start;gap:7px;margin:0 0 21px;font-size:11px;line-height:1.8;color:var(--ink-faint)}
.functions-key-note svg{flex-shrink:0;margin-top:2px}
.functions-group+.functions-group{margin-top:25px}
.functions-group-heading{margin:0 0 12px}
.functions-group-heading h4{display:flex;align-items:center;gap:8px;font-size:14px;font-weight:600;margin:0 0 5px;color:var(--ink)}
.functions-group-heading h4::before{content:'';width:3px;height:15px;border-radius:2px;background:var(--accent)}
.functions-group-heading h4>span{font-size:11px;color:var(--ink-faint);font-weight:400}
.functions-group-heading>p{margin:0 0 0 11px;font-size:12px;line-height:1.6;color:var(--ink-faint)}
.functions-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px}
.function-card{min-width:0;padding:15px;border:1px solid var(--line);border-radius:12px;background:var(--surface)}
.function-card>header{display:flex;align-items:center;flex-wrap:wrap;gap:9px;min-height:36px}
.function-icon{display:flex;align-items:center;justify-content:center;width:36px;height:36px;flex-shrink:0;border:1px solid var(--accent-glow);border-radius:10px;background:var(--accent-wash);color:var(--accent)}
.function-icon svg{color:inherit}
.function-card h5{margin:0;font-size:13px;font-weight:600;color:var(--ink);line-height:1.5}
.function-shortcut{display:flex;align-items:center;flex-wrap:wrap;gap:3px;margin-left:auto;padding:4px 6px;border:1px solid var(--line);border-radius:6px;background:var(--paper);color:var(--ink-soft);font-size:11px;line-height:1.5}
.function-shortcut kbd{padding:0;font-family:var(--font-mono);font-size:11px;white-space:nowrap}
.function-shortcut i{font-style:normal;color:var(--ink-faint)}
.function-description{font-size:13px;line-height:1.8;margin:12px 0;color:var(--ink-soft)}
.function-instructions{padding:10px 11px;border-radius:8px;background:var(--paper)}
.function-instructions>span{display:block;margin-bottom:4px;font-size:11px;font-weight:500;color:var(--accent)}
.function-instructions p{margin:0;font-size:12px;line-height:1.8;color:var(--ink-faint)}
.functions-empty{display:flex;flex-direction:column;align-items:center;gap:9px;padding:38px 16px;border:1px dashed var(--line-strong);border-radius:12px;text-align:center;color:var(--ink-faint)}
.functions-empty svg{color:var(--accent-soft)}
.functions-empty strong{font-size:14px;color:var(--ink-soft)}
.functions-empty p{margin:0;font-size:12px;line-height:1.7}
.capture-functions button:focus-visible{outline:2px solid var(--accent);outline-offset:2px}
@container(max-width:639px){.functions-grid{grid-template-columns:1fr}.functions-heading{flex-direction:column;gap:10px}.function-card{padding:14px}.functions-search>span{font-size:10px}}
</style>
