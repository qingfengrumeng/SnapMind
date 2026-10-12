<script setup lang="ts">
import {ref,watch,nextTick} from 'vue'
import {ArrowLeft,Sun,Moon,Monitor} from 'lucide-vue-next'
import {theme,language,tr,type Theme} from '../preferences'
import CaptureFunctions from './CaptureFunctions.vue'
import AboutSnapMind from './AboutSnapMind.vue'
import ModelSettings from './ModelSettings.vue'
import ShortcutSetting from './ShortcutSetting.vue'
import ToolShortcutSettings from './ToolShortcutSettings.vue'
import ModelUsageStatistics from './ModelUsageStatistics.vue'
import type {ToolAction} from '../tool-actions'
const props=defineProps<{connected:boolean;initialTab?:string}>()
const emit=defineEmits<{close:[];action:[action:ToolAction]}>()
const tab=ref(props.initialTab==='shortcuts'?'general':props.initialTab||'general')
const content=ref<HTMLElement>()
const tabItems=[{id:'general',zh:'通用',tw:'通用',en:'General'},{id:'usage',zh:'使用统计',tw:'使用統計',en:'Usage'},{id:'models',zh:'模型配置',tw:'模型設定',en:'Models'},{id:'tools',zh:'功能',tw:'功能',en:'Features'},{id:'about',zh:'关于',tw:'關於',en:'About'}]
function stepTab(step:number){const index=tabItems.findIndex(t=>t.id===tab.value);select(tabItems[(index+step+tabItems.length)%tabItems.length]!.id)}
const themes:{id:Theme;icon:typeof Sun;zh:string;tw:string;en:string}[]=[{id:'light',icon:Sun,zh:'浅色',tw:'淺色',en:'Light'},{id:'dark',icon:Moon,zh:'深色',tw:'深色',en:'Dark'},{id:'system',icon:Monitor,zh:'跟随系统',tw:'跟隨系統',en:'System'}]
function select(value:string){tab.value=value==='shortcuts'?'general':value;nextTick(()=>content.value?.scrollTo(0,0))}
function configureShortcuts(){select('general');nextTick(()=>content.value?.querySelector('#general-shortcuts')?.scrollIntoView({block:'start'}))}
watch(()=>props.initialTab,value=>{if(value)select(value)})
</script>
<template>
 <nav id="home-settings" class="launcher-menu home-settings-panel" :aria-label="tr('设置与工具面板','設定與工具面板','Settings panel')" @click.stop>
  <header class="home-settings-heading"><div><strong>{{tr('设置','設定','Settings')}}</strong><span>{{tr('按你的习惯，轻松捕捉','按你的習慣，輕鬆擷取','Make SnapMind feel like yours.')}}</span></div><button class="settings-return-home" :aria-label="tr('关闭设置面板','關閉設定面板','Close settings')" data-tooltip-disabled @click="emit('close')"><ArrowLeft :size="16" :stroke-width="1.8"/><span>{{tr('返回首页','返回首頁','Back home')}}</span></button></header>
  <div class="settings-tabs" role="tablist" :aria-label="tr('设置导航','設定導覽','Settings navigation')"><button v-for="item in tabItems" :key="item.id" role="tab" :id="'settings-tab-'+item.id" :aria-selected="tab===item.id" :aria-controls="'settings-content-'+item.id" @click="select(item.id)" @keydown.right.prevent="stepTab(1)" @keydown.left.prevent="stepTab(-1)">{{tr(item.zh,item.tw,item.en)}}</button></div>
  <section ref="content" class="settings-tab-content" role="tabpanel" :id="'settings-content-'+tab" :aria-labelledby="'settings-tab-'+tab">
   <template v-if="tab==='general'">
    <section class="general-setting"><h3>{{tr('界面语言','介面語言','Interface language')}}</h3><p>{{tr('立即切换界面语言，自动保存你的选择。','立即切換介面語言，自動儲存你的選擇。','Changes apply immediately and are saved automatically.')}}</p><div class="preference-segments" role="group" :aria-label="tr('界面语言','介面語言','Interface language')"><button v-for="item in [{id:'zh-CN',label:'简体中文'},{id:'zh-TW',label:'繁體中文'},{id:'en',label:'English'}] as const" :key="item.id" :aria-pressed="language===item.id" @click="language=item.id">{{item.label}}</button></div></section>
    <section class="general-setting"><h3>{{tr('外观主题','外觀主題','Appearance')}}</h3><p>{{tr('选择舒适的配色，或随系统自动调整。','選擇舒適的配色，或隨系統自動調整。','Choose a color theme or follow your system.')}}</p><div class="preference-segments" role="group" :aria-label="tr('外观主题','外觀主題','Appearance')"><button v-for="item in themes" :key="item.id" :aria-pressed="theme===item.id" @click="theme=item.id"><component :is="item.icon" :size="16"/>{{tr(item.zh,item.tw,item.en)}}</button></div></section>
    <section id="general-shortcuts" class="general-setting"><h3>{{tr('快捷键','快捷鍵','Shortcuts')}}</h3><p>{{tr('配置开始截图和各个工具的快捷键，修改后自动保存。','設定開始擷取與各工具的快捷鍵，修改後自動儲存。','Configure capture and tool shortcuts. Changes are saved automatically.')}}</p><ShortcutSetting/><ToolShortcutSettings/></section>
   </template>
   <ModelUsageStatistics v-else-if="tab==='usage'"/>
   <ModelSettings v-else-if="tab==='models'"/>
   <AboutSnapMind v-else-if="tab==='about'"/>
   <CaptureFunctions v-else @configure-shortcuts="configureShortcuts"/>
  </section>
  <footer class="settings-page-footer" :class="{'is-general':tab==='general'}"><i :class="{online:connected}"/>{{connected?tr('本地服务已连接','本機服務已連線','Local service connected'):tr('本地服务未连接','本機服務未連線','Local service offline')}}<span>SnapMind</span></footer>
 </nav>
</template>
