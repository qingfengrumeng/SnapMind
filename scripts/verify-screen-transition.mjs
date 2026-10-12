// Checks physical screen pixels at stripe boundaries while completing/cancelling capture.
// Fixture covers the desktop; only binary pixel classes are collected.
import {spawn} from 'node:child_process'
import {createInterface} from 'node:readline'
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const b=await chromium.connectOverCDP('http://127.0.0.1:9223')
const main=b.contexts()[0].pages().find(p=>p.url().includes('5174')&&!p.url().includes('desktop='))
const invoke=command=>main.evaluate(command=>window.__TAURI_INTERNALS__.invoke(command),command)
const original=(await invoke('native_status')).windows.main.visible
await main.evaluate(()=>window.__TAURI_INTERNALS__.invoke('hide_desktop_window'))
const fixture=spawn('python',['-u','scripts/capture-screen-fixture.py'],{windowsHide:true,stdio:['pipe','pipe','pipe']})
const frames=[], errors=[]
let phase='baseline'
const lines=createInterface({input:fixture.stdout})
lines.on('line',line=>frames.push({pixels:JSON.parse(line).pixels,phase}))
fixture.stderr.on('data',chunk=>errors.push(chunk.toString()))
try {
  for(let n=0;n<100&&!frames.length;n++)await new Promise(r=>setTimeout(r,30))
  assert.ok(frames.length,'Fixture must produce physical screen samples')
  const baseline=frames[0].pixels
  const begin=frames.length
  phase='completion'
  const child=spawn(process.execPath,['scripts/verify-capture-completion.mjs'],{windowsHide:true,env:{...process.env,SNAPMIND_SCREEN_TRACE:'1'},stdio:['ignore','pipe','pipe']})
  let output=''; child.stdout.on('data',data=>output+=data);child.stderr.on('data',data=>output+=data)
  const code=await new Promise(resolve=>child.on('exit',resolve))
  assert.equal(code,0,output)
  phase='capture-entry';await invoke('begin_capture')
  phase='capture-active'
  await new Promise(r=>setTimeout(r,250))
  phase='cancel-exit';await invoke('cancel_capture')
  phase='after-cancel'
  await new Promise(r=>setTimeout(r,250))
  const checked=frames.slice(begin),mismatches=checked.map((frame,index)=>({index,phase:frame.phase,points:frame.pixels.flatMap((bit,i)=>bit!==baseline[i]?[i]:[])})).filter(frame=>frame.points.length),changed=mismatches.length
  if(changed)console.log(JSON.stringify({physicalScreenFrames:checked.length,mismatches}))
  assert.deepEqual(errors,[])
  assert.ok(checked.length>=5,'Must sample multiple compositor frames')
  assert.equal(changed,0,'Stripe edges must not shift or disappear during capture entry/exit')
  console.log(JSON.stringify({physicalScreenFrames:checked.length,shiftedOrBlankFrames:changed,closeButtons:'PASS',completion:'PASS',cancel:'PASS'}))
} finally {
  fixture.stdin.end('\n')
  await invoke('cancel_capture').catch(()=>{})
  if(original)await invoke('show_launcher').catch(()=>{})
  await b.close()
}
