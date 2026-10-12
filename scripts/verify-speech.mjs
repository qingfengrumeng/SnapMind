// Synthetic configuration/audio only. Never touches credentials or user settings.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1100,height:1000}}),errors=[]
 let previews=0,saves=0,blockedPreview=false,releasePreview,voiceFetches=0,previewBodies=[],failedVoices=false,modelFetches=[],failedModels=false
 let registry={activeTtsId:'qwen-tts',activeAsrId:'qwen-asr',profiles:['tts','asr'].map(kind=>({id:'qwen-'+kind,name:'Qwen '+kind.toUpperCase(),kind,provider:'dashscope',baseUrl:'wss://example.com/api-ws/v1/'+(kind==='tts'?'inference':'realtime'),model:kind==='tts'?'qwen-audio-3.1-tts-flash':'qwen3-asr-flash-realtime',voice:'longanwen_v3.1',sampleRate:kind==='tts'?22050:16000,rate:1,volume:50,pitch:1,hasApiKey:true}))}
 page.on('pageerror',e=>errors.push(e.message))
 await page.addInitScript(()=>{window.audioEvents=[];window.Audio=class{async play(){window.audioEvents.push(this.started?'resume':'play');this.started=true}pause(){window.audioEvents.push('pause')}removeAttribute(){}load(){window.audioEvents.push('clear')}}})
 await page.route('**/api/**',async r=>{
  const path=new URL(r.request().url()).pathname,method=r.request().method()
  if(path.startsWith('/api/settings/speech')){
   if(method==='GET')return r.fulfill({json:registry})
   const body=r.request().postDataJSON(),id=path.split('/')[4]
   if(path.endsWith('/models')){modelFetches.push(body.kind);await new Promise(resolve=>setTimeout(resolve,800));if(failedModels)return r.fulfill({status:400,json:{detail:'模型列表接口不可用'}});return r.fulfill({json:{kind:body.kind,models:body.kind==='asr'?['qwen3-asr-flash-realtime','fun-asr-realtime']:['qwen-audio-3.1-tts-flash','cosyvoice-v3'],source:'https://example.com/api/v1/models'}})}
   if(path.endsWith('/voices')){voiceFetches++;await new Promise(resolve=>setTimeout(resolve,200));if(failedVoices)return r.fulfill({status:502,json:{detail:'获取官方音色列表失败，请稍后重试'}});return r.fulfill({json:{model:body.model,source:'https://help.aliyun.com/zh/model-studio/qwen-audio-tts-voice-list',voices:[{id:'longanwen_v3.1',name:'龙安温',description:'优雅知性女',language:'zh'},{id:'Emily_v3.1',name:'Emily',description:'英式女声',language:'en'}]}})}
   if(path.endsWith('/preview')){previews++;previewBodies.push(body);if(blockedPreview)await new Promise(resolve=>releasePreview=resolve);return r.fulfill({contentType:'audio/mpeg',body:Buffer.from('ID3fixture')}).catch(()=>{})}
   if(path.endsWith('/test'))return r.fulfill({json:{ok:true,latencyMs:24,authVerified:true}})
   if(path.endsWith('/active'))registry[body.kind==='tts'?'activeTtsId':'activeAsrId']=body.activeId
   else{saves++;const old=registry.profiles.find(p=>p.id===id);const p={...old,...body,id,hasApiKey:body.clearApiKey?false:!!body.apiKey||old?.hasApiKey};delete p.apiKey;delete p.clearApiKey;registry.profiles=registry.profiles.filter(p=>p.id!==id).concat(p);registry[body.kind==='tts'?'activeTtsId':'activeAsrId']=null}
   return r.fulfill({json:registry})
  }
  if(path==='/api/settings/models')return r.fulfill({json:{activeId:null,profiles:[]}})
  if(path==='/api/settings/config')return r.fulfill({json:{schemaVersion:1,activeModelId:null,models:[]}})
  return r.fulfill({json:path==='/api/sessions'?[]:{tools:[],items:[]}})
 })
 await page.goto('http://127.0.0.1:5174')
 await page.locator('.launcher-settings-toggle').click();await page.getByRole('tab',{name:'模型配置',exact:true}).click()
 await page.getByRole('tab',{name:/TTS/}).click()
 const panel=page.locator('#model-panel-speech')
 assert.equal(await page.locator('#model-category-tts img').count(),0,'Navigation is vendor-neutral')
 assert.equal(await page.locator('#model-category-asr').count(),1);assert.equal(await page.locator('#model-category-tts').count(),1);assert.equal(await panel.locator('h3,.speech-section-title').count(),0,'No duplicated speech subtitle below navigation')
 assert.deepEqual(await panel.locator('.speech-config-section').evaluateAll(els=>els.map(el=>el.getAttribute('aria-label'))),['TTS · 语音合成'])
 await page.getByRole('tab',{name:/^TTS/}).click();await panel.getByRole('button',{name:'展开 Qwen TTS',exact:true}).click()
 assert.equal(await panel.getByRole('textbox',{name:'Qwen TTS 模型名称'}).inputValue(),'qwen-audio-3.1-tts-flash')
 assert.equal(await panel.getByRole('combobox',{name:'Qwen TTS 采样率'}).count(),0)
 assert.equal(await panel.getByRole('spinbutton').count(),0,'TTS tuning fields are removed')
 const modelFetch=panel.getByRole('button',{name:'获取模型列表',exact:true});await modelFetch.click();await modelFetch.locator('.rotating').waitFor();assert.equal((await modelFetch.innerText()).trim(),'获取模型列表');await panel.getByRole('status').filter({hasText:'2 个 TTS 模型'}).waitFor()
 const modelSelect=panel.getByRole('combobox',{name:'Qwen TTS 模型名称'});await modelSelect.click();assert.deepEqual(await page.getByRole('option').allTextContents(),['qwen-audio-3.1-tts-flash','cosyvoice-v3']);await page.getByRole('searchbox',{name:'输入名称筛选模型'}).fill('cosy');assert.equal(await page.getByRole('option').count(),1);await page.getByRole('searchbox',{name:'输入名称筛选模型'}).press('Escape')
 failedModels=true;await modelFetch.click();await panel.getByRole('alert').filter({hasText:'模型列表接口不可用'}).waitFor();await modelSelect.click();assert.equal(await page.getByRole('option').count(),2,'Failed model refresh retains the real previous catalogue');await page.getByRole('searchbox',{name:'输入名称筛选模型'}).press('Escape');failedModels=false
 await panel.getByRole('button',{name:'手动输入',exact:true}).click();await panel.getByRole('textbox',{name:'Qwen TTS 模型名称'}).waitFor()
 assert.equal(await panel.getByRole('textbox',{name:'Qwen TTS API Key'}).inputValue(),'')
 assert.equal(await panel.getByRole('switch',{name:'启用 Qwen TTS'}).getAttribute('aria-checked'),'true')
 const logo=panel.locator('.model-vendor-mark img').first();assert.equal(await logo.evaluate(el=>el.complete&&el.naturalWidth>0),true)
 assert.equal(await panel.getByRole('textbox',{name:/配置名称/}).count(),0)
 assert.equal(await panel.locator('select').count(),0,'All speech dropdowns use the shared model selector')
 const fetchButton=panel.getByRole('button',{name:'获取音色列表',exact:true});assert.equal(await fetchButton.evaluate(el=>getComputedStyle(el).color),'rgb(124, 58, 237)');assert.equal(await page.locator('#model-category-tts .model-category-icon svg').evaluate(el=>getComputedStyle(el).stroke),'rgb(124, 58, 237)');assert.ok(await panel.locator('.model-profile-title small').first().evaluate(el=>parseFloat(getComputedStyle(el).fontSize)>=12))
 await fetchButton.click();await fetchButton.locator('.rotating').waitFor();assert.equal((await fetchButton.innerText()).trim(),'获取音色列表');await panel.getByRole('status').filter({hasText:'2 个官方系统音色'}).waitFor();assert.equal(voiceFetches,1)
 await panel.getByRole('button',{name:'试听音色',exact:true}).click();await panel.getByRole('button',{name:'暂停试听',exact:true}).waitFor();await panel.getByRole('button',{name:'暂停试听',exact:true}).click();await panel.getByRole('button',{name:'继续试听',exact:true}).click();assert.equal(previews,1,'Pause/resume reuses generated audio')
 const voice=panel.getByRole('combobox',{name:'Qwen TTS 音色名称'})
 await voice.scrollIntoViewIfNeeded();await voice.click();await page.getByRole('button',{name:'试听 Emily_v3.1',exact:true}).click();await page.getByRole('button',{name:'暂停试听 Emily_v3.1',exact:true}).waitFor();assert.equal(await voice.getAttribute('aria-expanded'),'true');assert.match(await voice.innerText(),/longanwen_v3.1/);assert.equal(previewBodies.at(-1).voice,'Emily_v3.1');assert.match(previewBodies.at(-1).text,/Hello/)
 await page.waitForFunction(()=>{const el=document.querySelector('.speech-option-preview.reading');return el&&getComputedStyle(el).color==='rgb(255, 255, 255)'})
 await mkdir('artifacts/speech',{recursive:true});await page.screenshot({path:'artifacts/speech/voice-dropdown.png'})
 await page.getByRole('button',{name:'暂停试听 Emily_v3.1',exact:true}).click();await page.getByRole('button',{name:'继续试听 Emily_v3.1',exact:true}).click();assert.equal(previews,2)
 await page.getByRole('searchbox',{name:'搜索名称或输入音色 ID'}).fill('new-voice');await page.getByRole('searchbox',{name:'搜索名称或输入音色 ID'}).press('Enter');await panel.getByRole('switch',{name:'启用 Qwen TTS'}).click();await panel.getByRole('alert').filter({hasText:'请先保存修改'}).waitFor()
 await panel.getByRole('button',{name:'保存配置',exact:true}).click();await panel.getByRole('status').filter({hasText:'配置已保存'}).waitFor();assert.equal(saves,1);assert.equal(registry.activeTtsId,null);assert.equal(registry.activeAsrId,'qwen-asr')
 await panel.getByRole('switch',{name:'启用 Qwen TTS'}).click();await page.waitForFunction(()=>document.querySelector('[aria-label="启用 Qwen TTS"]')?.getAttribute('aria-checked')==='true')
 await panel.getByRole('button',{name:'测速',exact:true}).click();await panel.getByRole('status').filter({hasText:'24 ms'}).waitFor()
 failedVoices=true;await panel.getByRole('button',{name:'获取音色列表',exact:true}).click();await panel.getByRole('alert').filter({hasText:'获取官方音色列表失败'}).waitFor();await voice.click();assert.equal(await page.getByRole('option').count(),3,'Failed refresh keeps the current selection and previously fetched voices');await page.getByRole('searchbox',{name:'搜索名称或输入音色 ID'}).press('Escape');failedVoices=false
 await page.getByRole('tab',{name:/^ASR/}).click();await panel.getByRole('button',{name:'展开 Qwen ASR',exact:true}).click();assert.equal(await panel.getByRole('combobox',{name:'Qwen ASR 识别语言'}).count(),0);assert.equal(await panel.getByRole('combobox',{name:'Qwen ASR 采样率'}).count(),0)
 await panel.getByRole('button',{name:'获取模型列表',exact:true}).click();await panel.getByRole('status').filter({hasText:'2 个 ASR 模型'}).waitFor();await panel.getByRole('combobox',{name:'Qwen ASR 模型名称'}).click();assert.deepEqual(await page.getByRole('option').allTextContents(),['qwen3-asr-flash-realtime','fun-asr-realtime']);await page.getByRole('searchbox',{name:'输入名称筛选模型'}).press('Escape');assert.deepEqual(modelFetches,['tts','tts','asr']);assert.equal(registry.profiles.find(p=>p.kind==='tts').sampleRate,22050,'Removing controls preserves the saved audio format')
 await page.getByRole('tab',{name:/^TTS/}).click();await panel.getByRole('button',{name:'展开 Qwen TTS',exact:true}).click()
 await mkdir('artifacts/speech',{recursive:true});await page.getByRole('tab',{name:/TTS/}).scrollIntoViewIfNeeded();await page.screenshot({path:'artifacts/speech/configuration.png'})
 await panel.getByRole('button',{name:'试听音色',exact:true}).click();await panel.getByRole('button',{name:'暂停试听',exact:true}).waitFor();await page.getByRole('tab',{name:/^LLM/}).click();assert.equal(await page.evaluate(()=>window.audioEvents.at(-1)),'clear')
 await page.getByRole('tab',{name:/TTS/}).click();blockedPreview=true;await panel.getByRole('button',{name:'试听音色',exact:true}).click();await panel.getByRole('button',{name:'取消试听',exact:true}).click();await panel.getByRole('button',{name:'试听音色',exact:true}).waitFor();releasePreview();await page.waitForTimeout(100);assert.equal(await panel.getByRole('button',{name:'暂停试听',exact:true}).count(),0,'Cancelled synthesis must not start playing after its late response')
 await page.setViewportSize({width:420,height:900});await page.getByRole('tab',{name:/TTS/}).scrollIntoViewIfNeeded();assert.equal(await page.locator('.settings-tab-content').evaluate(el=>el.scrollWidth<=el.clientWidth),true,'Speech settings fit a narrow window');await page.screenshot({path:'artifacts/speech/configuration-mobile.png'})
 assert.deepEqual(errors,[])
 console.log('PASS: separate vendor-neutral ASR/TTS tabs, no duplicate subtitle, category-filtered cards, shared dropdowns, fetched voices, per-option preview, independent activation, save-before-enable, preview cancellation/cleanup, narrow layout.')
}finally{await browser.close()}
