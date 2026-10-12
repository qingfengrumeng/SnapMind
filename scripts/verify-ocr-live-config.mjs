// Read-only check of the running development app. No OCR/LLM requests or settings writes.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1100,height:1050}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',route=>{
  assert.equal(route.request().method(),'GET','Live configuration check must remain read-only')
  return route.continue()
 })
 const health=await page.request.get('http://127.0.0.1:8776/api/health')
 assert.equal(health.status(),200,'Development API health must be available')
 const response=await page.request.get('http://127.0.0.1:8776/api/settings/ocr')
 assert.equal(response.status(),200,'OCR settings must be available')
 const p=await response.json()
 assert.equal(p.model,'PaddleOCR-VL-1.6');assert.equal(p.apiMode,'async')
 assert.equal(p.enabled,true);assert.equal(p.hasApiKey,true);assert.equal(p.dailyLimit,20000)
 assert.equal(p.apiKey,undefined);assert.equal(p.apiKeyProtected,undefined)
 assert.equal(p.fallback,'windows-ocr')
 await page.goto('http://127.0.0.1:5174')
 await page.locator('.launcher-settings-toggle').click()
 await page.getByRole('tab',{name:'模型配置',exact:true}).click()
 await page.getByRole('tab',{name:/^OCR/}).click()
 const panel=page.locator('#model-panel-ocr'),key=panel.locator('#paddleocr-key')
 await page.waitForFunction(()=>document.querySelector('#paddleocr-key')?.value==='••••••••')
 assert.equal(await key.getAttribute('type'),'password')
 assert.equal(await panel.getByLabel('每日图片上限').inputValue(),'20000')
 assert.equal(await panel.getByLabel('PaddleOCR 调用方式').inputValue(),'async')
 assert.equal(await panel.getByRole('switch',{name:'启用 PaddleOCR'}).getAttribute('aria-checked'),'true')
 await page.mouse.move(0,0);await page.waitForTimeout(200)
 await page.screenshot({path:'artifacts/paddle-location/live-ocr-settings.png'})
 assert.deepEqual(errors,[])
 console.log('PASS: actual imported OCR configuration is enabled, async VL-1.6, limit 20,000, fallback Windows OCR; token stays masked. No settings writes or model calls.')
}finally{await browser.close()}
