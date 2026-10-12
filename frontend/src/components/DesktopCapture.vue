<script setup lang="ts">
import {onMounted,onBeforeUnmount,ref} from 'vue'
import CaptureOverlay from './CaptureOverlay.vue'
import {desktop,type DesktopFrame} from '../desktop'
import type {Asset} from '../types'
import type {CaptureResult} from '../capture'
const asset=ref<Asset>(),error=ref(''),closing=ref(false),editing=ref(false),floatingPreview=ref(false)
const dispose:(()=>void)[]=[]
async function finish(result:CaptureResult){if(closing.value)return;closing.value=true;try{await desktop.finish(result)}catch(e){closing.value=false;error.value=String(e)}}
async function cancel(){if(closing.value)return;closing.value=true;try{await desktop.cancel();asset.value=undefined}catch(e){closing.value=false;error.value=String(e)}}
function edit(assetToEdit:Asset){editing.value=true;asset.value=assetToEdit;error.value=''}
async function ready(){const id=asset.value?.id;if(id)try{await desktop.captureReady(id)}catch(e){error.value=String(e);await cancel()}}
onMounted(async()=>{dispose.push(await desktop.listen<DesktopFrame>('desktop:capture-ready',frame=>{floatingPreview.value=!!frame.floatingPreview;editing.value=false;asset.value=frame.asset;error.value='';closing.value=false}));dispose.push(await desktop.listen('desktop:capture-closed',()=>{asset.value=undefined;closing.value=false;floatingPreview.value=false}));const state=await desktop.state();if(state.captureActive&&state.frame){asset.value=state.frame.asset;floatingPreview.value=!!state.frame.floatingPreview}})
onBeforeUnmount(()=>dispose.forEach(fn=>fn()))
</script>
<template><CaptureOverlay v-if="asset" :key="asset.id" :source="asset" :closing="closing" :initial-selection="editing||floatingPreview" :floating-preview="floatingPreview" @edit="edit" @ready="ready" @finish="finish" @cancel="cancel" @toast="error=$event"/><div class="native-toast" v-if="error" role="status">{{error}}<button @click="error=''">×</button></div></template>
