import {connectNative,invoke,delay} from './native-cdp.mjs'
import {mkdir,readFile,writeFile,rm} from 'node:fs/promises'
import {spawn} from 'node:child_process'
import {resolve} from 'node:path'
import assert from 'node:assert/strict'
const output=resolve('artifacts/image-tools/native');await mkdir(output,{recursive:true})
await rm(resolve(output,'fixture.json'),{force:true});await rm(resolve(output,'command.json'),{force:true})
const fixture=spawn('python',['scripts/windows-control-fixture.py','--output',output],{windowsHide:true,stdio:'ignore'})
let capture,main
try{
 let info;for(let i=0;i<100;i++){try{info=JSON.parse(await readFile(resolve(output,'fixture.json'),'utf8'));break}catch{}await delay(100)}assert.ok(info,'Generated control fixture unavailable')
 await delay(500);main=await connectNative();await invoke(main,'begin_capture');capture=await connectNative('capture')
 const state=await invoke(capture,'get_desktop_state'),frame=state.frame,args={id:frame.asset.id,x:info.x-frame.x,y:info.y-frame.y,width:info.width,height:info.height}
 for(let i=0;i<100;i++){if(await capture.evaluate(id=>{const el=document.querySelector('.capture-overlay');return el?.dataset.ready==='true'&&el.dataset.sourceId===id},frame.asset.id))break;await delay(100)}
 const controls=await invoke(capture,'capture_control_targets',args),input=controls.find(c=>c.controlType==='Edit'&&c.text==='Username');console.log('Frozen fixture controls:',controls.map(c=>({name:c.text,type:c.controlType,bbox:c.bbox})));assert.ok(input)
 for(const action of ['window','fill','snapshot-start','snapshot-next','snapshot-restore','snapshot-frame'])await assert.rejects(invoke(capture,'capture_image_action',{...args,request:{action}}),'Removed operation must be unsupported')
 await assert.rejects(invoke(capture,'capture_image_action',{...args,request:{action:'video'}}),'unsupported action')
 await assert.rejects(invoke(main,'export_image_note',{assets:[],text:''}),'Removed note command must be unavailable')
 await invoke(capture,'cancel_capture')
 await invoke(main,'copy_table_content',{text:'Code\tValue\n001\t0',html:'<table><tr><td>Code</td><td>Value</td></tr><tr><td style="mso-number-format:\\@">001</td><td>0</td></tr></table>'})
 const clip=await new Promise((resolve,reject)=>{const p=spawn('python',['scripts/read-test-clipboard.py'],{windowsHide:true,stdio:['ignore','pipe','pipe']});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);p.on('exit',code=>code?reject(Error(err)):resolve(JSON.parse(out)))})
 assert.equal(clip.text,'Code\tValue\n001\t0');assert.ok(clip.html.includes('001')&&clip.html.includes('StartFragment:'))
 const results={windowScreenshotRemoved:true,memoryFillRemoved:true,applicationSnapshotRemoved:true,imageNoteRemoved:true,imageOnlyActionWhitelist:true,clipboardText:true,clipboardHtml:true}
 await writeFile(resolve(output,'results.json'),JSON.stringify(results,null,2));console.log('PASS:',results)
}finally{if(capture)await invoke(capture,'cancel_capture').catch(()=>{});capture?.close();main?.close();await writeFile(resolve(output,'command.json'),JSON.stringify({action:'close'}));await delay(250);if(fixture.exitCode===null)fixture.kill()}
