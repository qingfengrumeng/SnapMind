// Real continuous ASR, real agent/tools, real streaming TTS and MSE playback.
// Generated speech/images only; never opens a microphone or saves a session.
import {chromium} from 'playwright'
import {mkdir,writeFile} from 'node:fs/promises'
if(!process.argv.includes('--cloud'))throw Error('Pass --cloud to use the configured speech/LLM models with synthetic inputs.')
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=no-user-gesture-required']})
try{
 const page=await browser.newPage();const errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/src/main.ts',r=>r.fulfill({contentType:'application/javascript',body:''}))
 await page.goto('http://127.0.0.1:5174')
 const selectedCases=(process.argv.find(v=>v.startsWith('--cases='))||'').slice(8).split(',').filter(Boolean)
 const output=process.argv.find(v=>v.startsWith('--output='))?.slice(9)||'artifacts/agent-query-optimized/voice-results.json'
 const rows=await page.evaluate(async(selectedCases)=>{
  const [{api},{useSpeechPlayer},{createApp,h},{applyImageResult,annotationEdits,renderAnnotations},{createSpeechTurns}]=await Promise.all([import('/src/api.ts'),import('/src/speech-player.ts'),import('/node_modules/.vite/deps/vue.js'),import('/src/image-actions.ts'),import('/src/speech-turns.ts')])
  let player,playerError='',ended
  const host=document.createElement('div');document.body.append(host)
  const app=createApp({setup(){player=useSpeechPlayer(e=>{playerError=e;ended?.()},()=>ended?.());return ()=>h('span',player.state.value)}});app.mount(host)
  const c=document.createElement('canvas');c.width=760;c.height=430;const g=c.getContext('2d');g.fillStyle='white';g.fillRect(0,0,c.width,c.height);g.fillStyle='black';g.font='28px Microsoft YaHei'
  for(const [text,x,y] of [['订单汇总',30,55],['商品',30,120],['数量',330,120],['单价',520,120],['键盘',30,176],['2',330,176],['100.00',520,176],['鼠标',30,232],['1',330,232],['50.00',520,232],['邮箱 support@example.com',30,315]])g.fillText(text,x,y)
  for(const y of [80,136,192,248]){g.strokeStyle='#999';g.beginPath();g.moveTo(20,y);g.lineTo(720,y);g.stroke()}
  let asset={id:'generated-voice-query',name:'Generated order screenshot',data:c.toDataURL(),width:c.width,height:c.height,scenario:'custom'},annotations=[],history=[],undo=[]
  const ws=new WebSocket('ws://127.0.0.1:5174/api/speech/recognize?continuous=true')
  let current,readyResolve,readyReject,rate=16000
  const joiner=createSpeechTurns(text=>{if(current){current.resolve({text,partial:current.partial,at:performance.now()});current=null}})
  const ready=new Promise((resolve,reject)=>{readyResolve=resolve;readyReject=reject})
  ws.onmessage=event=>{const data=JSON.parse(event.data),now=performance.now();if(data.type==='ready'){rate=data.sampleRate;readyResolve()}else if(data.type==='error'){const error=Error(data.message);current?.reject(error);readyReject(error)}else if(current&&data.type==='transcript'&&!data.confirmed&&current.partial===null)current.partial=now;else if(data.type==='speech-started'){joiner.speechStarted()}else if(current&&data.type==='utterance'){joiner.push(data.text)}}
  ws.onerror=()=>{const error=Error('ASR WebSocket error');current?.reject(error);readyReject(error)}
  await ready
  async function recognize(text){
   const prep=performance.now(),response=await api.synthesize(text,AbortSignal.timeout(120000))
   const context=new AudioContext(),decoded=await context.decodeAudioData(await response.arrayBuffer());await context.close()
   const offline=new OfflineAudioContext(1,Math.ceil(decoded.duration*rate),rate),source=offline.createBufferSource();source.buffer=decoded;source.connect(offline.destination);source.start();const samples=(await offline.startRendering()).getChannelData(0)
   const start=performance.now();let timer
   const result=new Promise((resolve,reject)=>{current={resolve,reject,partial:null};timer=setTimeout(()=>{current=null;reject(Error('ASR utterance timeout'))},25000)})
   const upload=(async()=>{const pcm=new Float32Array(samples.length+rate*1.2);pcm.set(samples);for(let offset=0;offset<pcm.length;offset+=rate/10){const slice=pcm.subarray(offset,offset+rate/10),bytes=new ArrayBuffer(slice.length*2),v=new DataView(bytes);slice.forEach((n,i)=>v.setInt16(i*2,Math.round(Math.max(-1,Math.min(1,n))*(n<0?32768:32767)),true));ws.send(bytes);await new Promise(r=>setTimeout(r,100))}})()
   try{const recognition=await result;return {...recognition,upload,start,inputAudioSeconds:decoded.duration,prepSeconds:(start-prep)/1000}}
   finally{clearTimeout(timer)}
  }
  const cases=[['ocr','请提取截图中的全部文字。',['ocr','offline']],['highlight','请高亮截图中的订单汇总。',['highlight']],['undo_highlight','请撤销刚才的高亮操作。',['restore_image']],['translate','请把截图里的文字原位翻译成英文。',['translate']],['table','请提取截图中的表格。',['table']],['crop','把标题那一行裁剪出来。',['crop']],['undo_crop','撤销刚才的裁剪。',['restore_image']],['ambiguous','帮我处理一下这张截图。',[]]]
  const rows=[];window.queryImages=[]
  for(const [name,input,expected] of cases){
   if(selectedCases.length&&!selectedCases.includes(name))continue
   player.stop();playerError='';let recognition,result,error,firstText=null,firstAudio=null,firstPlaying=null,ttsStart=null,ttsDone=null,packets=0,spoken='',pending='',speechPromise,watcher,agentEnd
   try{
    recognition=await recognize(input);const agentStart=performance.now();let toolEvents=[]
    const startSpeech=text=>{
     if(speechPromise||!text.trim())return
     spoken=text.trim();ttsStart=performance.now();watcher=setInterval(()=>{if(firstPlaying===null&&player.state.value==='playing')firstPlaying=performance.now()},5)
     speechPromise=player.play(async signal=>{
      const response=await api.synthesize(spoken,signal),reader=response.body.getReader()
      const body=new ReadableStream({async pull(controller){const block=await reader.read();if(block.done){ttsDone=performance.now();controller.close();return}if(firstAudio===null)firstAudio=performance.now();packets++;controller.enqueue(block.value)},cancel(){return reader.cancel()}})
      return new Response(body,{headers:{'Content-Type':'audio/mpeg'}})
     })
    }
    const previous=undo.at(-1)
    result=await api.imageConversation([asset],asset.id,recognition.text,history,annotations,AbortSignal.timeout(240000),undefined,'zh-CN',[],undefined,undefined,text=>{
     if(firstText===null)firstText=performance.now();pending+=text
     const match=/^[\s\S]*?[。！？!?\n]|^[\s\S]{80}/.exec(pending)
     if(match)startSpeech(match[0])
    },event=>{if(event.type==='tool_result')toolEvents.push({name:event.name,seconds:(performance.now()-agentStart)/1000})},undefined,previous?{asset:previous.asset,annotations:previous.annotations}:undefined)
    agentEnd=performance.now();if(!speechPromise)startSpeech(result.answer.slice(0,80))
    await speechPromise;await new Promise(r=>setTimeout(r,100));clearInterval(watcher)
    const actions=(result.steps?.length?result.steps:[result]).map(s=>s.action),highlighted=name==='highlight'&&result.steps?.some(s=>s.action==='annotate'&&s.payload.annotations?.some(a=>a.kind==='highlight')),checks={recognized:!!recognition.text,intent:expected.length?!!highlighted||expected.some(a=>actions.includes(a)):!actions.some(a=>['translate','crop','annotate','highlight','mosaic','blur'].includes(a)),reply:!!result.answer,audio:packets>1&&firstPlaying!==null&&!playerError}
    const expectedRestore=previous?.asset.data
    if(name==='translate'){
     const lines=(result.steps||[]).filter(s=>s.action==='translate').flatMap(s=>s.payload.lines||[])
     checks.quantity_translated=lines.some(l=>l.sourceText.replace(/\s/g,'')==='数量'&&/quantity|count|qty/i.test(l.text))
     checks.all_headers_translated=['商品','数量','单价'].every(header=>lines.some(l=>l.sourceText.replace(/\s/g,'')===header&&!/[\u4e00-\u9fff]/.test(l.text)))
    }
    for(const step of result.steps||[]){
     if(step.action==='restore_image'){
      const saved=undo.pop();if(!saved)throw Error('Undo lacks prior snapshot');checks.undo_pixels=step.payload.data===saved.asset.data
      asset={...saved.asset,...step.payload};annotations=step.payload.annotations||[]
     }else if(step.action==='annotate'){
      undo.push({asset:{...asset},annotations:structuredClone(annotations)});annotations=annotationEdits(annotations,step.payload);await renderAnnotations(asset,annotations)
     }else{
      const rendered=await applyImageResult(asset,step)
      if(rendered){undo.push({asset:{...asset},annotations:structuredClone(annotations)});asset=rendered;annotations=[]}
     }
    }
    history.push({role:'user',text:recognition.text},{role:'assistant',text:result.answer.slice(0,2500)});history=history.slice(-18)
    window.queryImages.push({name,data:(await renderAnnotations(asset,annotations)).data})
    const seconds=t=>t===null||t===undefined?null:Number(((t-recognition.start)/1000).toFixed(3))
    const row={case:name,input,recognized:recognition.text,passed:Object.values(checks).every(Boolean),checks,actions,toolEvents,spokenFirstSegment:spoken,reply:result.answer,timing:{inputAudioSeconds:Number(recognition.inputAudioSeconds.toFixed(3)),syntheticInputPreparationSeconds:Number(recognition.prepSeconds.toFixed(3)),asrFirstPartialSeconds:seconds(recognition.partial),asrUtteranceSeconds:seconds(recognition.at),agentSeconds:Number(((agentEnd-agentStart)/1000).toFixed(3)),firstTextFromSpeechStartSeconds:seconds(firstText),ttsFirstPacketSeconds:firstAudio===null?null:Number(((firstAudio-ttsStart)/1000).toFixed(3)),firstAudibleFromSpeechStartSeconds:seconds(firstPlaying),afterSpeechEndsToAudibleSeconds:firstPlaying===null?null:Number(((firstPlaying-recognition.start)/1000-recognition.inputAudioSeconds).toFixed(3)),audioPackets:packets,firstSegmentStreaming:firstPlaying!==null&&firstPlaying<ttsDone}}
    row.outputs=(result.steps||[]).map(s=>({action:s.action,payload:JSON.parse(JSON.stringify(s.payload,(key,value)=>key==='data'?undefined:value))}))
    rows.push(row)
   }catch(e){clearInterval(watcher);rows.push({case:name,input,recognized:recognition?.text,passed:false,error:e.message})}
   if(recognition?.upload)await recognition.upload;player.stop();await new Promise(r=>setTimeout(r,100))
  }
  ws.send(JSON.stringify({type:'cancel'}));ws.close();app.unmount();host.remove()
  return {rows,asrConnections:1,microphoneUsed:false,speechOutputMeasured:'first spoken segment; generated PCM sent at real-time speed',screenshotsUsed:'generated',savedSessions:0}
 },selectedCases)
 await mkdir('artifacts/agent-query-optimized',{recursive:true})
 await writeFile(output,JSON.stringify({...rows,browserErrors:errors},null,2),'utf8')
 for(const picture of await page.evaluate(()=>window.queryImages||[])){
  if(picture.data)await writeFile(output.replace(/\.json$/,`-${picture.name}.png`),Buffer.from(picture.data.split(',')[1],'base64'))
 }
 console.log(JSON.stringify(rows,null,2));console.log(JSON.stringify({passed:rows.rows.filter(r=>r.passed).length,total:rows.rows.length,browserErrors:errors}))
 if(rows.rows.some(r=>!r.passed)||errors.length)process.exitCode=1
}finally{await browser.close()}
