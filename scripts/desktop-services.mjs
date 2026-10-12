import { spawn,spawnSync } from 'node:child_process'
import { resolve } from 'node:path'
const root=resolve(import.meta.dirname,'..'),children=[]
function run(name,command,args,env={}){const child=spawn(command,args,{cwd:root,windowsHide:true,stdio:'inherit',env:{...process.env,...env}});children.push(child);child.on('error',e=>{console.error(name+': '+e.message);stop(1)});child.on('exit',code=>{if(!stopping){console.error(name+' stopped: '+code);stop(code||1)}});return child}
let stopping=false
function stop(code=0){if(stopping)return;stopping=true;for(const child of children){if(child.pid){if(process.platform==='win32')spawnSync('taskkill',['/PID',String(child.pid),'/T','/F'],{windowsHide:true,stdio:'ignore'});else child.kill('SIGTERM')}}process.exit(code)}
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());process.on('exit',()=>{if(!stopping)stop()})
for(const port of [5174,8776]){try{const r=await fetch('http://127.0.0.1:'+port,{signal:AbortSignal.timeout(500)});console.error('端口 '+port+' 已被使用，请先关闭旧的 SnapMind 桌面开发进程。');process.exit(1)}catch(e){if(e.name!=='TypeError'&&e.name!=='TimeoutError')throw e}}
console.log('SnapMind desktop dev: Python 8776 + Vite 5174. No installer is generated.')
run('Python',process.execPath,['scripts/backend-dev.mjs','8776'],{PYTHONUNBUFFERED:'1'})
run('Vite',process.execPath,['node_modules/vite/bin/vite.js','frontend','--host','127.0.0.1','--port','5174','--strictPort'],{SNAPMIND_BACKEND_PORT:'8776'})
