// Native WebView smoke check with a temporary generated image; never captures the desktop.
import assert from 'node:assert/strict'
import {connectNative,invoke} from './native-cdp.mjs'
const page=await connectNative()
try{
 const result=await page.evaluate(async()=>{
  const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')])
  const container=document.createElement('div');container.style.cssText='position:fixed;z-index:9999;left:20px;top:20px;width:min(480px,calc(100vw - 40px));height:min(620px,calc(100vh - 40px));background:white;border:1px solid #e5d6fa;border-radius:18px;overflow:hidden';document.body.append(container)
  const canvas=document.createElement('canvas');canvas.width=300;canvas.height=180;const g=canvas.getContext('2d');g.fillStyle='#fff';g.fillRect(0,0,300,180);g.fillStyle='#9c68dd';g.fillRect(40,40,70,50)
  const app=createApp(Chat,{initial:{id:'native-slash-generated',name:'Generated test',data:canvas.toDataURL(),width:300,height:180,scenario:'custom'}});app.mount(container)
  try{
   const input=container.querySelector('textarea[aria-label="图片对话输入"]');input.value='/';input.focus();input.setSelectionRange(1,1);input.dispatchEvent(new Event('input',{bubbles:true}))
   for(let i=0;i<80&&!container.querySelectorAll('[role=option]').length;i++)await new Promise(r=>setTimeout(r,100))
   const options=[...container.querySelectorAll('[role=option]')],menu=container.querySelector('.image-tool-menu'),box=menu?.getBoundingClientRect()
   const count=options.length,snapshot=options.some(o=>o.dataset.tool==='snapshot'),fits=!!box&&box.left>=0&&box.top>=0&&box.right<=innerWidth&&box.bottom<=innerHeight
   const note=container.querySelector('[data-tool=note]');note?.click();await new Promise(r=>setTimeout(r,100))
   return {count,snapshot,fits,selected:container.querySelector('.image-tool-selection>span')?.textContent,ready:!container.querySelector('[aria-label="发送图片对话"]')?.disabled}
  }finally{app.unmount();container.remove()}
 })
 assert.equal(result.count,21);assert.equal(result.snapshot,false);assert.equal(result.fits,true);assert.equal(result.selected,'图片笔记');assert.equal(result.ready,true)
 await invoke(page,'show_launcher')
 console.log('PASS: native WebView slash menu, all retained tools, panel bounds and selected-tool send; desktop is ready.')
}finally{page.close()}
