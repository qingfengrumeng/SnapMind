<script setup lang="ts">
import {computed,ref} from 'vue'
import {Braces,Copy,Check,Minimize2,Maximize2} from 'lucide-vue-next'
import {tr} from '../preferences'
import type {SnapMindConfiguration,OcrDocument} from '../api'
const props=defineProps<{value:SnapMindConfiguration|OcrDocument;showKeys:boolean;status:string;error?:string;lockKeys?:boolean}>()
const emit=defineEmits<{reveal:[value:boolean]}>()
const compact=ref(false),copied=ref(false),copyError=ref(false)
const json=computed(()=>JSON.stringify(props.value,null,compact.value?0:2))
function tokens(line:string){const parts:{text:string;kind:string}[]=[];const pattern=/("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false|null)\b|-?\d+(?:\.\d+)?/g;let previous=0;for(const match of line.matchAll(pattern)){if(match.index!>previous)parts.push({text:line.slice(previous,match.index),kind:''});parts.push({text:match[0],kind:match[2]?'key':match[1]?'string':match[3]?'boolean':'number'});previous=match.index!+match[0].length}if(previous<line.length)parts.push({text:line.slice(previous),kind:''});return parts}
async function copy(){copyError.value=false;try{await navigator.clipboard.writeText(json.value);copied.value=true;setTimeout(()=>copied.value=false,1800)}catch{copyError.value=true}}
</script>
<template>
 <section class="configuration-json" :aria-label="tr('配置 JSON','設定 JSON','Configuration JSON')">
  <header><div><Braces :size="17"/><strong>{{tr('配置 JSON','設定 JSON','Configuration JSON')}}</strong></div><span class="configuration-sync" :class="status">{{status==='saving'?tr('同步中…','同步中…','Syncing…'):status==='pending'?tr('待同步','待同步','Pending'):status==='error'?tr('同步失败','同步失敗','Sync failed'):tr('已同步','已同步','Synced')}}</span></header>
  <div class="configuration-json-toolbar"><label><input type="checkbox" :disabled="lockKeys" :checked="!showKeys" @change="emit('reveal',!($event.target as HTMLInputElement).checked)"/>{{tr('隐藏 API Key','隱藏 API Key','Hide API keys')}}</label><span>{{tr('表单修改实时预览，自动写入文件','表單修改即時預覽，自動寫入檔案','Live preview. Changes save automatically.')}}</span><button type="button" :aria-label="tr('切换 JSON 格式','切換 JSON 格式','Toggle JSON format')" @click="compact=!compact"><Maximize2 v-if="compact" :size="13"/><Minimize2 v-else :size="13"/>{{compact?tr('格式化','格式化','Format'):tr('紧凑','緊湊','Compact')}}</button><button type="button" :aria-label="tr('复制 JSON 预览','複製 JSON 預覽','Copy JSON preview')" @click="copy"><Check v-if="copied" :size="13"/><Copy v-else :size="13"/>{{copied?tr('已复制','已複製','Copied'):tr('复制','複製','Copy')}}</button></div>
  <div class="configuration-code" tabindex="0"><div v-for="(line,index) in json.split('\n')" :key="index" class="configuration-code-line"><span class="configuration-line-number" aria-hidden="true">{{index+1}}</span><code><span v-for="(part,i) in tokens(line)" :key="i" :class="'json-'+part.kind">{{part.text}}</span></code></div></div>
  <p v-if="error||copyError" class="configuration-json-error" role="alert">{{error||tr('复制失败，可以选中内容复制','複製失敗，可以選取內容複製','Copy failed. Select the text to copy it.')}}</p>
  <p class="configuration-json-note">{{tr('预览可隐藏密钥；文件保存真实 API Key。enabled 表示该模型是否启用。','預覽可隱藏金鑰；檔案儲存實際 API Key。enabled 表示該模型是否啟用。','Keys may be hidden in the preview. The file stores actual keys; enabled marks the active model.')}}</p>
 </section>
</template>
