import type {Session,Scenario} from './types'
export const uid=()=>crypto.randomUUID()
export function newSession(scenario:Scenario='custom'):Session{
 const now=new Date().toISOString()
 return {id:uid(),title:'新的截图会话',scenario,assets:[],messages:[],formula:'',rows:[],createdAt:now,updatedAt:now,pinned:false}
}
export function withoutDemoData(session:Session):Session|undefined{
 const demo=session.messages.filter(message=>message.demo)
 if(demo.length&&session.messages.length===2&&session.scenario!=='custom')return undefined
 const value={...session,messages:session.messages.filter(message=>!message.demo)}
 if(!value.messages.some(message=>message.kind==='formula')&&value.formula===String.raw`\operatorname{Attention}(Q,K,V)=\operatorname{softmax}\!\left(\frac{QK^\top}{\sqrt{d_k}}\right)V`)value.formula=''
 if(!value.messages.some(message=>message.kind==='table')&&JSON.stringify(value.rows)===JSON.stringify([{label:'7 月',value:128},{label:'8 月',value:156},{label:'9 月',value:182}]))value.rows=[]
 return value
}
