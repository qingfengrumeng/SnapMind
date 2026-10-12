import type {TextAttachment} from './types'
export function attachmentPrompt(prompt:string,attachments:TextAttachment[]){
 if(!attachments.length)return prompt
 return (prompt.trim()||'请阅读以下文本附件并帮助我分析内容。')+attachments.map(a=>'\n\n--- 文本附件：'+a.name+' ---\n'+a.content+'\n--- 附件结束 ---').join('')
}
export function attachmentBytes(content:string){const bytes=new TextEncoder().encode(content).length;return bytes>=1048576?(bytes/1048576).toFixed(1)+' MB':(bytes/1024).toFixed(1)+' KB'}
export function pastedAttachment(content:string):TextAttachment{
 const parts=new Intl.DateTimeFormat('sv-SE',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit',hour:'2-digit',minute:'2-digit',second:'2-digit',hour12:false}).format(new Date()).replace(/[ :]/g,'-')
 return {id:'text-'+crypto.randomUUID(),name:'粘贴内容-'+parts+'.txt',content}
}
