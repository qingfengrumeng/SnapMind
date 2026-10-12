import {connectNative,invoke,delay} from './native-cdp.mjs'
import {spawn} from 'node:child_process'
import assert from 'node:assert/strict'
const main=await connectNative(),capture=await connectNative('capture')
async function region(points){return new Promise((resolve,reject)=>{const p=spawn('python',['scripts/verify-preview-region.py'],{windowsHide:true,stdio:['pipe','pipe','pipe']});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);p.on('error',reject);p.on('exit',code=>code?reject(Error(err)):resolve(JSON.parse(out)));p.stdin.end(JSON.stringify({points}))})}
try{
 const asset=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=420;c.height=260;const g=c.getContext('2d');g.fillStyle='#eee7fa';g.fillRect(0,0,420,260);return {id:'synthetic-native-editor-'+Date.now(),name:'Synthetic editor verification',scenario:'custom',width:420,height:260,data:c.toDataURL('image/png')}})
 await invoke(main,'begin_preview_capture',{asset,floatingPreview:true})
 for(let i=0;i<100;i++){if(await capture.evaluate(id=>document.querySelector('.floating-preview-editor')?.dataset.sourceId===id&&document.querySelector('.capture-overlay')?.dataset.ready==='true',asset.id))break;await delay(100)}
 const info=await capture.evaluate(()=>{const root=document.querySelector('.floating-preview-editor'),image=root?.querySelector('.capture-screen')?.getBoundingClientRect(),bar=root?.querySelector('.capture-toolbar')?.getBoundingClientRect();return {exists:!!root,tools:root?.querySelectorAll('.capture-tools-scroll button').length,chrome:root?.querySelectorAll('.capture-top-controls,.capture-shade').length,image:image&&{x:image.x,y:image.y,w:image.width,h:image.height},bar:bar&&{x:bar.x,y:bar.y,w:bar.width,h:bar.height},ratio:devicePixelRatio}})
 assert.equal(info.exists,true);assert.equal(info.tools,24);assert.equal(info.chrome,0);assert.ok(info.bar.y>=info.image.y+info.image.h)
 await delay(300)
 const px=(x,y)=>[x*info.ratio,y*info.ratio]
 let clip=await region([px(2,2),px(info.image.x+info.image.w/2,info.image.y+info.image.h/2),px(info.bar.x+20,info.bar.y+20)])
 assert.ok(clip.kind>0);assert.deepEqual(clip.points,[false,true,true],'Transparent desktop space must be outside the native window region')
 await assert.rejects(invoke(main,'set_preview_regions',{id:asset.id,regions:[{x:0,y:0,width:20,height:20}]}))
 await assert.rejects(invoke(capture,'set_preview_regions',{id:asset.id,regions:[{x:-1,y:0,width:20,height:20}]}))
 const x=info.image.x+info.image.w/2,y=info.image.y+info.image.h/2
 await capture.send('Input.dispatchMouseEvent',{type:'mousePressed',x,y,button:'left',buttons:1,clickCount:1})
 await capture.send('Input.dispatchMouseEvent',{type:'mouseMoved',x:x+45,y:y+25,button:'left',buttons:1})
 await capture.send('Input.dispatchMouseEvent',{type:'mouseReleased',x:x+45,y:y+25,button:'left',buttons:0,clickCount:1})
 await delay(200)
 const moved=await capture.evaluate(()=>{const c=document.querySelector('.capture-screen'),r=c.getBoundingClientRect();return {x:r.x,y:r.y,width:c.width,height:c.height}})
 assert.ok(Math.abs(moved.x-info.image.x-45)<1);assert.ok(Math.abs(moved.y-info.image.y-25)<1);assert.equal(moved.width,420);assert.equal(moved.height,260)
 clip=await region([px(info.image.x,info.image.y+60),px(moved.x+30,moved.y+30)]);assert.deepEqual(clip.points,[false,true],'Native region must follow image movement')
 await invoke(capture,'cancel_capture');assert.equal((await invoke(main,'get_desktop_state')).captureActive,false)
 for(let i=0;i<100;i++){if(await capture.evaluate(()=>!document.querySelector('.capture-overlay')))break;await delay(50)}
 await invoke(main,'begin_preview_capture',{asset,floatingPreview:false})
 for(let i=0;i<100;i++){if(await capture.evaluate(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true'&&!document.querySelector('.floating-preview-editor')))break;await delay(100)}
 const restored=await region([px(20,20)])
 assert.ok(restored.kind===0||restored.points[0],'New screen captures must restore interaction outside the old image region: '+JSON.stringify(restored))
 assert.equal(await capture.evaluate(()=>document.querySelectorAll('.capture-selection').length),0)
 console.log('PASS: Native saved-image editor has all editing tools, moves its image and OS hit region together, leaves the surrounding desktop clickable, cancels cleanly and preserves normal capture. Synthetic data only; no saved records created.')
}finally{await invoke(capture,'cancel_capture').catch(()=>{});capture.close();main.close()}
