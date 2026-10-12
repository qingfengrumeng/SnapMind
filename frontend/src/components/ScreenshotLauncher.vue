<script setup lang="ts">
import { ref,watch } from 'vue'
import { Scissors, Minus, X, Monitor, ImageUp, Images, LayoutGrid, List, Scan, ArrowUpRight, ChevronRight, Settings, PenLine, Sparkles } from 'lucide-vue-next'
import Icon from './Icon.vue'
import SnapMindLogo from './SnapMindLogo.vue'
import HomeSettings from './HomeSettings.vue'
import {tr,tx} from '../preferences'

import {captureShortcut} from '../shortcut'
import type {ToolAction} from '../tool-actions'
import type { Asset } from '../types'
import { native, desktop } from '../desktop'

const props=defineProps<{ recent: Asset[]; connected: boolean; capturing: boolean; refreshing: boolean;modelRequest?:number;shortcutRequest?:number }>()
const emit = defineEmits<{ capture: []; import: []; gallery: []; settings: []; 'model-settings': []; shortcut: []; refresh: []; preview: [asset: Asset]; drop: [files: FileList] }>()
const menu = ref(false), minimized = ref(false), dropActive = ref(false)
const settingsTab=ref('general')
watch(()=>props.modelRequest,()=>{menu.value=true;settingsTab.value='models'})
watch(()=>props.shortcutRequest,()=>{menu.value=true;settingsTab.value='general'})
const galleryView=ref<'grid'|'list'>(localStorage.getItem('snapmind-gallery-view')==='list'?'list':'grid')
function setGalleryView(value:'grid'|'list'){galleryView.value=value;localStorage.setItem('snapmind-gallery-view',value)}
function fileType(asset:Asset){return asset.data.startsWith('data:image/jpeg')?'JPG':asset.data.startsWith('data:image/webp')?'WEBP':'PNG'}
function toolAction(action:ToolAction){if(['settings','model-settings','shortcut'].includes(action)){trigger(action as 'settings'|'model-settings'|'shortcut');return}menu.value=false;if(action==='close')close();else if(action==='refresh')emit('refresh');else if(action!=='quit'&&action!=='launcher')trigger(action)}
function trigger(event: 'capture' | 'import' | 'gallery' | 'settings' | 'model-settings' | 'shortcut') { if(event==='model-settings'||event==='shortcut'){menu.value=true;settingsTab.value=event==='model-settings'?'models':'general';return}if(event!=='settings')menu.value = false; emit(event as 'capture') }
function drop(e: DragEvent) { dropActive.value = false; if (e.dataTransfer?.files.length) emit('drop', e.dataTransfer.files) }
function minimize() { if (native) desktop.minimize(); else minimized.value = true }
function close() { menu.value = false; if (native) desktop.hide(); else minimized.value = true }
function drag(e: PointerEvent) { if (native && !(e.target as Element).closest('button')) desktop.drag() }
</script>

<template>
 <main class="screenshot-desktop launcher-desktop" @keydown.esc="menu=false" @dragover.prevent="dropActive=true" @dragleave.self="dropActive=false" @drop.prevent="drop">
  <div class="desktop-preview-label"><span class="preview-indicator"/>SnapMind 截图工具 · 网页预览</div>
  <section v-if="!minimized" class="screenshot-window snapmind-home" aria-label="SnapMind 截图工具">
   <header class="launcher-titlebar" @pointerdown="drag">
    <span class="launcher-brand-logo"><SnapMindLogo :size="25"/></span>
    <span class="launcher-name">SnapMind</span>
<div class="window-controls" data-tooltip-disabled><button class="launcher-settings-toggle" :class="{active:menu}" :aria-label="tx('设置与工具')" :aria-expanded="menu" aria-controls="home-settings" @click.stop="menu=!menu"><Settings :size="18" :stroke-width="1.7"/></button><span class="window-control-divider" aria-hidden="true"/><button :aria-label="tx('最小化工具')" @click="minimize"><Minus :size="21"/></button><button :aria-label="tx('关闭工具窗口')" @click="close"><X :size="21"/></button></div>
   </header>

   <div class="launcher-content">
    <section class="launcher-banner" aria-label="SnapMind"><span class="banner-ambient" aria-hidden="true"/>
     <div class="launcher-banner-copy"><span class="banner-brandline"><span class="banner-brand-dot"/>CAPTURE. THINK. KEEP.</span><strong>{{tr('把看见的，变成灵感。','把看見的，變成靈感。','Capture a moment. Keep an idea.')}}</strong><span class="banner-description">{{tr('截取一瞬，留给思考更多空间。','擷取一瞬，留給思考更多空間。','A little capture. More room to think.')}}</span><div class="banner-feature-tags"><span><Scan :size="13"/>{{tr('框选截图','框選擷取','Capture')}}</span><i/><span><PenLine :size="13"/>{{tr('自由标注','自由標註','Annotate')}}</span><i/><span><Sparkles :size="13"/>{{tr('随图思考','隨圖思考','Explore')}}</span></div></div>
     <div class="banner-action-area"><span class="banner-mini-mark" aria-hidden="true"><span class="banner-logo-halo"/><Scan :size="82" :stroke-width=".85"/><SnapMindLogo :size="56"/><span class="banner-logo-dot one"/><span class="banner-logo-dot two"/></span><button class="banner-capture-button" :disabled="capturing" :aria-label="tr('开始截图','開始擷取','Start capture')" :data-tooltip="tr('开始截图','開始擷取','Start capture')" :data-shortcut="captureShortcut" @click="trigger('capture')"><Scissors :size="17" :stroke-width="1.7"/><span>{{tr('开始截图','開始擷取','Start capture')}}</span><ArrowUpRight :size="15"/></button></div>
    </section>

    <div class="launcher-gallery-heading">
     <h1><Images :size="21" :stroke-width="1.7"/>{{tr('我的图片','我的圖片','My images')}}<span class="launcher-image-count">{{recent.length}} {{tr('张','張','images')}}</span></h1>
     <div class="launcher-view-switch" data-tooltip-disabled role="group" aria-label="图片展示方式"><button :aria-label="tx('网格展示')" :aria-pressed="galleryView==='grid'" @click="setGalleryView('grid')"><LayoutGrid :size="17" :stroke-width="1.7"/></button><button :aria-label="tx('列表展示')" :aria-pressed="galleryView==='list'" @click="setGalleryView('list')"><List :size="18" :stroke-width="1.7"/></button></div>
    </div>

    <div class="launcher-gallery-body">
     <div v-if="recent.length" class="launcher-recent-grid" :class="{'is-list':galleryView==='list'}"><button v-for="(a,index) in recent" :key="a.id" class="shot-card" data-tooltip-disabled :aria-label="`预览 ${a.name}`" @click="emit('preview',a)"><span class="shot-thumbnail"><img :src="a.data" :alt="a.name" loading="lazy"/><span class="shot-number">{{String(index+1).padStart(2,'0')}}</span></span><span class="shot-caption"><strong>{{a.name||'屏幕截图'}}</strong><span class="shot-meta"><span>{{a.width}} × {{a.height}}</span><i/><span>{{fileType(a)}}</span></span></span><ChevronRight v-if="galleryView==='list'" class="shot-open" :size="17" :stroke-width="1.7"/></button></div>
     <button v-else class="launcher-empty-album" :aria-label="tx('导入第一张图片')" data-tooltip="从一张图片开始" data-tooltip-detail="点击导入，也可以拖入图片或 Ctrl+V 粘贴" @click="trigger('import')"><span class="launcher-empty-art"><Scan :size="72" :stroke-width=".8"/><Images :size="29" :stroke-width="1.2"/></span><span class="launcher-empty-copy"><strong>{{tx('先截一张，开启新思路')}}</strong><span>{{tx('每一次捕捉，都在这里好好收纳。')}}</span></span></button>
    </div>
   </div>

   <div v-if="dropActive" class="launcher-drop-overlay"><ImageUp :size="35"/><span>松开，开始裁剪与标注</span></div>
   <template v-if="native"><div v-for="direction in ['North','South','East','West','NorthWest','NorthEast','SouthWest','SouthEast'] as const" :key="direction" class="launcher-resize-edge" :class="direction" aria-hidden="true" @pointerdown.stop.prevent="desktop.resize(direction)"/></template>
   <HomeSettings v-if="menu" :initial-tab="settingsTab" :connected="connected" @close="menu=false;settingsTab='general'" @action="toolAction"/>
  </section>
  <div v-else class="minimized-tool"><button @click="minimized=false" aria-label="恢复截图工具" title="恢复截图工具"><Scissors :size="26"/></button><button class="minimized-snap" @click="trigger('capture')" title="直接截图"><Icon name="scan" :size="18"/></button></div>
  <div class="desktop-browser-note"><Monitor :size="13"/><span>网页截屏需浏览器授权；Alt+Z 在本页获得焦点时生效。</span></div>
 </main>
</template>
