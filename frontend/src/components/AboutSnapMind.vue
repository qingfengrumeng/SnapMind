<script setup lang="ts">
import {computed,onMounted,ref} from 'vue'
import {getVersion} from '@tauri-apps/api/app'
import {ExternalLink,GitBranch,Github,Sparkles} from 'lucide-vue-next'
import {appInfo} from '../app-info'
import {desktop,native} from '../desktop'
import {tr} from '../preferences'
import SnapMindLogo from './SnapMindLogo.vue'

const localize=(text:readonly [string,string,string])=>tr(text[0],text[1],text[2])
const version=ref(appInfo.version),error=ref('')
onMounted(async()=>{if(native){try{version.value=await getVersion()}catch{/* Use the configured version when native metadata is unavailable. */}}})
const repository=computed(()=>appInfo.repositoryUrl.trim().replace(/\/+$/,''))
const links=computed(()=>[
 {id:'github',icon:Github,title:['GitHub','GitHub','GitHub'],url:repository.value},
 {id:'releases',icon:ExternalLink,title:['更新日志','更新日誌','Changelog'],url:repository.value?repository.value+'/releases':''},
] as const)
async function openLink(event:MouseEvent,url:string){
 if(!native)return
 event.preventDefault();error.value=''
 try{await desktop.openEntity(url)}catch{error.value=tr('无法打开链接，请稍后重试。','無法開啟連結，請稍後重試。','Unable to open this link. Please try again.')}
}
</script>

<template>
 <div class="about-snapmind">
  <section class="about-hero" :aria-label="tr('关于 SnapMind','關於 SnapMind','About SnapMind')">
   <header class="about-brand">
    <span class="about-logo"><SnapMindLogo :size="48"/></span>
    <div class="about-brand-copy"><div class="about-brand-title"><h3>{{appInfo.name}}</h3><span class="about-version"><GitBranch :size="13" aria-hidden="true"/>v{{version}}</span></div><span class="about-tagline">{{tr('捕捉画面，连接灵感','擷取畫面，連結靈感','Capture a moment. Connect an idea.')}}</span></div>
    <div class="about-brand-actions"><component :is="link.url?'a':'button'" v-for="link in links" :key="link.id" class="about-project-button" :data-project-link="link.id" :href="link.url||undefined" :type="link.url?undefined:'button'" :disabled="link.url?undefined:true" :title="link.url?undefined:tr('链接暂未开放','連結暫未開放','Link coming soon')" :target="link.url?'_blank':undefined" :rel="link.url?'noopener noreferrer':undefined" @click="link.url&&openLink($event,link.url)"><component :is="link.icon" :size="16" :stroke-width="1.7" aria-hidden="true"/>{{localize(link.title)}}</component></div>
   </header>
   <div class="about-introduction"><span class="about-eyebrow"><Sparkles :size="14" aria-hidden="true"/>{{tr('你的截图与 AI 助手','你的擷取與 AI 助手','Your capture & AI companion')}}</span><h4>{{tr('从一张截图，开始理解与创作。','從一張擷取畫面，開始理解與創作。','Start with a capture. Understand and create.')}}</h4><p>{{tr('SnapMind 是一款面向 Windows 的截图与图片处理工具，将截图标注、文字识别、翻译和 AI 对话放在同一个工作流程中。无论是记录工作内容、阅读资料，还是整理学习笔记，都可以从截取画面开始，轻松保存、理解和利用图片中的信息。','SnapMind 是一款適用於 Windows 的擷取與圖片處理工具，整合擷取標註、文字辨識、翻譯與 AI 對話。無論是記錄工作內容、閱讀資料，還是整理學習筆記，都可以從擷取畫面開始，輕鬆儲存、理解與運用圖片中的資訊。','SnapMind is a Windows capture and image tool that brings annotation, text recognition, translation and AI chat into one workflow. Capture your work, read materials or organize study notes, then save, understand and use the information in your images.')}}</p></div>
   <p v-if="error" class="about-link-error" role="alert">{{error}}</p>
  </section>
 </div>
</template>

<style scoped>
.about-snapmind{padding-top:18px;color:var(--ink-soft)}
.about-snapmind svg{color:inherit}
.about-hero{padding:22px;border:1px solid var(--accent-glow);border-radius:16px;background:linear-gradient(135deg,var(--accent-wash),var(--surface) 80%)}
.about-brand{display:flex;align-items:center;gap:13px}
.about-logo{display:grid;place-items:center;flex-shrink:0;width:58px;height:58px;border:1px solid var(--accent-glow);border-radius:16px;background:var(--surface)}
.about-brand-copy{min-width:0}
.about-brand-title{display:flex;align-items:center;flex-wrap:wrap;gap:9px}
.about-brand h3{margin:0;font-family:var(--font-display);font-size:24px;line-height:1.35;letter-spacing:-.6px;color:var(--ink);font-weight:600}
.about-tagline{display:block;margin-top:4px;font-size:12px;line-height:1.6;color:var(--ink-faint)}
.about-version{display:flex;align-items:center;gap:5px;flex-shrink:0;padding:4px 8px;border:1px solid var(--accent-glow);border-radius:20px;background:var(--surface);font-family:var(--font-mono);font-size:11px;color:var(--accent)}
.about-brand-actions{display:flex;align-items:center;flex-wrap:wrap;gap:8px;margin-left:auto;flex-shrink:0}
.about-snapmind .about-project-button{display:inline-flex;align-items:center;justify-content:center;gap:7px;width:auto;height:34px;padding:0 11px;border:1px solid var(--line-strong);border-radius:9px;background:var(--surface);color:var(--ink-soft);font-size:12px;font-weight:500;white-space:nowrap;text-decoration:none}
.about-snapmind .about-project-button:disabled{opacity:1;cursor:default;color:var(--ink-faint)}
.about-snapmind a.about-project-button:hover{background:var(--accent-wash);border-color:var(--accent-soft);color:var(--accent)}
.about-introduction{margin-top:25px}
.about-eyebrow{display:flex;align-items:center;gap:6px;font-size:12px;color:var(--accent)}
.about-introduction h4{margin:8px 0 10px;font-size:20px;font-weight:600;line-height:1.6;color:var(--ink)}
.about-introduction p{margin:0;max-width:720px;font-size:13px;line-height:1.95;color:var(--ink-soft)}
.about-link-error{margin:10px 0 0;font-size:12px;color:var(--danger,#db4964)}
.about-snapmind a:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
@container(max-width:639px){.about-hero{padding:17px}.about-brand{flex-wrap:wrap}.about-brand-actions{flex-basis:100%;margin-left:0}.about-introduction h4{font-size:18px}}
@container(max-width:399px){.about-brand{gap:10px}.about-logo{width:50px;height:50px}.about-brand h3{font-size:22px}.about-tagline{font-size:11px}}
</style>
