// Exercise the production screenshot window with generated pixels; never capture the desktop.
import assert from 'node:assert/strict'
import {mkdir,writeFile} from 'node:fs/promises'
import {connectNative,invoke,delay} from './native-cdp.mjs'
const main=await connectNative(),capture=await connectNative('capture')
const waitFor=async test=>{for(let i=0;i<100;i++){if(await test())return;await delay(100)}throw Error('Native capture readiness timeout')}
let started=false
try{
 assert.equal((await invoke(main,'native_status')).captureActive,false,'Finish the user capture before this check')
 const fixture=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=1600;c.height=900;const g=c.getContext('2d');g.fillStyle='#faf7ff';g.fillRect(0,0,c.width,c.height);g.fillStyle='#c7afe9';g.fillRect(90,100,300,180);return {id:'native-chat-icon-generated-'+Date.now(),name:'Generated icon check',data:c.toDataURL(),width:c.width,height:c.height,scenario:'custom'}})
 await capture.send('Page.reload',{ignoreCache:true})
 await waitFor(()=>capture.evaluate(()=>document.readyState==='complete'&&!!document.querySelector('#app')))
 await delay(600)
 await invoke(main,'begin_preview_capture',{asset:fixture});started=true
 await waitFor(()=>capture.evaluate(id=>document.querySelector('.capture-overlay')?.dataset.sourceId===id&&document.querySelector('.capture-overlay')?.dataset.ready==='true',fixture.id))
 const box=await capture.evaluate(()=>{const r=document.querySelector('.capture-screen').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height}})
 const start={x:box.x+box.w*.04,y:box.y+box.h*.06},end={x:box.x+box.w*.96,y:box.y+box.h*.83}
 await capture.send('Input.dispatchMouseEvent',{type:'mouseMoved',...start})
 await capture.send('Input.dispatchMouseEvent',{type:'mousePressed',...start,button:'left',buttons:1,clickCount:1})
 await capture.send('Input.dispatchMouseEvent',{type:'mouseMoved',...end,button:'left',buttons:1})
 await capture.send('Input.dispatchMouseEvent',{type:'mouseReleased',...end,button:'left',clickCount:1})
 await waitFor(()=>capture.evaluate(()=>!!document.querySelector('.capture-ai-chat-button')))
 const icon=await capture.evaluate(()=>{const b=document.querySelector('.capture-ai-chat-button'),svg=b.querySelector('svg');return {classes:svg.getAttribute('class'),outline:!!svg.querySelector('path[d]'),lines:[...svg.querySelectorAll('line')].map(l=>({length:Number(l.getAttribute('x2'))-Number(l.getAttribute('x1')),y:Number(l.getAttribute('y1'))})),tooltip:b.dataset.tooltip}})
 assert.ok(icon.classes.includes('ai-chat-bubble-icon'));assert.equal(icon.outline,true);assert.equal(icon.lines.length,3);assert.ok(icon.lines.every((l,i)=>l.length>0&&(!i||(l.length<icon.lines[i-1].length&&l.y>icon.lines[i-1].y))));assert.equal(icon.tooltip,'AI对话')
 const clip=await capture.evaluate(()=>{const r=document.querySelector('.capture-toolbar').getBoundingClientRect();return {x:r.x,y:r.y,width:r.width,height:r.height,scale:1}})
 const screenshot=await capture.send('Page.captureScreenshot',{format:'png',clip})
 await mkdir('artifacts/image-tools',{recursive:true});await writeFile('artifacts/image-tools/native-chat-icon.png',Buffer.from(screenshot.data,'base64'))
 console.log('PASS: actual desktop screenshot window shows the bubble and three unequal text lines; generated toolbar preview saved.')
}finally{if(started)await invoke(main,'cancel_capture');main.close();capture.close()}
