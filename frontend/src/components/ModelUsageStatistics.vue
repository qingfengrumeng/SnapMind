<script setup lang="ts">
import {computed,onBeforeUnmount,ref,watch} from 'vue'
import {RefreshCw,Download,BotMessageSquare,ScanText,Activity,ArrowDownToLine,DatabaseZap,ArrowUpFromLine,Sigma,Layers} from 'lucide-vue-next'
import {tr} from '../preferences'
import {api,type UsageAnalytics,type UsageKind} from '../api'
import {presetRange,type UsageRange} from '../usage-range'
import {downloadUsage} from '../usage-export'
import {usageTokens} from '../usage-tokens'
import UsageDateFilter from './UsageDateFilter.vue'
import UsageTrendChart from './UsageTrendChart.vue'
import '../usage-dashboard.css'
const kind=ref<UsageKind>('llm'),ranges=ref<Record<UsageKind,UsageRange>>({llm:presetRange('week'),ocr:presetRange('week')}),data=ref<Partial<Record<UsageKind,UsageAnalytics>>>({}),loading=ref(false),error=ref(''),exporting=ref(false),exportMessage=ref('')
let controller:AbortController|undefined,generation=0
let exportNoticeTimer:ReturnType<typeof setTimeout>|undefined
const range=computed(()=>ranges.value[kind.value])
const usage=computed(()=>{const value=data.value[kind.value];return value?.range.start===range.value.start&&value.range.end===range.value.end?value:undefined})
const format=(value:number|null|undefined)=>(value??0).toLocaleString()
const rangeLabel=computed(()=>(usage.value?.range.start||range.value.start).replaceAll('-','.')+' — '+(usage.value?.range.end||range.value.end).replaceAll('-','.'))
const metrics=computed(()=>kind.value==='llm'?[
 {id:'requests',icon:Activity,label:tr('请求次数','請求次數','Requests'),value:usage.value?.summary.requests},
 {id:'input',icon:ArrowDownToLine,label:tr('输入 Token','輸入 Token','Input tokens'),value:usage.value?.summary.inputTokens},
 {id:'cached',icon:DatabaseZap,label:tr('缓存命中 Token','快取命中 Token','Cached input tokens'),value:usage.value?.summary.cachedInputTokens},
 {id:'output',icon:ArrowUpFromLine,label:tr('输出 Token','輸出 Token','Output tokens'),value:usage.value?.summary.outputTokens},
 {id:'total',icon:Sigma,label:tr('总 Token','總 Token','Total tokens'),value:usage.value?.summary.totalTokens}
]:[{id:'requests',icon:ScanText,label:tr('调用次数','呼叫次數','Requests'),value:usage.value?.summary.requests},{id:'models',icon:Layers,label:tr('使用模型数','使用模型數','Models used'),value:usage.value?.models.length}])
async function load(){
 controller?.abort();controller=new AbortController();const request=controller,version=++generation,target=kind.value,selected={...range.value}
 loading.value=true;error.value='';exportMessage.value=''
 try{const result=await api.usageAnalytics(target,selected.start,selected.end,AbortSignal.any([request.signal,AbortSignal.timeout(10000)]));if(version===generation)data.value={...data.value,[target]:result}}
 catch{if(version===generation&&!request.signal.aborted)error.value=tr('无法加载统计，请检查本地服务后重试。','無法載入統計，請檢查本機服務後重試。','Unable to load usage. Check the local service and retry.')}
 finally{if(version===generation)loading.value=false}
}
function updateRange(value:UsageRange){ranges.value={...ranges.value,[kind.value]:value}}
async function exportData(){
 if(!usage.value||loading.value||exporting.value)return
 exporting.value=true;exportMessage.value='';clearTimeout(exportNoticeTimer)
 try{
  const snapshot=JSON.parse(JSON.stringify(usage.value)) as UsageAnalytics,result=await downloadUsage(snapshot)
  if(result==='saved')exportMessage.value=tr('压缩包已保存，可再次导出','壓縮檔已儲存，可再次匯出','ZIP saved. You can export again.')
  else if(result==='download-started')exportMessage.value=tr('已开始下载，可再次导出','已開始下載，可再次匯出','Download started. You can export again.')
 }catch{exportMessage.value=tr('导出失败，请重试','匯出失敗，請重試','Export failed. Please retry.')}
 finally{exporting.value=false;exportNoticeTimer=setTimeout(()=>{exportMessage.value=''},3500)}
}
watch(()=>kind.value+':'+range.value.start+':'+range.value.end,load,{immediate:true})
onBeforeUnmount(()=>{generation++;controller?.abort();clearTimeout(exportNoticeTimer)})
</script>
<template>
 <div class="usage-dashboard">
  <nav class="model-category-tabs usage-category-tabs" role="tablist" :aria-label="tr('统计类别','統計類別','Usage category')"><button id="usage-category-llm" type="button" role="tab" :aria-selected="kind==='llm'" aria-controls="usage-category-panel" @click="kind='llm'" @keydown.right.prevent="kind='ocr'"><i class="model-category-icon" aria-hidden="true"><BotMessageSquare :size="20" :stroke-width="1.7"/></i><span>LLM<small>{{tr('Token 与缓存','Token 與快取','Tokens & cache')}}</small></span></button><button id="usage-category-ocr" type="button" role="tab" :aria-selected="kind==='ocr'" aria-controls="usage-category-panel" @click="kind='ocr'" @keydown.left.prevent="kind='llm'"><i class="model-category-icon" aria-hidden="true"><ScanText :size="20" :stroke-width="1.7"/></i><span>OCR<small>{{tr('识别调用次数','識別呼叫次數','Recognition requests')}}</small></span></button></nav>
  <section id="usage-category-panel" role="tabpanel" :aria-labelledby="'usage-category-'+kind">
   <header class="usage-dashboard-heading"><div><h3>{{kind==='llm'?tr('LLM 使用统计','LLM 使用統計','LLM usage'):tr('OCR 使用统计','OCR 使用統計','OCR usage')}}</h3><p>{{rangeLabel}}<span>{{tr('北京时间','北京時間','Beijing time')}}</span></p></div><div class="usage-dashboard-controls"><UsageDateFilter :model-value="range" @update:model-value="updateRange"/><button type="button" class="usage-export" :disabled="!usage||loading||exporting" @click="exportData"><Download :size="14"/>{{exporting?tr('导出中','匯出中','Exporting'):tr('导出','匯出','Export')}}</button><button type="button" class="usage-refresh" :class="{'is-refreshing':loading}" :disabled="loading" :aria-busy="loading" :aria-label="tr('刷新使用统计','重新整理使用統計','Refresh usage')" @click="load"><RefreshCw :size="15" :stroke-width="1.8"/></button></div></header>
   <p v-if="error" class="usage-dashboard-message error" role="alert">{{error}}</p><p v-if="exportMessage" class="usage-dashboard-message" role="status">{{exportMessage}}</p>
   <div v-if="!usage&&loading" class="usage-dashboard-loading" role="status"><span class="usage-skeleton"/><span class="usage-skeleton"/><span class="usage-skeleton"/><p>{{tr('正在加载统计…','正在載入統計…','Loading usage…')}}</p></div>
   <template v-if="usage">
    <div class="usage-summary-cards" :class="{'ocr-summary':kind==='ocr'}"><article v-for="metric in metrics" :key="metric.id" :data-stat="metric.id" :class="{'cache-metric':metric.id==='cached'}"><span><component :is="metric.icon" :size="14" :stroke-width="1.7" aria-hidden="true"/>{{metric.label}}</span><strong>{{format(metric.value)}}</strong></article></div>
    <section class="usage-overview-trends" :aria-label="tr('总体使用趋势','整體使用趨勢','Overall usage trend')"><header class="usage-section-title"><h4><Activity :size="14"/>{{tr('使用趋势','使用趨勢','Usage trend')}}</h4><span>{{usage.range.granularity==='hour'?tr('按小时','按小時','Hourly'):tr('按天','按天','Daily')}}</span></header><div class="usage-charts" :class="{'single-chart':kind==='ocr'}"><UsageTrendChart :points="usage.trend" metric="requests" :title="kind==='llm'?tr('API 请求次数','API 請求次數','API requests'):tr('OCR 调用次数','OCR 呼叫次數','OCR requests')" :total="usage.summary.requests" :granularity="usage.range.granularity"/><UsageTrendChart v-if="kind==='llm'" :points="usage.trend" metric="tokens" title="Tokens" :total="usage.summary.totalTokens||0" :granularity="usage.range.granularity"/></div><p v-if="usage.summary.unbucketedRequests" class="usage-data-note">{{usage.summary.unbucketedRequests}} {{tr('次请求缺少小时明细，已计入总数。','次請求缺少小時明細，已計入總數。','requests lack hourly detail and are included in the total.')}}</p></section>
    <section class="usage-model-details"><header class="usage-section-title"><h4>{{tr('模型明细','模型明細','Model details')}}</h4><span>{{usage.models.length}} {{tr('个模型','個模型','models')}}</span></header><div v-if="usage.models.length" class="usage-model-table-scroll"><table class="usage-model-table" :aria-label="kind.toUpperCase()+tr(' 模型用量',' 模型用量',' model usage')"><thead><tr><th>{{tr('模型','模型','Model')}}</th><template v-if="kind==='llm'"><th>{{tr('输入（命中缓存）','輸入（命中快取）','Input (cached)')}}</th><th>{{tr('输入（未命中缓存）','輸入（未命中快取）','Input (uncached)')}}</th><th>{{tr('输出','輸出','Output')}}</th><th>{{tr('总 Token','總 Token','Total tokens')}}</th></template><th>{{kind==='llm'?tr('请求','請求','Requests'):tr('调用次数','呼叫次數','Requests')}}</th></tr></thead><tbody><tr v-for="model in usage.models" :key="model.model"><td><span>{{model.model}}</span><small v-if="kind==='ocr'" class="usage-model-type">PaddleOCR</small></td><template v-if="kind==='llm'"><td class="usage-cached-cell">{{format(usageTokens(model).cached)}}</td><td>{{format(usageTokens(model).uncached)}}</td><td>{{format(usageTokens(model).output)}}</td><td>{{format(usageTokens(model).total)}}</td></template><td>{{format(model.requests)}}</td></tr></tbody></table></div><div v-else class="usage-empty"><ScanText v-if="kind==='ocr'" :size="24"/><BotMessageSquare v-else :size="24"/><strong>{{tr('所选时间内暂无调用','所選時間內暫無呼叫','No requests in this date range')}}</strong></div></section>
    <section v-for="model in usage.modelTrends" :key="model.model" class="usage-per-model" :aria-label="model.model+tr(' 使用趋势',' 使用趨勢',' usage trend')"><header><h4>{{model.model}}</h4><small v-if="kind==='ocr'" class="usage-model-type">PaddleOCR</small></header><div class="usage-charts" :class="{'single-chart':kind==='ocr'}"><UsageTrendChart chart-type="line" :points="model.points" metric="requests" :title="kind==='llm'?tr('API 请求次数','API 請求次數','API requests'):tr('OCR 调用次数','OCR 呼叫次數','OCR requests')" :total="usage.models.find(row=>row.model===model.model)?.requests||0" :granularity="usage.range.granularity"/><UsageTrendChart chart-type="line" v-if="kind==='llm'" :points="model.points" metric="tokens" title="Tokens" :total="usage.models.find(row=>row.model===model.model)?.totalTokens||0" :granularity="usage.range.granularity"/></div></section>
   </template>
  </section>
 </div>
</template>
