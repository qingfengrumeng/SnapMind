// Real configured TTS/ASR with synthetic text only; never opens a microphone.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
if(!process.argv.includes('--cloud'))throw Error('Pass --cloud for synthetic cloud speech verification.')
const browser=await chromium.launch({channel:'msedge',headless:true,args:['--autoplay-policy=no-user-gesture-required']})
try{
 const page=await browser.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/src/main.ts',r=>r.fulfill({contentType:'application/javascript',body:''}))
 await page.goto('http://127.0.0.1:5174')
 const result=await page.evaluate(async()=>{
  const [{useSpeechPlayer},{createApp,h}]=await Promise.all([import('/src/speech-player.ts'),import('/node_modules/.vite/deps/vue.js')]);let player,failed='',firstMs=0,playingBeforeComplete=false,finished=false,packets=0,bytes=0,networkDoneMs=0,paused=false,resumed=false
  const host=document.createElement('div');document.body.append(host);const app=createApp({setup(){player=useSpeechPlayer(message=>failed=message);return ()=>h('span',player.state.value)}});app.mount(host)
  const begin=performance.now(),timer=setInterval(()=>{if(player.state.value==='playing'&&!finished)playingBeforeComplete=true},5)
  await player.play(async signal=>{
   const response=await fetch('/api/speech/synthesize?stream=true',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({text:'你好，我是小洁。现在为你测试流式语音播放。收到第一段音频就开始朗读，后面的声音会持续到达。你可以随时暂停、继续或打断我的回复。我可以帮你识别截图里的文字，翻译内容，也可以在图片上添加标注。流式输出让你不必等待整段内容全部生成，就能开始听到反馈。'}),signal})
   if(!response.ok)throw Error('Streaming TTS HTTP '+response.status)
   if(response.headers.get('x-snapmind-audio')!=='stream')throw Error('Buffered endpoint used')
   const upstream=response.body.getReader()
   const body=new ReadableStream({async pull(controller){const chunk=await upstream.read();if(chunk.done){finished=true;networkDoneMs=Math.round(performance.now()-begin);controller.close();return}if(!packets)firstMs=Math.round(performance.now()-begin);packets++;bytes+=chunk.value.length;controller.enqueue(chunk.value)},cancel(){return upstream.cancel()}})
   return new Response(body,{headers:{'Content-Type':'audio/mpeg'}})
  })
  clearInterval(timer);if(failed)throw Error(failed);if(player.state.value==='playing'){player.pause();paused=player.state.value==='paused';await player.resume();resumed=player.state.value==='playing'}player.stop();app.unmount();host.remove()
  return {firstMs,networkDoneMs,packets,bytes,playingBeforeComplete,paused,resumed,mse:MediaSource.isTypeSupported('audio/mpeg')}
 })
 assert.ok(result.mse&&result.packets>1&&result.playingBeforeComplete,'Audio must play while upstream is still producing chunks');assert.ok(result.paused&&result.resumed);assert.deepEqual(errors,[])
 console.log('PASS: real cloud TTS → chunked HTTP → real MSE MP3 playback before EOF, pause/resume/stop; '+JSON.stringify(result))
}finally{await browser.close()}
