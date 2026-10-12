// Synthetic image only: verifies the loupe at text pixels and image edges, no saves/AI.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const b=await chromium.connectOverCDP('http://127.0.0.1:9223')
const pages=b.contexts()[0].pages(),main=pages.find(p=>p.url().includes('5174')&&!p.url().includes('desktop=')),capture=pages.find(p=>p.url().includes('desktop=capture'))
const invoke=(command,args)=>main.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})
const errors=[];capture.on('pageerror',e=>errors.push(e.message))
try{
 const asset=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=512;c.height=320;const g=c.getContext('2d');g.fillStyle='#2d7df2';g.fillRect(0,0,512,320);g.fillStyle='#fff';g.font='bold 48px Arial';g.fillText('SnapMind',80,130);return {id:'magnifier-test-'+Date.now(),name:'Magnifier fixture',data:c.toDataURL('image/png'),width:512,height:320,scenario:'custom'}})
 await invoke('begin_preview_capture',{asset})
 await capture.waitForFunction(id=>{const e=document.querySelector('.capture-overlay');return e?.dataset.sourceId===id&&e.dataset.ready==='true'},asset.id)
 async function point(x,y){
  await capture.evaluate(({x,y})=>{const c=document.querySelector('.capture-screen'),r=c.getBoundingClientRect();document.querySelector('.capture-overlay').dispatchEvent(new PointerEvent('pointermove',{bubbles:true,clientX:r.x+(x+.25)*r.width/c.width,clientY:r.y+(y+.25)*r.height/c.height}))},{x,y})
  await capture.locator('.capture-loupe').waitFor()
  await capture.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))
  const match=await capture.evaluate(({x,y})=>{const a=document.querySelector('.capture-screen').getContext('2d').getImageData(x,y,1,1).data,b=document.querySelector('.capture-loupe canvas').getContext('2d').getImageData(85,85,1,1).data;const r=document.querySelector('.capture-loupe').getBoundingClientRect();return {same:Array.from(a).every((v,i)=>v===b[i]),inside:r.left>=0&&r.top>=0&&r.right<=innerWidth&&r.bottom<=innerHeight,coords:document.querySelector('.capture-loupe-coordinates').textContent}},{x,y})
  assert.equal(match.same,true,`Magnified center must match original pixel ${x},${y}`);assert.equal(match.inside,true);assert.ok(match.coords.includes(`${x}, ${y}`))
 }
 await point(0,0);await point(511,319);await point(100,200)
 assert.equal(await capture.locator('.capture-loupe-coordinates small').innerText(),'3×')
 const text=await capture.evaluate(()=>{const c=document.querySelector('.capture-screen'),g=c.getContext('2d');for(let y=90;y<130;y++)for(let x=80;x<320;x++){if(Array.from(g.getImageData(x,y,1,1).data.slice(0,3)).every(v=>v===255))return {x,y}}throw Error('Missing fixture text')})
 await point(text.x,text.y)
 assert.equal(await capture.locator('.capture-loupe-color strong').innerText(),'#FFFFFF')
 const rect=await capture.locator('.capture-screen').boundingBox()
 await capture.mouse.move(rect.x+100,rect.y+100);await capture.mouse.down();await capture.mouse.move(rect.x+400,rect.y+300,{steps:5});await capture.mouse.up()
 await capture.locator('.capture-selection').waitFor()
 const style=await capture.locator('.capture-selection').evaluate(e=>({color:getComputedStyle(e).outlineColor,width:getComputedStyle(e).outlineWidth}))
 assert.deepEqual(style,{color:'rgb(132, 61, 255)',width:'2px'})
 assert.equal(await capture.locator('.capture-handle').count(),8)
 await capture.locator('.capture-top-controls button').dispatchEvent('pointermove')
 assert.equal(await capture.locator('.capture-loupe').count(),0,'Loupe must hide over controls')
 assert.deepEqual(errors,[])
 console.log('PASS: 3x text/pixel magnification, edge clamping, purple selection and eight handles; no screenshot saved or AI called.')
}finally{await invoke('cancel_capture').catch(()=>{});await b.close()}
