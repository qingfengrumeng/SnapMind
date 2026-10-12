// Join VAD fragments when speech resumes before the turn is committed.
export function isSpeechFiller(value:string){
 const text=value.replace(/[\s\p{P}\p{S}]/gu,'').toLowerCase()
 return !text||/^[嗯呃啊哦唔]+$/.test(text)||/^(?:u+h+|u+m+|h+m+)+$/.test(text)
}
export function createSpeechTurns(onTurn:(text:string)=>void,waitMs=450){
 let fragments:string[]=[],timer:ReturnType<typeof setTimeout>|undefined
 const text=()=>fragments.join(' ')
 function speechStarted(){clearTimeout(timer);timer=undefined}
 function push(value:string){
  const segment=value.trim();if(!segment)return
  fragments.push(segment);clearTimeout(timer)
  timer=setTimeout(()=>{const result=text();fragments=[];timer=undefined;if(result&&!isSpeechFiller(result))onTurn(result)},waitMs)
 }
 function reset(){clearTimeout(timer);timer=undefined;fragments=[]}
 return {text,speechStarted,push,reset}
}
