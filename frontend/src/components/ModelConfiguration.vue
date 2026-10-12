<script setup lang="ts">
import {onMounted,ref} from 'vue'
import {tx} from '../preferences'
import {BrainCircuit,Eye,EyeOff,Check,LoaderCircle} from 'lucide-vue-next'
import {api,type ModelConfig} from '../api'
const emit=defineEmits<{saved:[];cancel:[]}>()
const provider=ref<ModelConfig['provider']>('openai-compatible'),baseUrl=ref(''),model=ref(''),apiKey=ref(''),hasApiKey=ref(false),clearApiKey=ref(false),showKey=ref(false),loading=ref(true),saving=ref(false),loaded=ref(false),error=ref('')
async function load(){loading.value=true;error.value='';try{const config=await api.modelConfig();provider.value=config.provider;baseUrl.value=config.baseUrl;model.value=config.model;hasApiKey.value=config.hasApiKey;loaded.value=true}catch{error.value='无法加载模型配置，请检查本地服务后重试'}finally{loading.value=false}}
async function save(){saving.value=true;error.value='';try{await api.saveModelConfig({provider:provider.value,baseUrl:baseUrl.value.trim(),model:model.value.trim(),apiKey:apiKey.value||undefined,clearApiKey:clearApiKey.value});apiKey.value='';emit('saved')}catch(e){error.value=e instanceof Error?e.message:'配置保存失败，请重试'}finally{saving.value=false}}
onMounted(load)
</script>
<template>
 <div class="model-configuration">
  <span class="model-config-symbol"><BrainCircuit :size="23"/></span><h2>{{tx('模型配置')}}</h2><p class="model-config-intro">{{tx('设置接口地址与模型，配置保存在本机。')}}</p>
  <div v-if="loading" class="model-config-loading"><LoaderCircle :size="17"/>{{tx('正在加载配置…')}}</div>
  <form v-else-if="loaded" @submit.prevent="save">
   <fieldset :disabled="saving">
    <label class="model-config-field"><span>{{tx('接口类型')}}</span><select v-model="provider" aria-label="模型接口类型"><option value="openai-compatible">{{tx('OpenAI 兼容接口')}}</option><option value="ollama">{{tx('Ollama 本地接口')}}</option></select></label>
    <label class="model-config-field"><span>模型名称 <b>*</b></span><input v-model="model" :aria-label="tx('模型名称')" required maxlength="160" :placeholder="tx('填写服务提供的模型 ID')" spellcheck="false"/></label>
    <label class="model-config-field"><span>{{tx('接口地址')}} <b>*</b></span><input v-model="baseUrl" aria-label="模型接口地址" required maxlength="2048" type="url" placeholder="https://api.example.com/v1" spellcheck="false"/><small>{{tx('填写完整地址；本地服务也可使用 HTTP。')}}</small></label>
    <div class="model-config-field"><label for="model-api-key">API Key <span class="model-key-state">{{hasApiKey?tx('已保存'):tx('可选')}}</span></label><div class="model-key-input"><input id="model-api-key" v-model="apiKey" aria-label="模型 API Key" :type="showKey?'text':'password'" maxlength="4096" autocomplete="off" :disabled="clearApiKey" :placeholder="hasApiKey?tx('留空保留已保存的密钥'):tx('输入 API Key，本地无鉴权服务可留空')" spellcheck="false"/><button type="button" :aria-label="showKey?'隐藏 API Key':'显示 API Key'" @click="showKey=!showKey"><EyeOff v-if="showKey" :size="17"/><Eye v-else :size="17"/></button></div><label v-if="hasApiKey" class="model-key-clear"><input type="checkbox" v-model="clearApiKey"/>{{tx('清除已保存的 API Key')}}</label></div>
   </fieldset>
   <p class="model-config-note">{{tx('当前 AI 处理仍为演示模式；此处先保存模型配置。')}}</p>
   <p v-if="error" class="model-config-error" role="alert">{{error}}</p>
   <div class="model-config-actions"><button type="button" :disabled="saving" @click="emit('cancel')">{{tx('取消')}}</button><button class="primary" type="submit" :disabled="saving||!baseUrl.trim()||!model.trim()"><LoaderCircle v-if="saving" :size="15"/><Check v-else :size="15"/>{{saving?tx('保存中…'):tx('保存配置')}}</button></div>
  </form>
  <template v-else><p class="model-config-error" role="alert">{{error}}</p><button class="primary" @click="load">{{tx('重新加载')}}</button></template>
 </div>
</template>
