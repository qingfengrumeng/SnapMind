import {spawn} from 'node:child_process'
import {resolve} from 'node:path'
import {mkdir,readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const targets=await(await fetch('http://127.0.0.1:9223/json/list')).json()
const target=targets.find(p=>p.type==='page'&&!p.url.includes('desktop='))
assert.ok(target,'SnapMind main window must be running')
const ws=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let id=0
await new Promise((resolve,reject)=>{ws.onopen=resolve;ws.onerror=reject})
ws.onmessage=e=>{const value=JSON.parse(e.data),entry=pending.get(value.id);if(entry){pending.delete(value.id);value.error?entry.reject(Error(value.error.message)):entry.resolve(value.result)}}
const send=(method,params)=>new Promise((resolve,reject)=>{const next=++id;pending.set(next,{resolve,reject});ws.send(JSON.stringify({id:next,method,params}))})
const directory=resolve('artifacts/usage-dashboard/native-repeat-'+Date.now());await mkdir(directory,{recursive:true})
const metrics={requests:3,inputTokens:300,outputTokens:90,totalTokens:390,cachedInputTokens:120,uncachedInputTokens:180,cacheInputTokens:300,cacheReportedRequests:3,cacheHitRate:40,unreportedRequests:0,unbucketedRequests:0}
const data={kind:'llm',range:{start:'2000-01-01',end:'2000-01-01',timezone:'Asia/Shanghai',granularity:'hour'},summary:metrics,models:[{model:'synthetic-repeat',...metrics}],trend:[{key:'2000-01-01T00:00',label:'00:00',...metrics}],modelTrends:[]}
try{
 for(const [i,outcome] of ['saved','saved','cancelled','saved'].entries()){
  const filename=resolve(directory,`export-${i+1}.zip`)
  const saving=send('Runtime.evaluate',{expression:`(async()=>{const m=await import('/src/usage-export.ts');return await m.downloadUsage(${JSON.stringify(data)})})()`,awaitPromise:true,returnByValue:true})
  const controlling=new Promise((resolve,reject)=>{
   const helper=spawn('python',['scripts/verify-save-dialog.py',filename,...(outcome==='cancelled'?['cancel']:[])],{windowsHide:true,stdio:['ignore','pipe','pipe']});let output=''
   helper.stdout.on('data',chunk=>output+=chunk);helper.stderr.on('data',chunk=>output+=chunk)
   helper.on('error',reject);helper.on('exit',code=>code===0?resolve(output):reject(Error(output)))
  })
  await controlling
  const result=await Promise.race([saving,new Promise((_,reject)=>setTimeout(()=>reject(Error('Native saving timed out')),15000))])
  if(result.exceptionDetails)throw Error(result.exceptionDetails.text)
  assert.equal(result.result.value,outcome)
  if(outcome==='saved'){const bytes=await readFile(filename);assert.equal(bytes.readUInt32LE(0),0x04034b50)}
 }
 console.log('PASS: Native ZIP saving twice, cancellation, and saving again. Synthetic data only, files under '+directory)
}finally{ws.close()}
process.exit(0)
