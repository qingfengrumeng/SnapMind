<script setup lang="ts">
import {computed} from 'vue'
import katex from 'katex'
const props=defineProps<{text:string}>()
// All ordinary text and code are Vue-escaped. Only KaTeX's trust:false output is HTML.
const pieces=computed(()=>{
 const result:{kind:'text'|'code'|'math'|'strong'|'inline-code'|'heading';text:string;html?:string;display?:boolean}[]=[]
 const expression=/```[^\n]*\n([\s\S]*?)```|\$\$([\s\S]*?)\$\$|\$([^\n$]+)\$|\*\*([^*\n]+)\*\*|`([^`\n]+)`|^#{1,6}[ \t]+([^\n]+)/gm
 let start=0
 for(const match of props.text.matchAll(expression)){
  if(match.index!>start)result.push({kind:'text',text:props.text.slice(start,match.index)})
  if(match[1]!==undefined)result.push({kind:'code',text:match[1].replace(/\n$/,'')})
  else if(match[4]!==undefined)result.push({kind:'strong',text:match[4]})
  else if(match[5]!==undefined)result.push({kind:'inline-code',text:match[5]})
  else if(match[6]!==undefined)result.push({kind:'heading',text:match[6]})
  else{
   try{result.push({kind:'math',text:match[0],display:match[2]!==undefined,html:katex.renderToString(match[2]??match[3]!,{displayMode:match[2]!==undefined,throwOnError:true,trust:false,strict:'ignore'})})}
   catch{result.push({kind:'text',text:match[0]})}
  }
  start=match.index!+match[0].length
 }
 if(start<props.text.length)result.push({kind:'text',text:props.text.slice(start)})
 return result
})
</script>
<template><div class="capture-study-message assistant"><template v-for="(piece,index) in pieces" :key="index"><pre v-if="piece.kind==='code'"><code>{{piece.text}}</code></pre><strong v-else-if="piece.kind==='strong'">{{piece.text}}</strong><code v-else-if="piece.kind==='inline-code'" class="study-inline-code">{{piece.text}}</code><h4 v-else-if="piece.kind==='heading'">{{piece.text}}</h4><span v-else-if="piece.kind==='math'" :class="{'study-display-math':piece.display}" v-html="piece.html"/><span v-else>{{piece.text}}</span></template></div></template>
