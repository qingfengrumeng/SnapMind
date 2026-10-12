<script setup lang="ts">
import {ref,watch} from 'vue'
import {BotMessageSquare,ScanText,AudioLines,Mic} from 'lucide-vue-next'
import ModelProfiles from './ModelProfiles.vue'
import OcrConfiguration from './OcrConfiguration.vue'
import SpeechConfiguration from './SpeechConfiguration.vue'
import {tr} from '../preferences'
const category=ref<'llm'|'ocr'|'asr'|'tts'>('llm'),speechKind=ref<'asr'|'tts'>('asr')
const profiles=ref<InstanceType<typeof ModelProfiles>>()
const ocr=ref<InstanceType<typeof OcrConfiguration>>()
const ocrVisited=ref(false)
const speechVisited=ref(false),speech=ref<InstanceType<typeof SpeechConfiguration>>()
watch(category,value=>{profiles.value?.discardModelLists();ocr.value?.discardModelLists();speech.value?.stopPreview();if(value==='ocr')ocrVisited.value=true;if(value==='asr'||value==='tts'){speechKind.value=value;speechVisited.value=true}})
</script>
<template>
 <div class="model-settings-categories">
  <nav class="model-category-tabs" role="tablist" :aria-label="tr('模型类别','模型類別','Model categories')">
   <button id="model-category-llm" role="tab" :aria-selected="category==='llm'" aria-controls="model-panel-llm" @click="category='llm'" @keydown.right.prevent="category='ocr'"><i class="model-category-icon" aria-hidden="true"><BotMessageSquare :size="20" :stroke-width="1.7"/></i><span>LLM<small>{{tr('语言与多模态','語言與多模態','Language & vision')}}</small></span></button>
   <button id="model-category-ocr" role="tab" :aria-selected="category==='ocr'" aria-controls="model-panel-ocr" @click="category='ocr'" @keydown.left.prevent="category='llm'" @keydown.right.prevent="category='asr'"><i class="model-category-icon" aria-hidden="true"><ScanText :size="20" :stroke-width="1.7"/></i><span>OCR<small>{{tr('文字识别与定位','文字識別與定位','Text & positioning')}}</small></span></button>
   <button id="model-category-asr" role="tab" :aria-selected="category==='asr'" aria-controls="model-panel-speech" @click="category='asr'" @keydown.left.prevent="category='ocr'" @keydown.right.prevent="category='tts'"><i class="model-category-icon" aria-hidden="true"><Mic :size="20" :stroke-width="1.7"/></i><span>ASR<small>{{tr('语音识别','語音識別','Speech recognition')}}</small></span></button>
   <button id="model-category-tts" role="tab" :aria-selected="category==='tts'" aria-controls="model-panel-speech" @click="category='tts'" @keydown.left.prevent="category='asr'"><i class="model-category-icon" aria-hidden="true"><AudioLines :size="20" :stroke-width="1.7"/></i><span>TTS<small>{{tr('语音合成','語音合成','Speech synthesis')}}</small></span></button>
  </nav>
  <section v-show="category==='llm'" id="model-panel-llm" role="tabpanel" aria-labelledby="model-category-llm"><ModelProfiles ref="profiles"/></section>
  <section v-show="category==='ocr'" id="model-panel-ocr" role="tabpanel" aria-labelledby="model-category-ocr"><OcrConfiguration v-if="ocrVisited" ref="ocr"/></section>
  <section v-show="category==='asr'||category==='tts'" id="model-panel-speech" role="tabpanel" :aria-labelledby="'model-category-'+speechKind"><SpeechConfiguration v-if="speechVisited" ref="speech" :kind="speechKind"/></section>
 </div>
</template>
