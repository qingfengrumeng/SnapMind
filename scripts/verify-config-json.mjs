// Isolated configuration fixture. Never writes the user's .snapmind file or exposes real keys.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const native=process.argv.includes('--native')
const browser=native?await chromium.connectOverCDP('http://127.0.0.1:9223'):await chromium.launch({channel:'msedge',headless:true})
const context=native?browser.contexts()[0]:await browser.newContext({viewport:{width:1100,height:1000}})
const page=native?context.pages().find(p=>p.url().includes('5174')&&!p.url().includes('desktop=')):await context.newPage()
let state={activeId:null,configFile:'backend/.snapmind',profiles:[['deepseek','DeepSeek'],['kimi','Kimi'],['qwen','Qwen'],['doubao','豆包'],['glm','GLM'],['custom','自定义接口']].map(([id,name])=>({id,name,vendor:id,provider:'openai-compatible',baseUrl:'https://example.invalid/v1',model:'',hasApiKey:false,saved:false,vision:false}))}
const keys={},errors=[];let draftWrites=0
page.on('pageerror',e=>errors.push(e.message))
const click=locator=>native?locator.evaluate(e=>e.click()):locator.click()
const document=reveal=>({schemaVersion:1,activeModelId:state.activeId,models:state.profiles.map(p=>({id:p.id,name:p.name,provider:p.vendor,baseUrl:p.baseUrl,apiKey:keys[p.id]?(reveal?keys[p.id]:'••••••••'):'',model:p.model,enabled:p.id===state.activeId,vision:p.vision}))})
async function wait(check){for(let i=0;i<50;i++){if(check())return;await page.waitForTimeout(100)}throw Error('Configuration state did not settle')}
await page.route('**/api/settings/config*',route=>route.fulfill({json:document(new URL(route.request().url()).searchParams.get('reveal_keys')==='true')}))
await page.route('**/api/settings/models**',async route=>{
 const url=new URL(route.request().url()),path=url.pathname
 if(route.request().method()==='GET')return route.fulfill({json:state})
 const body=route.request().postDataJSON()
 if(path.endsWith('/active')){state.activeId=body.activeId;return route.fulfill({json:state})}
 const id=path.endsWith('/draft')?path.split('/').at(-2):path.split('/').at(-1)
 const old=state.profiles.find(p=>p.id===id),key=keys[id]||''
 if(path.endsWith('/draft'))draftWrites++
 if(body.clearApiKey)delete keys[id];else if(body.apiKey)keys[id]=body.apiKey
 if(state.activeId===id&&(old.model!==body.model||old.baseUrl!==body.baseUrl||key!==(keys[id]||'')))state.activeId=null
 const p={...old,...body,id,hasApiKey:!!keys[id],saved:!!body.model&&!!body.baseUrl&&!!keys[id]};delete p.apiKey;delete p.clearApiKey
 state.profiles[state.profiles.indexOf(old)]=p
 return route.fulfill({json:state})
})
const row=id=>page.locator(`[data-profile-id="${id}"]`)
const json=async()=>JSON.parse((await page.locator('.configuration-code-line>code').allTextContents()).join('\n'))
async function hide(value){await page.getByRole('checkbox',{name:'隐藏 API Key',exact:true}).evaluate((e,value)=>{e.checked=value;e.dispatchEvent(new Event('change',{bubbles:true}))},value)}
try{
 if(native){await page.evaluate(()=>window.__TAURI_INTERNALS__.invoke('show_launcher'));await page.reload()}else await page.goto(process.env.SNAPMIND_UI_URL||'http://127.0.0.1:5174')
 await page.locator('.snapmind-home').waitFor();await click(page.locator('.launcher-settings-toggle'));await click(page.getByRole('tab',{name:'模型配置',exact:true}))
 await page.locator('.configuration-json').waitFor()
 assert.equal((await json()).models.length,6)
 await click(row('deepseek').locator('.model-profile-expand'))
 await row('deepseek').locator('#key-deepseek').fill('test-only-json-key')
 await wait(()=>keys.deepseek==='test-only-json-key')
 assert.equal(state.activeId,null);assert.equal(state.profiles.find(p=>p.id==='deepseek').saved,false)
 assert.equal(await row('deepseek').locator('#key-deepseek').inputValue(),'test-only-json-key','Autosave must not erase a key while typing')
 assert.equal((await json()).models.find(p=>p.id==='deepseek').apiKey,'••••••••')
 await row('deepseek').locator('input[maxlength="160"]').fill('live-model-one')
 assert.equal((await json()).models.find(p=>p.id==='deepseek').model,'live-model-one')
 await wait(()=>state.profiles.find(p=>p.id==='deepseek').saved)
 await click(row('deepseek').getByRole('switch'));await wait(()=>state.activeId==='deepseek')
 assert.equal((await json()).models.find(p=>p.id==='deepseek').enabled,true)
 await click(row('kimi').locator('.model-profile-expand'))
 await row('kimi').locator('#key-kimi').fill('test-only-second-json-key')
 await row('kimi').locator('input[maxlength="160"]').fill('live-model-two')
 await wait(()=>state.profiles.find(p=>p.id==='kimi').saved)
 await click(row('kimi').getByRole('switch'));await wait(()=>state.activeId==='kimi')
 let value=await json();assert.equal(value.activeModelId,'kimi');assert.deepEqual(value.models.filter(p=>p.enabled).map(p=>p.id),['kimi'])
 await hide(false);await wait(()=>page!==undefined);value=await json();assert.equal(value.models.find(p=>p.id==='deepseek').apiKey,'test-only-json-key')
 await hide(true);assert.equal((await json()).models.find(p=>p.id==='kimi').apiKey,'••••••••')
 await page.locator('.configuration-json').scrollIntoViewIfNeeded();await page.waitForTimeout(160)
 await page.screenshot({path:native?'artifacts/native-configuration-json.png':'artifacts/configuration-json.png'})
 await click(page.getByRole('button',{name:'切换 JSON 格式',exact:true}));assert.equal(await page.locator('.configuration-code-line').count(),1)
 assert.equal((await json()).activeModelId,'kimi')
 await click(page.getByRole('button',{name:'切换 JSON 格式',exact:true}))
 if(!native){await page.setViewportSize({width:390,height:844});assert.equal(await page.locator('.settings-tab-content').evaluate(e=>e.scrollWidth<=e.clientWidth),true)}
 assert.ok(draftWrites>=3);assert.deepEqual(errors,[])
 console.log('PASS: live valid JSON, partial-key autosave, typing preservation, single enabled flag, masked/revealed preview, formatting and responsive layout. No user file changed.')
}finally{await page.unroute('**/api/settings/models**');await page.unroute('**/api/settings/config*');if(native)await page.reload();await browser.close()}
