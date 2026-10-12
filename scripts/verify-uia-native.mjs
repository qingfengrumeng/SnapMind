// Real UIA/PNG consistency test, confined to a generated WinForms fixture.
import assert from 'node:assert/strict'
import {readFile,writeFile,mkdir,rm} from 'node:fs/promises'
import {spawn} from 'node:child_process'
import {resolve} from 'node:path'
const output=resolve('artifacts/uia-grounding'),delay=ms=>new Promise(r=>setTimeout(r,ms))
await mkdir(output,{recursive:true})
await rm(resolve(output,'command.json'),{force:true});await rm(resolve(output,'fixture.json'),{force:true})
const fixture=spawn('python',['scripts/windows-control-fixture.py','--output',output],{windowsHide:true,stdio:['ignore','ignore','pipe']})
let fixtureError='';fixture.stderr.on('data',d=>fixtureError+=d)
let capture,main;const sessions=[]
async function connect(target){
 const socket=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let id=0
 await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})})
 socket.addEventListener('message',event=>{const m=JSON.parse(event.data),p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}})
 const session={close:()=>socket.close(),async evaluate(fn,arg){const n=++id,expression=`(${fn.toString()})(${JSON.stringify(arg)})`;const result=await new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(n);reject(Error('CDP timeout'))},20000);pending.set(n,{resolve,reject,timer});socket.send(JSON.stringify({id:n,method:'Runtime.evaluate',params:{expression,awaitPromise:true,returnByValue:true}}))});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}}
 sessions.push(session);return session
}
async function ready(){for(let i=0;i<100;i++){if(await capture.evaluate(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true'))return;await delay(100)}throw Error('Capture not ready')}
const invoke=(page,command,args={})=>page.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})
try{
 let info
 for(let i=0;i<150;i++){try{info=JSON.parse(await readFile(resolve(output,'fixture.json'),'utf8'));break}catch{}if(fixture.exitCode!==null)throw Error(fixtureError);await delay(100)}
 assert.ok(info,'Fixture not ready: '+fixtureError)
 const raw=await new Promise((done,reject)=>{const child=spawn('python',['backend/app/windows_uia.py'],{windowsHide:true,stdio:['pipe','pipe','pipe']});let out='',err='';child.stdout.on('data',d=>out+=d);child.stderr.on('data',d=>err+=d);child.on('exit',code=>code===0?done(JSON.parse(out)):reject(Error(err)));child.stdin.end(JSON.stringify({...info,excludePid:0}))})
 assert.ok(raw.some(c=>c.text==='Save')&&raw.some(c=>c.text==='Username'),'Generated fixture must be visible before capture')
 const pages=(await(await fetch('http://127.0.0.1:9223/json/list')).json()).filter(p=>p.type==='page'&&p.url.startsWith('http://127.0.0.1:5174'))
 const captureTarget=pages.find(p=>p.url.includes('desktop=capture')),mainTarget=pages.find(p=>!p.url.includes('desktop='))
 assert.ok(captureTarget&&mainTarget,'Native targets missing');capture=await connect(captureTarget);main=await connect(mainTarget)
 assert.ok(capture&&main,'Native windows missing')
 await invoke(main,'begin_capture');await ready()
 const state=await invoke(capture,'get_desktop_state'),f=state.frame
 const rect={id:f.asset.id,x:info.x-f.x,y:info.y-f.y,width:info.width,height:info.height}
 const started=performance.now(),controls=await invoke(capture,'capture_control_targets',rect),elapsed=performance.now()-started
 await capture.evaluate(async({rect})=>{const c=document.querySelector('.capture-screen'),cropped=document.createElement('canvas');cropped.width=rect.width;cropped.height=rect.height;cropped.getContext('2d').drawImage(c,rect.x,rect.y,rect.width,rect.height,0,0,rect.width,rect.height);window.uiaFixturePng=cropped.toDataURL()}, {rect})
 const png=await capture.evaluate(()=>window.uiaFixturePng);await writeFile(resolve(output,'fixture.png'),Buffer.from(png.split(',')[1],'base64'))
 const expected=info.expected.map(e=>({...e,bbox:e.bbox.map((v,i)=>v-(i%2?info.y:info.x))}))
 function iou(a,b){const area=r=>(r[2]-r[0])*(r[3]-r[1]),intersection=Math.max(0,Math.min(a[2],b[2])-Math.max(a[0],b[0]))*Math.max(0,Math.min(a[3],b[3])-Math.max(a[1],b[1]));return intersection/(area(a)+area(b)-intersection)}
 const matches=expected.map(e=>{const candidates=controls.filter(c=>c.text===e.text||c.text===e.display);const score=Math.max(0,...candidates.map(c=>iou(e.bbox,c.bbox)));return {text:e.text||e.display,iou:score}})
 assert.equal(matches.length,5);assert.ok(matches.every(m=>m.iou>.97),JSON.stringify({raw,controls,matches,elapsed,rect,frameId:f.asset.id}))
 assert.ok(!JSON.stringify(controls).includes('Synthetic example'),'Input ValuePattern must not be read')
 await writeFile(resolve(output,'command.json'),JSON.stringify({action:'rename'}));await delay(500)
 const changed=await invoke(capture,'capture_control_targets',rect)
 assert.ok(!changed.some(c=>c.text==='Changed'||c.text==='Save'),'Changed control must not correct the frozen image')
 assert.ok(changed.some(c=>c.text==='Cancel'),'Unchanged controls remain usable')
 await writeFile(resolve(output,'command.json'),JSON.stringify({action:'move'}));await delay(500)
 const moved=await invoke(capture,'capture_control_targets',rect)
 assert.ok(!moved.some(c=>c.text==='Changed'||c.text==='Cancel'),'Moved window must not reuse live bounds')
 await invoke(capture,'cancel_capture')
 const preview={id:'uploaded-uia-test',name:'Uploaded synthetic fixture',data:png,width:rect.width,height:rect.height,scenario:'custom'}
 await invoke(main,'begin_preview_capture',{asset:preview});await ready()
 assert.deepEqual(await invoke(capture,'capture_control_targets',{id:preview.id,x:0,y:0,width:preview.width,height:preview.height}),[])
 const result={passed:true,controls:controls.length,matches,meanIoU:matches.reduce((s,m)=>s+m.iou,0)/matches.length,latencyMs:Math.round(elapsed),changedControlRejected:true,movedWindowRejected:true,uploadedImageRejected:true,inputValueNotRead:true}
 await writeFile(resolve(output,'results.json'),JSON.stringify(result,null,2));console.log(JSON.stringify(result))
}finally{
 if(capture)await invoke(capture,'cancel_capture').catch(()=>{})
 await writeFile(resolve(output,'command.json'),JSON.stringify({action:'close'}))
 for(const session of sessions)session.close()
 await Promise.race([new Promise(r=>fixture.once('exit',r)),delay(1500)])
 if(fixture.exitCode===null)fixture.kill()
}
