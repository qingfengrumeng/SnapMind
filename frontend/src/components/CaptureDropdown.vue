<script setup lang="ts">
import {computed,nextTick,onBeforeUnmount,onMounted,ref} from 'vue'
import {Check,ChevronDown} from 'lucide-vue-next'
type Option={value:string;label:string;disabled?:boolean}
const props=defineProps<{modelValue:string;label:string;options:Option[];kind?:'arrow'|'line'|'shortcut'|'language'}>()
const emit=defineEmits<{'update:modelValue':[value:string]}>()
const trigger=ref<HTMLButtonElement>(),menu=ref<HTMLElement>(),open=ref(false),focused=ref(0)
const selected=computed(()=>props.options.find(o=>o.value===props.modelValue))
const position=ref({left:'0px',top:'0px',maxHeight:'280px'})
function place(){const r=trigger.value?.getBoundingClientRect();if(!r)return;const width=props.kind==='shortcut'?208:props.kind==='language'?144:180,height=Math.min(props.kind==='shortcut'?268:props.kind==='language'?props.options.length*35+40:props.options.length*41+52,280),below=innerHeight-r.bottom-20;const top=below>=100?r.bottom+8:Math.max(12,r.top-height-8),left=props.kind==='language'?r.left+(r.width-width)/2:r.left;position.value={left:Math.max(12,Math.min(left,innerWidth-width-12))+'px',top:top+'px',maxHeight:Math.max(80,Math.min(height,innerHeight-top-12))+'px'}}
function close(restore=false){open.value=false;if(restore)trigger.value?.focus({preventScroll:true})}
async function toggle(){if(open.value){close();return}focused.value=Math.max(0,props.options.findIndex(o=>o.value===props.modelValue));place();open.value=true;await nextTick();menu.value?.focus({preventScroll:true});menu.value?.querySelector('[aria-selected="true"]')?.scrollIntoView({block:'nearest'})}
function choose(index:number){const option=props.options[index];if(!option||option.disabled)return;emit('update:modelValue',option.value);close(true)}
function key(e:KeyboardEvent){if(['Escape','Enter',' ','ArrowDown','ArrowUp','ArrowLeft','ArrowRight','Home','End','Tab'].includes(e.key))e.stopPropagation();if(e.key==='Escape'){e.preventDefault();close(true);return}if(e.key==='Tab'){close(true);return}if(e.key==='Enter'||e.key===' '){e.preventDefault();choose(focused.value);return}
 const enabled=props.options.map((o,i)=>o.disabled?-1:i).filter(i=>i>=0);if(!enabled.length)return
 if(e.key==='Home'||e.key==='End'){e.preventDefault();focused.value=e.key==='Home'?enabled[0]!:enabled.at(-1)!}
 else if(e.key.startsWith('Arrow')){e.preventDefault();const direction=['ArrowDown','ArrowRight'].includes(e.key)?1:-1,index=enabled.indexOf(focused.value);focused.value=enabled[(index+direction+enabled.length)%enabled.length]!}
 else if(props.kind==='shortcut'&&/^[a-z0-9]$/i.test(e.key)){e.preventDefault();const index=props.options.findIndex(o=>o.value===e.key.toUpperCase()&&!o.disabled);if(index>=0)focused.value=index}
 nextTick(()=>menu.value?.querySelector('.keyboard-focused')?.scrollIntoView({block:'nearest'}))
}
function outside(e:PointerEvent){if(!trigger.value?.contains(e.target as Node)&&!menu.value?.contains(e.target as Node))close()}
onMounted(()=>{document.addEventListener('pointerdown',outside,true);window.addEventListener('resize',place);window.addEventListener('blur',()=>close(),{signal:controller.signal})})
const controller=new AbortController()
onBeforeUnmount(()=>{controller.abort();document.removeEventListener('pointerdown',outside,true);window.removeEventListener('resize',place)})
</script>
<template>
 <div class="capture-dropdown" :class="{'is-open':open,'shortcut-dropdown':kind==='shortcut','language-dropdown':kind==='language'}">
  <button ref="trigger" type="button" class="capture-dropdown-trigger" :aria-label="label" aria-haspopup="listbox" :aria-expanded="open" @click="toggle" @keydown.down.prevent="!open&&toggle()">
   <svg v-if="kind==='arrow'||kind==='line'" class="dropdown-preview" width="25" height="18" viewBox="0 0 28 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
    <path d="M3 9h22" :stroke-dasharray="kind==='line'?(modelValue==='dashed'?'5 4':modelValue==='dotted'?'1 4':undefined):undefined"/>
    <path v-if="kind==='arrow'&&modelValue==='outline'" d="m19 4 6 5-6 5"/><path v-if="kind==='arrow'&&modelValue==='solid'" d="m18 4 8 5-8 5z" fill="currentColor" stroke="none"/><path v-if="kind==='arrow'&&modelValue==='double'" d="m9 4-6 5 6 5m10-10 6 5-6 5"/>
   </svg>
   <span>{{selected?.label||modelValue}}</span><ChevronDown :size="15" class="dropdown-chevron"/>
  </button>
  <Teleport to="body">
   <div v-if="open" ref="menu" class="capture-dropdown capture-dropdown-menu" :class="{'shortcut-menu':kind==='shortcut','language-menu':kind==='language'}" :style="position" role="listbox" :aria-label="label+'选项'" tabindex="-1" @pointerdown.stop @contextmenu.stop.prevent @keydown="key">
    <div class="dropdown-menu-heading">{{label}}</div>
    <div class="dropdown-option-list">
     <button v-for="(option,index) in options" :key="option.value" type="button" role="option" :aria-selected="modelValue===option.value" :aria-disabled="option.disabled||undefined" :disabled="option.disabled" :class="{selected:modelValue===option.value,'keyboard-focused':focused===index,'shortcut-chord':kind==='shortcut'&&option.value.includes('+')}" @pointermove="focused=index" @click="choose(index)">
      <svg v-if="kind==='arrow'||kind==='line'" class="dropdown-preview" width="28" height="18" viewBox="0 0 28 18" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round">
       <path d="M3 9h22" :stroke-dasharray="kind==='line'?(option.value==='dashed'?'5 4':option.value==='dotted'?'1 4':undefined):undefined"/><path v-if="kind==='arrow'&&option.value==='outline'" d="m19 4 6 5-6 5"/><path v-if="kind==='arrow'&&option.value==='solid'" d="m18 4 8 5-8 5z" fill="currentColor" stroke="none"/><path v-if="kind==='arrow'&&option.value==='double'" d="m9 4-6 5 6 5m10-10 6 5-6 5"/>
      </svg>
      <span>{{option.label}}</span><Check v-if="modelValue===option.value&&kind!=='shortcut'" :size="16" class="dropdown-selected-check"/>
     </button>
    </div>
   </div>
  </Teleport>
 </div>
</template>
