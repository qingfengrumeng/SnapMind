<script setup lang="ts">
import {computed,onBeforeUnmount,onMounted,ref,useId,watch} from 'vue'
import {tr} from '../preferences'
import type {UsagePoint} from '../api'
import {usageTokens} from '../usage-tokens'
const props=withDefaults(defineProps<{points:UsagePoint[];metric:'requests'|'tokens';title:string;total:number;granularity:'hour'|'day';chartType?:'bar'|'line'}>(),{chartType:'bar'})
const root=ref<HTMLElement>(),width=ref(360),selected=ref<number>(),uid='usage-'+useId().replace(/[^a-zA-Z0-9-]/g,'')
let observer:ResizeObserver|undefined
const left=48,right=15,top=17,bottom=162,height=192
const plotWidth=computed(()=>Math.max(120,width.value-left-right))
const values=computed(()=>props.points.map(point=>props.metric==='requests'?point.requests:usageTokens(point).total))
const series=computed(()=>props.metric==='requests'?[{id:'requests',values:props.points.map(point=>point.requests)}]:[
 {id:'cached',values:props.points.map(point=>usageTokens(point).cached)},
 {id:'uncached',values:props.points.map(point=>usageTokens(point).uncached)},
 {id:'output',values:props.points.map(point=>usageTokens(point).output)}
])
const maximum=computed(()=>{
 const plotted=props.chartType==='line'?series.value.flatMap(line=>line.values):values.value
 const max=Math.max(...plotted,props.metric==='requests'?2:1),unit=10**Math.floor(Math.log10(max)),step=[1,2,5,10].find(value=>value*unit>=max)||10
 return step*unit
})
const ticks=computed(()=>[maximum.value,maximum.value/2,0])
const labelIndices=computed(()=>{const count=Math.min(props.points.length,width.value<350?3:4);return [...new Set(Array.from({length:count},(_,i)=>Math.round(i*(props.points.length-1)/Math.max(1,count-1))))]})
const barWidth=computed(()=>Math.max(1,plotWidth.value/Math.max(1,props.points.length)*.62))
const x=(index:number)=>left+(index+.5)*plotWidth.value/Math.max(1,props.points.length)
const y=(value:number)=>bottom-(bottom-top)*value/maximum.value
const lines=computed(()=>series.value.map(line=>({...line,points:line.values.map((value,index)=>`${x(index)},${y(value)}`).join(' ')})))
function short(value:number){if(value>=1e6)return +(value/1e6).toFixed(1)+'M';if(value>=1e3)return +(value/1e3).toFixed(1)+'K';return Number.isInteger(value)?String(value):value.toFixed(1)}
const point=computed(()=>selected.value===undefined?undefined:props.points[selected.value])
const tooltipStyle=computed(()=>({left:Math.max(6,Math.min(width.value-248,selected.value===undefined?0:x(selected.value)-118))+'px'}))
const format=(value:number|null|undefined)=>(value??0).toLocaleString()
function segments(point:UsagePoint){const tokens=usageTokens(point);return [{id:'cached',value:tokens.cached},{id:'uncached',value:tokens.uncached},{id:'output',value:tokens.output}].map((segment,index,all)=>({...segment,base:all.slice(0,index).reduce((sum,item)=>sum+item.value,0)}))}
function move(event:PointerEvent){const rect=(event.currentTarget as SVGElement).getBoundingClientRect();const px=(event.clientX-rect.left)*width.value/rect.width;if(px<left||px>width.value-right){selected.value=undefined;return}selected.value=Math.max(0,Math.min(props.points.length-1,Math.floor((px-left)/plotWidth.value*props.points.length)))}
function keyboard(event:KeyboardEvent){if(!props.points.length)return;if(event.key==='Escape'){event.stopPropagation();selected.value=undefined;return}if(!['ArrowLeft','ArrowRight','Home','End'].includes(event.key))return;event.preventDefault();selected.value=event.key==='Home'?0:event.key==='End'?props.points.length-1:Math.max(0,Math.min(props.points.length-1,(selected.value??-1)+(event.key==='ArrowLeft'?-1:1)))}
onMounted(()=>{observer=new ResizeObserver(entries=>{width.value=Math.max(240,entries[0]!.contentRect.width)});if(root.value)observer.observe(root.value)})
onBeforeUnmount(()=>observer?.disconnect())
watch(()=>props.points,()=>{selected.value=undefined})
</script>
<template>
 <article class="usage-chart-card" :data-metric="metric" :data-chart-type="chartType">
  <header><h5>{{title}}</h5><strong>{{total.toLocaleString()}}</strong></header>
  <div v-if="metric==='tokens'" class="usage-chart-legend"><span><i class="cached"/>{{tr('输入（命中缓存）','輸入（命中快取）','Input (cached)')}}</span><span><i class="uncached"/>{{tr('输入（未命中缓存）','輸入（未命中快取）','Input (uncached)')}}</span><span><i class="output"/>{{tr('输出','輸出','Output')}}</span></div>
  <div v-else class="usage-chart-legend"><span>{{granularity==='hour'?tr('每小时请求次数','每小時請求次數','Requests per hour'):tr('每日请求次数','每日請求次數','Requests per day')}}</span></div>
  <div ref="root" class="usage-chart-plot" tabindex="0" :aria-label="title+tr('，使用左右方向键查看数据','，使用左右方向鍵查看資料',', use arrow keys to explore')" @keydown="keyboard" @blur="selected=undefined">
   <svg :viewBox="'0 0 '+width+' '+height" :height="height" width="100%" role="img" :aria-label="title+' '+total.toLocaleString()" @pointermove="move" @pointerleave="selected=undefined" @pointerdown="move">
    <defs><linearGradient :id="uid" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="var(--chart-request-top)"/><stop offset="1" stop-color="var(--chart-request-bottom)"/></linearGradient></defs>
    <g v-for="tick in ticks" :key="tick"><line :x1="left" :x2="width-right" :y1="y(tick)" :y2="y(tick)" class="usage-chart-gridline"/><text :x="left-9" :y="y(tick)+3" text-anchor="end" class="usage-chart-label">{{short(tick)}}</text></g>
    <rect v-if="selected!==undefined&&chartType==='bar'" :x="x(selected)-plotWidth/points.length/2" :y="top" :width="plotWidth/points.length" :height="bottom-top" class="usage-chart-selection" rx="3"/>
    <template v-if="chartType==='bar'"><g v-for="(p,index) in points" :key="p.key"><rect v-if="metric==='requests'&&p.requests" :x="x(index)-barWidth/2" :y="y(p.requests)" :width="barWidth" :height="bottom-y(p.requests)" :fill="'url(#'+uid+')'" rx="3"/><template v-else-if="metric==='tokens'"><rect v-for="segment in segments(p).filter(item=>item.value>0)" :key="segment.id" :x="x(index)-barWidth/2" :y="y(segment.base+segment.value)" :width="barWidth" :height="y(segment.base)-y(segment.base+segment.value)" :class="'usage-token-bar '+segment.id"/></template></g></template>
    <g v-else class="usage-line-series"><polyline v-for="line in lines" :key="line.id" :points="line.points" :class="'usage-trend-line '+line.id" :data-series="line.id"/><line v-if="selected!==undefined" :x1="x(selected)" :x2="x(selected)" :y1="top" :y2="bottom" class="usage-line-guide"/><template v-if="selected!==undefined"><circle v-for="line in lines" :key="line.id" :cx="x(selected)" :cy="y(line.values[selected]??0)" r="3.5" :class="'usage-line-point '+line.id"/></template></g>
    <text v-for="index in labelIndices" :key="index" :x="x(index)" :y="bottom+20" text-anchor="middle" class="usage-chart-label">{{points[index]?.label}}</text>
   </svg>
   <span v-if="!values.some(value=>value>0)" class="usage-chart-no-data">{{tr('暂无数据','暫無資料','No data')}}</span>
   <div v-if="point" class="usage-chart-tooltip" :style="tooltipStyle" role="status"><strong>{{point.key.replace('T',' ')}}</strong><template v-if="metric==='requests'"><p><span>{{tr('请求次数','請求次數','Requests')}}</span><b>{{format(point.requests)}}</b></p></template><template v-else><p><span><i class="cached"/>{{tr('输入（命中缓存）','輸入（命中快取）','Input (cached)')}}</span><b>{{format(usageTokens(point).cached)}}</b></p><p><span><i class="uncached"/>{{tr('输入（未命中缓存）','輸入（未命中快取）','Input (uncached)')}}</span><b>{{format(usageTokens(point).uncached)}}</b></p><p><span><i class="output"/>{{tr('输出','輸出','Output')}}</span><b>{{format(usageTokens(point).output)}}</b></p><p class="usage-tooltip-total"><span>{{tr('总 Token','總 Token','Total tokens')}}</span><b>{{format(usageTokens(point).total)}}</b></p></template></div>
  </div>
 </article>
</template>
