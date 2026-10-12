<script setup lang="ts">
import { computed, type Component } from 'vue'
import { Scissors, ImageUp, Images, RotateCw, Settings2, Power, BotMessageSquare } from 'lucide-vue-next'
import SnapMindLogo from './SnapMindLogo.vue'
import type { ToolAction } from '../tool-actions'
import {captureShortcut} from '../shortcut'
import {tr} from '../preferences'
const props=withDefaults(defineProps<{tray?:boolean;connected?:boolean;compact?:boolean}>(),{tray:false,connected:false,compact:false})
const emit=defineEmits<{action:[action:ToolAction]}>()
interface Item {action:ToolAction;label:string;description:string;icon:Component;shortcut?:string;primary?:boolean}
const shot:Item={action:'capture',label:'截图',description:'框选屏幕，保留当下的画面',icon:Scissors,shortcut:'Alt+Z',primary:true}
const gallery:Item={action:'gallery',label:'截图相册',description:'浏览已保存的截图',icon:Images}
const settings:Item={action:'settings',label:'截图设置',description:'快捷键、布局和保存说明',icon:Settings2}
const modelSettings:Item={action:'model-settings',label:'模型配置',description:'接口地址、模型与 API Key',icon:BotMessageSquare}
const groups=computed<Item[][]>(()=>props.tray?[
 [shot,modelSettings]
]:[
 [shot,{action:'import',label:'打开图片',description:'导入图片，继续裁剪和标注',icon:ImageUp,shortcut:'Ctrl+O'}],
 [gallery,{action:'refresh',label:'刷新相册',description:'重新载入已保存的截图',icon:RotateCw}],[settings,modelSettings]
])
const headings=['截图与导入','图片管理','偏好设置']
const translations:Record<string,[string,string]>={
 '截图':['擷取','Capture'],'打开图片':['開啟圖片','Open image'],'截图相册':['截圖相簿','Image library'],'AI 历史':['AI 歷史','AI history'],'刷新相册':['重新整理相簿','Refresh images'],'截图设置':['擷取設定','Capture settings'],'模型配置':['模型設定','Model configuration'],'打开主界面':['開啟主畫面','Open SnapMind'],
 '框选屏幕，保留当下的画面':['框選螢幕，保留當下畫面','Select an area of your screen'],'导入图片，继续裁剪和标注':['匯入圖片，繼續裁切與標註','Import, crop and annotate'],'浏览已保存的截图':['瀏覽已儲存的截圖','Browse saved captures'],'回到截图的讨论与内容工作区':['返回截圖討論與工作區','Return to capture conversations'],'重新载入已保存的截图':['重新載入已儲存的截圖','Reload saved captures'],'快捷键、布局和保存说明':['快捷鍵、版面與儲存說明','Shortcuts, layout and saving'],'接口地址、模型与 API Key':['介面位址、模型與 API Key','Endpoint, model and API key'],'查看与整理最近的截图':['查看與整理最近的截圖','Review your recent captures'],
 '截图与导入':['擷取與匯入','Capture & import'],'图片管理':['素材與對話','Images & conversations'],'偏好设置':['偏好設定','Preferences']}
function translated(value:string){const pair=translations[value];return pair?tr(value,pair[0],pair[1]):value}
</script>
<template>
 <div class="tool-menu-content" :class="{'tray-menu-content':tray}">
  <header v-if="!compact&&!tray" class="tool-menu-brand"><SnapMindLogo :size="32"/><div><strong>SnapMind</strong><span>截图、整理与思考</span></div><span class="tool-menu-tag">快捷工具</span></header>
  <div class="tool-menu-groups"><section v-for="(group,index) in groups" :key="index" class="tool-menu-group"><h3 v-if="compact" class="tool-menu-section-title">{{translated(headings[index])}}</h3><button v-for="item in group" :key="item.action" :aria-label="translated(item.label)" :class="{'tool-menu-primary':item.primary}" @click="emit('action',item.action)"><span class="tool-menu-icon"><component :is="item.icon" :size="19" :stroke-width="1.7"/></span><span class="tool-menu-text"><strong>{{translated(item.label)}}</strong><small v-if="!tray">{{translated(item.description)}}</small></span><kbd v-if="!tray&&item.shortcut">{{item.action==='capture'?captureShortcut:item.shortcut}}</kbd></button></section></div>
  <div v-if="tray" class="tray-menu-exit"><button aria-label="退出 SnapMind" @click="emit('action','quit')"><Power :size="17" :stroke-width="1.7"/><span>{{tr('退出','退出','Quit')}}</span></button></div>
  <footer v-if="!tray" class="tool-menu-footer"><span><i :class="{online:connected}"/>{{connected?'本地服务已连接':'SnapMind 截图'}}</span></footer>
 </div>
</template>
