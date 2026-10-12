// Verify the updated native entry and toolbar using generated pixels only.
import assert from 'node:assert/strict'
import {connectNative,invoke,delay} from './native-cdp.mjs'
const page=await connectNative()
try{
 // A fresh document ensures temporary test imports don't reuse a previous fixture's module.
 await page.evaluate(()=>{setTimeout(()=>location.reload(),0);return true});await delay(1500)
 await invoke(page,'show_launcher')
 assert.equal(await page.evaluate(()=>!!document.querySelector('.launcher-chat-button,.standalone-image-chat')),false)
 await assert.rejects(()=>invoke(page,'show_workspace'))
 await assert.rejects(()=>invoke(page,'desktop_tool_action',{action:'workspace'}))
 const result=await page.evaluate(async()=>{
  const [{default:Overlay},{createApp,h}]=await Promise.all([import('/src/components/CaptureOverlay.vue'),import('/node_modules/.vite/deps/vue.js')])
  const canvas=document.createElement('canvas');canvas.width=800;canvas.height=500;const g=canvas.getContext('2d');g.fillStyle='#faf7ff';g.fillRect(0,0,800,500);g.fillStyle='#9c68dd';g.fillRect(50,50,100,80)
  const container=document.createElement('div');document.body.append(container)
  const finished=[]
  const app=createApp({render:()=>h(Overlay,{source:{id:'native-ai-entry-generated',name:'Generated test',data:canvas.toDataURL(),width:800,height:500,scenario:'custom'},initialSelection:true,onFinish:result=>finished.push(result)})});app.mount(container)
  const waitFor=async test=>{for(let i=0;i<100;i++){if(test())return;await new Promise(r=>setTimeout(r,100))}throw Error('Native fixture readiness timeout')}
  try{
   await waitFor(()=>container.querySelector('.capture-overlay')?.dataset.ready==='true')
   const ai=container.querySelector('.capture-ai-chat-button')
   const label=ai?.getAttribute('aria-label'),tooltip=ai?.dataset.tooltip,glyph=!!ai?.querySelector('svg.ai-chat-bubble-icon'),extraMenu=!!container.querySelector('.capture-all-tools-button,.capture-function-menu')
   const bounds=ai.getBoundingClientRect(),visible=bounds.left>=0&&bounds.right<=innerWidth,scroll=container.querySelector('[aria-label="滚动截图"]'),grouped=scroll.nextElementSibling?.getAttribute('aria-label')==='截图贴图'&&scroll.nextElementSibling?.nextElementSibling===ai&&ai.nextElementSibling?.classList.contains('capture-separator')
   ai.click();await waitFor(()=>container.querySelector('[aria-label="图片对话输入"]'))
   const input=container.querySelector('[aria-label="图片对话输入"]');input.value='/';input.focus();input.setSelectionRange(1,1);input.dispatchEvent(new Event('input',{bubbles:true}))
   await waitFor(()=>container.querySelectorAll('.image-tool-menu [role=option]').length===14)
   const count=container.querySelectorAll('.image-tool-menu [role=option]').length
   container.querySelector('.capture-conversation-panel>header button').click();await waitFor(()=>!container.querySelector('.capture-conversation-panel'))
   container.querySelector('[aria-label="保存截图"]').click();await waitFor(()=>finished.length>0)
   const directSave=finished.length===1&&finished[0].action==='save'&&finished[0].width===800&&finished[0].height===500&&finished[0].data.startsWith('data:image/png;base64,')&&!container.querySelector('.capture-tool-options')
   return {label,tooltip,glyph,extraMenu,visible,grouped,count,directSave}
  }finally{app.unmount();container.remove()}
 })
 assert.deepEqual(result,{label:'AI对话',tooltip:'AI对话',glyph:true,extraMenu:false,visible:true,grouped:true,count:14,directSave:true})
 console.log('PASS: native scroll/pin/AI group, tooltip, toggle, all 14 slash tools and direct save without options.')
}finally{await invoke(page,'show_launcher');page.close()}
