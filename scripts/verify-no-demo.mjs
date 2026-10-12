import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage(),writes=[],errors=[];page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',r=>{const path=new URL(r.request().url()).pathname;if(path.startsWith('/api/sessions/')&&r.request().method()==='PUT')writes.push(r.request().postDataJSON());return r.fulfill({json:path==='/api/sessions'?[]:path==='/api/settings/models'?{activeId:null,profiles:[]}:path==='/api/health'?{mode:'unconfigured',storage:'sqlite'}:{tools:[],items:[]}})})
 await page.goto('http://127.0.0.1:5174');await page.locator('.launcher-titlebar').waitFor();await page.waitForTimeout(150)
 assert.equal(writes.length,0,'Startup never generates or saves seeded sessions')
 const value=await page.evaluate(async()=>{const {newSession,withoutDemoData}=await import('/src/sessions.ts');const s=newSession();const real={...s,formula:'x^2+y^2',messages:[{id:'real',role:'user',text:'actual user input'}]};return {empty:[s.assets.length,s.messages.length,s.rows.length,s.formula],preserved:withoutDemoData(real).formula,legacy:withoutDemoData({...s,scenario:'formula',messages:[{id:'seed-user',role:'user',text:'seeded'},{id:'seed-assistant',role:'assistant',text:'seeded',demo:true}]})===undefined}})
 assert.deepEqual(value,{empty:[0,0,0,''],preserved:'x^2+y^2',legacy:true});assert.deepEqual(errors,[])
 console.log('PASS: no generated startup sessions, no prefilled images/formula/rows/replies, legacy demo cache filtering, real user formula preservation.')
}finally{await browser.close()}
