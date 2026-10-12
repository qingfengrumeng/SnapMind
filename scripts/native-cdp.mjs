export const delay=ms=>new Promise(r=>setTimeout(r,ms))
export async function connectNative(role='main'){
 const pages=await(await fetch('http://127.0.0.1:9223/json/list')).json(),target=pages.find(p=>p.type==='page'&&p.url.startsWith('http://127.0.0.1:5174')&&(role==='main'?!p.url.includes('desktop='):p.url.includes('desktop='+role)))
 if(!target)throw Error('Native page missing: '+role)
 const socket=new WebSocket(target.webSocketDebuggerUrl),pending=new Map();let id=0
 await new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true})})
 socket.addEventListener('message',e=>{const m=JSON.parse(e.data),p=pending.get(m.id);if(p){pending.delete(m.id);clearTimeout(p.timer);m.error?p.reject(Error(JSON.stringify(m.error))):p.resolve(m.result)}})
 const send=(method,params={})=>{const n=++id;return new Promise((resolve,reject)=>{const timer=setTimeout(()=>{pending.delete(n);reject(Error('Native command timeout: '+method))},60000);pending.set(n,{resolve,reject,timer});socket.send(JSON.stringify({id:n,method,params}))})}
 return {close:()=>socket.close(),send,async evaluate(fn,arg){const expression=`(${fn.toString()})(${JSON.stringify(arg)})`;const result=await send('Runtime.evaluate',{expression,awaitPromise:true,returnByValue:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}}
}
export const invoke=(page,command,args={})=>page.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})
