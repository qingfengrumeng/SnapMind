import {chromium} from 'playwright'
import {appendFile,readFile,writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'
import assert from 'node:assert/strict'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const pages=browser.contexts()[0].pages(),page=pages.find(p=>p.url().includes('desktop=image'))
assert.ok(page,'Native image window must be running')
await page.evaluate(async modulePath=>{const {getCurrentWindow}=await import(modulePath);await getCurrentWindow().setFocus()},'/@fs/'+resolve('node_modules/@tauri-apps/api/window.js').replaceAll('\\','/'))
const css=resolve('frontend/src/desktop.css'),value='hmr-'+Date.now(),marker='\n/* temporary native HMR verification */\n:root { --snapmind-hmr-probe: '+value+'; }\n'
const before=await page.evaluate(()=>window.__TAURI_INTERNALS__.invoke('get_desktop_state'))
try{
 const start=performance.now();await appendFile(css,marker)
 await page.waitForFunction(expected=>getComputedStyle(document.documentElement).getPropertyValue('--snapmind-hmr-probe').trim()===expected,value,{timeout:15000})
 const ms=Math.round(performance.now()-start),after=await page.evaluate(()=>window.__TAURI_INTERNALS__.invoke('get_desktop_state'))
 assert.equal(after.asset?.id,before.asset?.id);assert.equal(after.sessionId,before.sessionId)
 console.log(JSON.stringify({result:'PASS',cssHotUpdateMs:ms,nativeAssetRetained:true,sessionRetained:true,rustRestartRequired:false},null,2))
}finally{const current=await readFile(css,'utf8');await writeFile(css,current.replace(marker,''));await page.waitForFunction(()=>!getComputedStyle(document.documentElement).getPropertyValue('--snapmind-hmr-probe').trim(),{timeout:15000}).catch(()=>{});await browser.close()}
