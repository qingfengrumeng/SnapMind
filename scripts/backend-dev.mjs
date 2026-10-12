// Poll only Python source files; Windows watcher permissions must not leave an old API running.
import {spawn} from 'node:child_process'
import {readdir,readFile} from 'node:fs/promises'
import {existsSync} from 'node:fs'
import {resolve} from 'node:path'
import {createHash} from 'node:crypto'
const root=resolve(import.meta.dirname,'..'),source=resolve(root,'backend/app')
const port=Number(process.argv[2]||8776)
if(!Number.isInteger(port)||port<1||port>65535)throw Error('Invalid backend development port')
const python=existsSync(resolve(root,'.venv/Scripts/python.exe'))?resolve(root,'.venv/Scripts/python.exe'):'python'
let child,stopping=false,restarting=false,polling=false,timer
async function sourceHash(directory=source){const items=await readdir(directory,{withFileTypes:true});const hash=createHash('sha256');for(const item of items.sort((a,b)=>a.name.localeCompare(b.name))){if(item.isDirectory()&&item.name!=='__pycache__'&&!item.name.startsWith('.'))hash.update(await sourceHash(resolve(directory,item.name)));else if(item.isFile()&&item.name.endsWith('.py')){hash.update(item.name);hash.update(await readFile(resolve(directory,item.name)))}}return hash.digest('hex')}
function stop(code=0){if(stopping)return;stopping=true;clearInterval(timer);child?.kill();process.exit(code)}
function start(){child=spawn(python,['-m','uvicorn','backend.app.main:app','--host','127.0.0.1','--port',String(port)],{cwd:root,windowsHide:true,stdio:'inherit',env:{...process.env,PYTHONUNBUFFERED:'1'}});child.on('error',e=>{console.error('Python backend: '+e.message);stop(1)});child.on('exit',code=>{if(!stopping&&!restarting){console.error('Python backend stopped: '+code);stop(code||1)}})}
let previous=await sourceHash();start()
timer=setInterval(async()=>{if(stopping||polling||restarting)return;polling=true;try{const next=await sourceHash();if(next!==previous){previous=next;restarting=true;console.log('Python source changed. Restarting local API…');const exited=new Promise(r=>child.once('exit',r));child.kill();await exited;if(!stopping){start();restarting=false}}}catch(e){console.error('Python source check: '+e.message)}finally{polling=false}},800)
process.on('SIGINT',()=>stop());process.on('SIGTERM',()=>stop());process.on('exit',()=>{child?.kill()})
