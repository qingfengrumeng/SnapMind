<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref,useId,watch} from 'vue'
import {CalendarDays,ChevronDown,Check} from 'lucide-vue-next'
import {tr} from '../preferences'
import {presetRange,validUsageRange,type UsageRange,type UsagePreset} from '../usage-range'
const props=defineProps<{modelValue:UsageRange}>()
const emit=defineEmits<{'update:modelValue':[range:UsageRange]}>()
const root=ref<HTMLElement>(),trigger=ref<HTMLButtonElement>(),open=ref(false),custom=ref(false),start=ref(''),end=ref(''),uid=useId()
const options=computed(()=>[
 {id:'today',label:tr('今天','今天','Today')},{id:'yesterday',label:tr('昨天','昨天','Yesterday')},
 {id:'week',label:tr('近 7 天','近 7 天','Last 7 days')},{id:'month30',label:tr('近 30 天','近 30 天','Last 30 days')},
 {id:'month',label:tr('本月','本月','This month')},{id:'lastMonth',label:tr('上月','上月','Last month')},
 {id:'custom',label:tr('自定义','自訂','Custom')}
] as {id:UsagePreset;label:string}[])
const selected=computed(()=>options.value.find(option=>option.id===props.modelValue.preset)!.label)
const valid=computed(()=>validUsageRange(start.value,end.value))
function close(focus=false){open.value=false;if(focus)trigger.value?.focus()}
function toggle(){if(open.value){close();return}start.value=props.modelValue.start;end.value=props.modelValue.end;custom.value=props.modelValue.preset==='custom';open.value=true}
function choose(id:UsagePreset){if(id==='custom'){custom.value=true;return}emit('update:modelValue',presetRange(id));close(true)}
function apply(){if(!valid.value)return;emit('update:modelValue',{preset:'custom',start:start.value,end:end.value});close(true)}
function outside(event:PointerEvent){if(open.value&&!root.value?.contains(event.target as Node))close()}
watch(()=>props.modelValue,()=>close())
onMounted(()=>document.addEventListener('pointerdown',outside))
onBeforeUnmount(()=>document.removeEventListener('pointerdown',outside))
</script>
<template>
 <div ref="root" class="usage-date-filter" @keydown.esc.stop.prevent="close(true)">
  <button ref="trigger" type="button" class="usage-date-trigger" aria-haspopup="dialog" :aria-expanded="open" :aria-controls="uid" :aria-label="tr('筛选统计时间','篩選統計時間','Filter usage dates')" @click="toggle"><CalendarDays :size="15"/><span>{{selected}}</span><ChevronDown :size="13" :class="{expanded:open}"/></button>
  <div v-if="open" :id="uid" class="usage-date-popover" role="dialog" :aria-label="tr('选择时间范围','選擇時間範圍','Select date range')">
   <div class="usage-date-presets"><button v-for="option in options" :key="option.id" type="button" :class="{selected:custom?option.id==='custom':modelValue.preset===option.id}" @click="choose(option.id)"><span>{{option.label}}</span><Check v-if="custom?option.id==='custom':modelValue.preset===option.id" :size="13"/></button></div>
   <form v-if="custom" class="usage-custom-dates" @submit.prevent="apply"><div><label>{{tr('开始日期','開始日期','Start date')}}<input v-model="start" type="date" required :max="end||undefined" :aria-label="tr('开始日期','開始日期','Start date')"/></label><label>{{tr('结束日期','結束日期','End date')}}<input v-model="end" type="date" required :min="start||undefined" :aria-label="tr('结束日期','結束日期','End date')"/></label></div><p v-if="!valid" role="alert">{{tr('请选择有效日期，最多 366 天。','請選擇有效日期，最多 366 天。','Choose valid dates, up to 366 days.')}}</p><button type="submit" :disabled="!valid">{{tr('应用时间范围','套用時間範圍','Apply range')}}</button></form>
  </div>
 </div>
</template>
