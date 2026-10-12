<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref,useId,watch} from 'vue'
import {Check,ChevronDown,Search} from 'lucide-vue-next'
import {tr} from '../preferences'
const props=defineProps<{modelValue:string;options:string[];label:string;id:string;disabled?:boolean;labels?:Record<string,string>;descriptions?:Record<string,string>;searchLabel?:string;allowCustom?:boolean}>()
const emit=defineEmits<{'update:modelValue':[value:string]}>()
const uid=useId(),trigger=ref<HTMLButtonElement>(),menu=ref<HTMLElement>(),search=ref<HTMLInputElement>(),open=ref(false),query=ref(''),focused=ref(0)
const filtered=computed(()=>{const q=query.value.trim().toLowerCase(),names=props.options.filter(name=>[name,props.labels?.[name],props.descriptions?.[name]].some(v=>v?.toLowerCase().includes(q)));if(props.allowCustom&&query.value.trim()&&!props.options.includes(query.value.trim()))names.push(query.value.trim());return names})
function display(name:string){return props.labels?.[name]||name}
const position=ref({left:'0px',top:'0px',width:'0px',maxHeight:'320px'})
function place(){
 const r=trigger.value?.getBoundingClientRect();if(!r)return
 if(r.bottom<0||r.top>innerHeight){close();return}
 const width=Math.min(r.width,innerWidth-24),wanted=Math.min(320,70+filtered.value.length*(props.descriptions?54:36)),below=innerHeight-r.bottom-20,above=r.top-20,down=below>=wanted||below>=above,space=down?below:above,height=Math.min(wanted,Math.max(80,space))
 position.value={left:Math.max(12,Math.min(r.left,innerWidth-width-12))+'px',top:Math.max(12,down?r.bottom+7:r.top-height-7)+'px',width:width+'px',maxHeight:Math.min(height,innerHeight-24)+'px'}
}
function close(restore=false){open.value=false;if(restore)trigger.value?.focus({preventScroll:true})}
async function toggle(){if(open.value){close();return}if(props.disabled)return;query.value='';focused.value=Math.max(0,props.options.indexOf(props.modelValue));place();open.value=true;await nextTick();search.value?.focus({preventScroll:true});reveal()}
function reveal(){menu.value?.querySelector('[data-focused="true"]')?.scrollIntoView({block:'nearest'})}
function choose(name:string){if(props.disabled)return;emit('update:modelValue',name);close(true)}
function key(e:KeyboardEvent){
 if(e.isComposing||e.keyCode===229)return
 if(e.key==='Escape'){e.preventDefault();e.stopPropagation();close(true);return}
 if(e.key==='Tab'&&!menu.value?.querySelector('[data-option-action]')){close(true);return}
 if(['ArrowDown','ArrowUp','Enter'].includes(e.key)){e.preventDefault();e.stopPropagation();if(!filtered.value.length)return;if(e.key==='Enter'){choose(filtered.value[focused.value]!);return}focused.value=(focused.value+(e.key==='ArrowDown'?1:-1)+filtered.value.length)%filtered.value.length;nextTick(reveal)}
}
function outside(e:PointerEvent){if(!trigger.value?.contains(e.target as Node)&&!menu.value?.contains(e.target as Node))close()}
function scroll(e:Event){if(menu.value?.contains(e.target as Node))return;if(open.value)place()}
watch(query,()=>{focused.value=0;nextTick(()=>{place();reveal()})})
watch(()=>props.disabled,value=>{if(value)close()})
onMounted(()=>{document.addEventListener('pointerdown',outside,true);window.addEventListener('scroll',scroll,true);window.addEventListener('resize',place);window.addEventListener('blur',blur)})
function blur(){close()}
onBeforeUnmount(()=>{document.removeEventListener('pointerdown',outside,true);window.removeEventListener('scroll',scroll,true);window.removeEventListener('resize',place);window.removeEventListener('blur',blur)})
</script>
<template>
 <div class="profile-model-select" data-tooltip-disabled>
  <button :id="id" ref="trigger" type="button" class="profile-model-trigger" role="combobox" :aria-label="label" aria-haspopup="listbox" :aria-expanded="open" :aria-controls="uid+'-list'" :disabled="disabled" :class="{'is-open':open,'is-empty':!modelValue}" @click="toggle" @keydown.down.prevent="!open&&toggle()" @keydown.up.prevent="!open&&toggle()"><span>{{display(modelValue)||tr('请选择模型','請選擇模型','Choose a model')}}</span><ChevronDown :size="16"/></button>
  <Teleport to="body">
   <div v-if="open" ref="menu" class="profile-model-menu" :style="position" data-tooltip-disabled @keydown="key" @focusout="e=>{if(e.relatedTarget&&!menu?.contains(e.relatedTarget as Node))close()}">
    <div class="profile-model-search"><Search :size="15"/><input ref="search" v-model="query" type="search" :aria-label="searchLabel||tr('搜索模型','搜尋模型','Search models')" :placeholder="searchLabel||tr('搜索模型名称…','搜尋模型名稱…','Search model names…')" autocomplete="off" spellcheck="false" :aria-controls="uid+'-list'" :aria-activedescendant="filtered.length?uid+'-option-'+focused:undefined"/></div>
    <div :id="uid+'-list'" class="profile-model-options" role="listbox" :aria-label="label+tr('选项','選項',' options')">
     <template v-for="(name,index) in filtered" :key="name">
      <button v-if="!$slots.action" :id="uid+'-option-'+index" type="button" role="option" :aria-selected="name===modelValue" :data-focused="index===focused" :class="{selected:name===modelValue}" tabindex="-1" @pointermove="focused=index" @click="choose(name)"><span>{{display(name)}}</span><Check v-if="name===modelValue" :size="16"/></button>
      <div v-else :id="uid+'-option-'+index" class="profile-model-option-action" role="option" :aria-selected="name===modelValue" :data-focused="index===focused" :class="{selected:name===modelValue}" @pointermove="focused=index">
       <button type="button" class="profile-option-choice" tabindex="-1" @click="choose(name)"><span>{{display(name)}}<small v-if="descriptions?.[name]">{{descriptions[name]}}</small><small v-else-if="display(name)!==name">{{name}}</small></span><Check v-if="name===modelValue" :size="16"/></button>
       <slot name="action" :option="name"/>
      </div>
     </template>
    </div>
    <p v-if="!filtered.length" class="profile-model-empty" role="status">{{searchLabel?'没有匹配的选项':tr('没有匹配的模型','沒有符合的模型','No matching models')}}</p>
   </div>
  </Teleport>
 </div>
</template>
