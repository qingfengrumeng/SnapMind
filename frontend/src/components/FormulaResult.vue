<script setup lang="ts">
import { computed, ref } from 'vue'
import katex from 'katex'
import Icon from './Icon.vue'
const props=defineProps<{modelValue:string}>()
const emit=defineEmits<{'update:modelValue':[value:string];toast:[message:string]}>()
const editing=ref(false),draft=ref(''),error=ref('')
const rendered=computed(()=>{try{return katex.renderToString(props.modelValue,{displayMode:true,throwOnError:true,trust:false})}catch{return '<span>公式格式有误，请编辑校对</span>'}})
function edit(){draft.value=props.modelValue;error.value='';editing.value=true}
function save(){try{katex.renderToString(draft.value,{throwOnError:true,trust:false});emit('update:modelValue',draft.value);editing.value=false;emit('toast','公式已更新')}catch(e){error.value='LaTeX 格式有误，请检查括号与命令。'}}
async function copy(){try{await navigator.clipboard.writeText(props.modelValue);emit('toast','LaTeX 已复制')}catch{emit('toast','浏览器未允许剪贴板访问')}}
function download(){const url=URL.createObjectURL(new Blob([props.modelValue],{type:'text/plain;charset=utf-8'}));const a=document.createElement('a');a.href=url;a.download='formula.tex';a.click();URL.revokeObjectURL(url)}
</script>
<template>
 <div class="formula-result"><div class="result-label"><span><Icon name="formula" :size="16"/>公式 · LaTeX</span><button @click="edit" title="校对公式" aria-label="校对公式"><Icon name="edit" :size="15"/>校对</button></div><div class="formula-render" v-html="rendered"/><div class="result-footer"><span><i/>可编辑结果</span><button @click="copy"><Icon name="copy" :size="14"/>复制 LaTeX</button><button @click="download" title="导出 TEX" aria-label="导出 TEX"><Icon name="download" :size="15"/></button></div><div class="formula-edit" v-if="editing"><label>LaTeX 源码<textarea v-model="draft" rows="4" spellcheck="false"/></label><p v-if="error" class="error-text">{{error}}</p><div><button @click="editing=false">取消</button><button class="primary small" @click="save">应用修改</button></div></div></div>
</template>
