// localStorage remains the fast UI cache; the local API owns the durable copy.
import {native} from './desktop'
const base=native&&!/^https?:$/.test(location.protocol)?'http://127.0.0.1:8776/api':'/api'
const pending:Record<string,string|null>={}
let timer:ReturnType<typeof setTimeout>|undefined,saving=false
const managed=(key:string)=>key.startsWith('snapmind-')&&key!=='snapmind-sessions'&&key!=='snapmind-models-changed'
async function flush(){
 if(saving)return
 const changes={...pending};if(!Object.keys(changes).length)return
 for(const key of Object.keys(changes))delete pending[key]
 saving=true
 try{const response=await fetch(base+'/settings/preferences',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(changes),signal:AbortSignal.timeout(8000)});if(!response.ok)throw new Error('preferences write failed')}
 catch{for(const [key,value] of Object.entries(changes))if(!(key in pending))pending[key]=value}
 finally{saving=false;if(Object.keys(pending).length)timer=setTimeout(flush,3000)}
}
export async function restoreLocalPreferences(){
 const set=Storage.prototype.setItem,remove=Storage.prototype.removeItem
 try{
  const response=await fetch(base+'/settings/preferences',{signal:AbortSignal.timeout(3000)})
  if(response.ok){
   const stored:Record<string,string>=await response.json()
   for(const [key,value] of Object.entries(stored))if(managed(key)&&typeof value==='string'){
    const oldValue=localStorage.getItem(key);set.call(localStorage,key,value)
    window.dispatchEvent(new StorageEvent('storage',{key,oldValue,newValue:value,storageArea:localStorage}))
   }
   for(let i=0;i<localStorage.length;i++){const key=localStorage.key(i)!;if(managed(key)&&!(key in stored))pending[key]=localStorage.getItem(key)}
  }
 }catch{/* Retain the cache and retry writes after the API becomes available. */}
 Storage.prototype.setItem=function(key,value){set.call(this,key,value);if(this===localStorage&&managed(key)){pending[key]=value;clearTimeout(timer);timer=setTimeout(flush,300)}}
 Storage.prototype.removeItem=function(key){remove.call(this,key);if(this===localStorage&&managed(key)){pending[key]=null;clearTimeout(timer);timer=setTimeout(flush,300)}}
 window.addEventListener('storage',event=>{if(event.key&&managed(event.key)){pending[event.key]=event.newValue;clearTimeout(timer);timer=setTimeout(flush,300)}})
 if(Object.keys(pending).length)timer=setTimeout(flush,300)
}
