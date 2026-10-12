// Isolated browser fixtures and local image algorithms. Never attaches to desktop WebViews.
import {spawn,spawnSync} from 'node:child_process'
import {mkdir,writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'
const root=resolve(import.meta.dirname,'..'),folder=resolve(root,'artifacts/regression')
await mkdir(folder,{recursive:true})
const names=process.argv.slice(2)
const resultFile=names.length?'ui-recheck-results.json':'ui-results.json'
const defaults=['speech-turns','scroll-stitch','no-demo','asr','speech','voice-messages','voice-call','voice-call-stream','chat-messages','chat-composer','chat-layout','image-history','text-attachments','model-profiles','ocr-settings','usage-dashboard','ai-chat-entry','capture-dropdowns','capture-idle','content-brushes','conversation-detection','conversation-edits','image-tools','inline-translation','movable-annotations','saved-image-editor','slash-tools','tool-shortcuts','function-guide']
const queue=[...(names.length?names:defaults)],results=[]
async function run(name){
 const started=Date.now(),child=spawn(process.execPath,['scripts/verify-'+name+'.mjs'],{cwd:root,windowsHide:true,stdio:['ignore','pipe','pipe'],env:{...process.env,SNAPMIND_UI_URL:'http://127.0.0.1:5174'}});let output='',expired=false
 for(const stream of [child.stdout,child.stderr])stream.on('data',data=>output+=data.toString())
 const timer=setTimeout(()=>{expired=true;if(process.platform==='win32')spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});else child.kill()},150000)
 const code=await new Promise(resolve=>{child.on('error',error=>{output+=error.message;resolve(-1)});child.on('exit',resolve)})
 clearTimeout(timer);await writeFile(resolve(folder,name+'.log'),output)
 const result={name,status:code===0?'passed':expired?'timeout':'failed',seconds:Math.round((Date.now()-started)/100)/10,code}
 results.push(result);await writeFile(resolve(folder,resultFile),JSON.stringify(results,null,2))
 console.log(result.status.toUpperCase()+' '+name+' '+result.seconds+'s')
 if(code!==0)console.log(output.slice(-1800))
}
async function worker(){while(queue.length)await run(queue.shift())}
await Promise.all([worker(),worker()])
console.log(JSON.stringify({passed:results.filter(r=>r.status==='passed').length,failed:results.filter(r=>r.status!=='passed').length,total:results.length}))
if(results.some(r=>r.status!=='passed'))process.exitCode=1
