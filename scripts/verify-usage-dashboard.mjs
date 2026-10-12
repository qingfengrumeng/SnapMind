import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
const directory='artifacts/usage-dashboard'
await mkdir(directory,{recursive:true})
function fixture(kind,start,end,empty=false){
 const hourly=start===end,days=Math.round((Date.parse(end)-Date.parse(start))/86400000)+1
 const zero=()=>kind==='ocr'?{requests:0,unbucketedRequests:0}:{requests:0,inputTokens:0,outputTokens:0,totalTokens:0,cachedInputTokens:0,uncachedInputTokens:0,cacheInputTokens:0,cacheReportedRequests:0,cacheHitRate:null,unreportedRequests:0,unbucketedRequests:0}
 const points=Array.from({length:hourly?24:days},(_,i)=>{const day=new Date(Date.parse(start)+i*86400000).toISOString().slice(0,10),key=hourly?`${start}T${String(i).padStart(2,'0')}:00`:day;return {key,label:hourly?key.slice(-5):day.slice(5),...zero()}})
 if(!empty)points.forEach((p,i)=>{if(i%3===0)Object.assign(p,kind==='ocr'?{requests:i+1}:{requests:i+1,inputTokens:(i+1)*100,outputTokens:(i+1)*30,totalTokens:(i+1)*130,cachedInputTokens:(i+1)*40,uncachedInputTokens:(i+1)*60,cacheInputTokens:(i+1)*100,cacheReportedRequests:i+1,cacheHitRate:40})})
 const summary=zero();for(const p of points)for(const key of Object.keys(summary))if(key!=='cacheHitRate')summary[key]+=p[key]||0
 if(kind==='llm')summary.cacheHitRate=summary.cacheInputTokens?40:null
 const model=kind==='ocr'?'PP-StructureV3':'deepseek-flash'
 return {kind,range:{start,end,timezone:'Asia/Shanghai',granularity:hourly?'hour':'day'},summary,models:empty?[]:[{model,...summary}],trend:points,modelTrends:empty?[]:[{model,points}]}
}
try{
 const page=await browser.newPage({viewport:{width:1360,height:1080},acceptDownloads:true}),errors=[],queries=[]
 let fail=false,empty=false,hold=false,release,legacy=false,multipleModels=false
 page.on('pageerror',e=>errors.push(e.message))
 await page.route('**/api/**',async route=>{
  const url=new URL(route.request().url()),path=url.pathname
  if(path==='/api/usage/analytics'){
   const kind=url.searchParams.get('kind'),start=url.searchParams.get('start'),end=url.searchParams.get('end');queries.push({kind,start,end})
   if(hold){hold=false;await new Promise(resolve=>release=resolve)}
   const snapshot=fixture(kind,start,end,empty)
   if(multipleModels&&kind==='llm'&&!empty){
    const scale=(row,factor)=>Object.fromEntries(Object.entries(row).map(([key,value])=>[key,typeof value==='number'&&key!=='cacheHitRate'?value*factor:value]))
    snapshot.models.push({model:'synthetic-second-model',...scale(snapshot.summary,2)})
    snapshot.modelTrends.push({model:'synthetic-second-model',points:snapshot.trend.map(point=>scale(point,2))})
    snapshot.summary=scale(snapshot.summary,3);snapshot.trend=snapshot.trend.map(point=>scale(point,3))
   }
   if(legacy&&kind==='llm')for(const row of [snapshot.summary,...snapshot.models,...snapshot.trend,...snapshot.modelTrends.flatMap(model=>model.points)])Object.assign(row,{cachedInputTokens:null,uncachedInputTokens:null,cacheInputTokens:0,cacheReportedRequests:0,cacheHitRate:0})
   await route.fulfill(fail?{status:503,json:{detail:'English private error'}}:{json:snapshot});return
  }
  await route.fulfill({json:path==='/api/sessions'?[]:path==='/api/settings/models'?{activeId:null,profiles:[]}:{}})
 })
 await page.goto(process.env.SNAPMIND_UI_URL||'http://127.0.0.1:5174')
 await page.locator('.launcher-settings-toggle').click();await page.locator('#settings-tab-usage').click()
 const dashboard=page.locator('.usage-dashboard'),refresh=dashboard.locator('.usage-refresh')
 const ready=()=>page.waitForFunction(()=>document.querySelector('.usage-refresh')&&!document.querySelector('.usage-refresh').disabled)
 await ready();assert.equal(queries.length,1)
 assert.equal(await dashboard.locator('.usage-summary-cards article').count(),5)
 assert.equal(await dashboard.locator('.usage-chart-card').count(),4)
 assert.equal(await dashboard.locator('.usage-overview-trends [data-chart-type="bar"]').count(),2)
 assert.equal(await dashboard.locator('.usage-per-model [data-chart-type="line"]').count(),2)
 assert.equal(await dashboard.locator('.usage-per-model .usage-token-bar').count(),0)
 assert.equal(await dashboard.locator('.usage-per-model [data-metric="requests"] polyline').count(),1)
 assert.equal(await dashboard.locator('.usage-per-model [data-metric="tokens"] polyline').count(),3)
 assert.equal(await dashboard.locator('.usage-model-table tbody tr').count(),1)
 assert.equal(await dashboard.locator('[data-stat="cached"] small, .usage-summary-cards article > svg').count(),0)
 assert.equal(await dashboard.locator('.usage-summary-cards article > span > svg').count(),5)
 async function choose(name){await dashboard.locator('.usage-date-trigger').click();await dashboard.locator('.usage-date-presets').getByRole('button',{name,exact:true}).click();await ready()}
 await choose('今天');assert.equal(queries.at(-1).start,queries.at(-1).end)
 assert.equal(await dashboard.locator('.usage-chart-card').first().locator('svg > g').count(),27)
 const modelPlot=dashboard.locator('.usage-per-model [data-metric="tokens"] .usage-chart-plot').first()
 assert.equal((await modelPlot.locator('polyline').first().getAttribute('points')).split(' ').length,24)
 assert.ok(!(await modelPlot.locator('polyline').first().getAttribute('points')).includes('NaN'))
 await modelPlot.focus();await page.keyboard.press('Home')
 assert.equal(await modelPlot.locator('.usage-line-point').count(),3)
 assert.match(await modelPlot.locator('.usage-chart-tooltip').innerText(),/输入（命中缓存）\s+40/)
 await page.keyboard.press('Escape')
 const plot=dashboard.locator('[data-metric="tokens"] .usage-chart-plot').first();await plot.focus();await page.keyboard.press('Home')
 assert.match(await plot.locator('.usage-chart-tooltip').innerText(),/00:00/)
 assert.deepEqual(await dashboard.locator('[data-metric="tokens"] .usage-chart-legend').first().locator('span').allTextContents(),['输入（命中缓存）','输入（未命中缓存）','输出'])
 assert.match(await plot.locator('.usage-chart-tooltip').innerText(),/输入（命中缓存）\s+40/)
 await page.keyboard.press('End');assert.match(await plot.locator('.usage-chart-tooltip').innerText(),/23:00/)
 await page.keyboard.press('Escape');assert.equal(await plot.locator('.usage-chart-tooltip').count(),0);assert.equal(await dashboard.isVisible(),true)
 const countBefore=queries.length,download=page.waitForEvent('download');await dashboard.getByRole('button',{name:'导出',exact:true}).click();const file=await download
 assert.match(file.suggestedFilename(),/^SnapMind-LLM-/);await file.saveAs(`${directory}/llm.zip`);assert.equal(queries.length,countBefore)
 const names=[file.suggestedFilename()]
 for(let i=0;i<2;i++){
  await page.waitForFunction(()=>!document.querySelector('.usage-export').disabled)
  const next=page.waitForEvent('download');await dashboard.getByRole('button',{name:'导出',exact:true}).click()
  const repeated=await next;names.push(repeated.suggestedFilename());await repeated.saveAs(`${directory}/llm-repeat-${i+1}.zip`)
 }
 assert.equal(new Set(names).size,3);assert.equal(queries.length,countBefore)
 await page.waitForFunction(()=>!document.querySelector('.usage-export').disabled)
 await page.evaluate(()=>{
  window.isTauri=true;window.__exportCalls=[]
  window.__TAURI_INTERNALS__={invoke:(command,args)=>{if(command!=='save_usage_archive')throw Error('Unexpected native command');window.__exportCalls.push(args);return new Promise((resolve,reject)=>{window.__finishExport=resolve;window.__failExport=reject})}}
 })
 // A native export stays busy until saving succeeds, is cancelled, or fails.
 for(const outcome of ['cancel','fail','saved','saved']){
  const calls=await page.evaluate(()=>window.__exportCalls.length)
  await dashboard.getByRole('button',{name:'导出',exact:true}).click()
  await page.waitForFunction(count=>window.__exportCalls.length===count+1,calls)
  assert.equal(await dashboard.locator('.usage-export').isDisabled(),true)
  assert.equal(await dashboard.locator('.usage-dashboard-message').count(),0)
  await page.evaluate(outcome=>outcome==='fail'?window.__failExport(Error('synthetic error')):window.__finishExport(outcome==='saved'),outcome)
  await page.waitForFunction(()=>!document.querySelector('.usage-export').disabled)
  const message=await dashboard.locator('.usage-dashboard-message').allTextContents()
  if(outcome==='cancel')assert.deepEqual(message,[])
  if(outcome==='fail')assert.match(message.join(''),/导出失败/)
  if(outcome==='saved')assert.match(message.join(''),/可再次导出/)
 }
 const nativePayloads=await page.evaluate(()=>window.__exportCalls.map(args=>({filename:args.filename,magic:atob(args.base64Data).slice(0,4)})))
 assert.equal(nativePayloads.length,4);assert.ok(nativePayloads.every(args=>args.magic==='PK\x03\x04'))
 assert.equal(new Set(nativePayloads.map(args=>args.filename)).size,4)
 await page.waitForFunction(()=>!document.querySelector('.usage-dashboard-message'),{},{timeout:6000})
 await page.evaluate(()=>{window.isTauri=false;delete window.__TAURI_INTERNALS__})
 await choose('昨天');assert.equal(queries.at(-1).start,queries.at(-1).end)
 await choose('近 30 天');assert.equal((Date.parse(queries.at(-1).end)-Date.parse(queries.at(-1).start))/86400000,29)
 await choose('本月');assert.equal(queries.at(-1).start.slice(-2),'01')
 await choose('上月');assert.equal(queries.at(-1).start.slice(-2),'01')
 await dashboard.locator('.usage-date-trigger').click();await dashboard.locator('.usage-date-presets').getByRole('button',{name:'自定义',exact:true}).click()
 await dashboard.locator('input[aria-label="开始日期"]').fill('2026-10-03');await dashboard.locator('input[aria-label="结束日期"]').fill('2026-10-09')
 await dashboard.locator('input[aria-label="结束日期"]').fill('2026-10-02');assert.equal(await dashboard.getByRole('button',{name:'应用时间范围'}).isDisabled(),true)
 await dashboard.locator('input[aria-label="结束日期"]').fill('2026-10-09')
 await dashboard.getByRole('button',{name:'应用时间范围'}).click();await ready();assert.equal(queries.at(-1).start,'2026-10-03')
 await dashboard.locator('#usage-category-ocr').click();await ready()
 assert.equal(await dashboard.locator('.usage-summary-cards article').count(),2)
 assert.equal(await dashboard.locator('.usage-model-table th').count(),2)
 assert.equal(await dashboard.locator('.usage-chart-card').count(),2)
 assert.equal(await dashboard.locator('.usage-per-model [data-chart-type="line"] polyline').count(),1)
 assert.ok(!(await dashboard.locator('#usage-category-panel').innerText()).includes('Token'))
 assert.equal(await dashboard.locator('.usage-model-table .usage-model-type').innerText(),'PaddleOCR')
 await choose('今天');const ocrDownload=page.waitForEvent('download');await dashboard.getByRole('button',{name:'导出',exact:true}).click();await (await ocrDownload).saveAs(`${directory}/ocr.zip`)
 await dashboard.locator('#usage-category-llm').click();await ready();assert.equal(queries.at(-1).start,'2026-10-03');assert.equal(queries.at(-1).end,'2026-10-09')
 hold=true;const old=await dashboard.locator('.usage-summary-cards').innerText();await refresh.click()
 await page.waitForFunction(()=>document.querySelector('.usage-refresh').disabled)
 assert.equal(await refresh.locator('svg').evaluate(s=>getComputedStyle(s).animationName),'usage-refresh-spin')
 assert.equal(await dashboard.locator('.usage-summary-cards').innerText(),old)
 while(!release)await new Promise(resolve=>setTimeout(resolve,10));release();await ready()
 fail=true;await refresh.click();await ready();assert.match(await dashboard.getByRole('alert').innerText(),/无法加载/);assert.ok(!(await dashboard.innerText()).includes('English private error'));fail=false
 await refresh.click();await ready()
 const exported=await page.evaluate(async()=>{const m=await import('/src/usage-export.ts');const r={requests:1,unbucketedRequests:0};return m.usageExportDocuments({kind:'ocr',range:{start:'2026-10-09',end:'2026-10-09',timezone:'Asia/Shanghai',granularity:'hour'},summary:r,models:[{model:'=SUM(1,2)|test',...r}],trend:[],modelTrends:[]})})
 assert.ok(exported.csv.includes("'=SUM(1,2)|test"));assert.ok(exported.markdown.includes('\\|test'))
 const rangeChecks=await page.evaluate(async()=>{const m=await import('/src/usage-range.ts');return [m.presetRange('lastMonth','2026-01-01'),m.presetRange('lastMonth','2024-03-03'),m.validUsageRange('2026-02-30','2026-03-01')]})
 assert.equal(rangeChecks[0].start,'2025-12-01');assert.equal(rangeChecks[0].end,'2025-12-31');assert.equal(rangeChecks[1].end,'2024-02-29');assert.equal(rangeChecks[2],false)
 legacy=true;await refresh.click();await ready()
 assert.equal(await dashboard.locator('[data-stat="cached"] strong').innerText(),'0')
 assert.ok(!(await dashboard.innerText()).includes('缓存未上报'))
 assert.equal(await dashboard.locator('.usage-token-bar.unknown,.usage-chart-legend .unknown').count(),0)
 assert.equal(await dashboard.locator('.usage-model-table .usage-cached-cell').innerText(),'0')
 assert.deepEqual((await dashboard.locator('.usage-model-table tbody tr td').allTextContents()).slice(1,5),['0','1,200','360','1,560'])
 await plot.focus();await page.keyboard.press('Home')
 assert.match(await plot.locator('.usage-chart-tooltip').innerText(),/输入（命中缓存）\s+0/)
 assert.match(await plot.locator('.usage-chart-tooltip').innerText(),/输入（未命中缓存）\s+100/)
 await page.keyboard.press('ArrowRight');assert.deepEqual(await plot.locator('.usage-chart-tooltip b').allTextContents(),['0','0','0','0'])
 await page.keyboard.press('Escape')
 const legacyExport=page.waitForEvent('download');await dashboard.getByRole('button',{name:'导出',exact:true}).click();await (await legacyExport).saveAs(`${directory}/legacy-three-categories.zip`)
 legacy=false;await refresh.click();await ready()
 multipleModels=true;await refresh.click();await ready()
 assert.equal(await dashboard.locator('.usage-per-model').count(),2)
 assert.equal(await dashboard.locator('.usage-per-model .usage-trend-line').count(),8)
 const colors=await dashboard.locator('.usage-per-model').evaluateAll(sections=>sections.map(section=>Array.from(section.querySelectorAll('.usage-trend-line')).map(line=>getComputedStyle(line).stroke)))
 assert.deepEqual(colors[0],colors[1])
 const curves=await dashboard.locator('.usage-per-model [data-metric="tokens"] polyline.uncached').evaluateAll(lines=>lines.map(line=>line.getAttribute('points')))
 // Each model keeps its own data even though both share a color scheme.
 assert.equal(await dashboard.locator('.usage-per-model header h4').last().innerText(),'synthetic-second-model')
 const modelsTotal=await dashboard.locator('.usage-per-model [data-metric="tokens"] header strong').allTextContents()
 assert.deepEqual(modelsTotal,['1,560','3,120'])
 assert.ok(curves.every(curve=>!curve.includes('NaN')))
 await dashboard.locator('.usage-per-model').first().screenshot({path:`${directory}/model-line-preview.png`})
 await dashboard.locator('.usage-per-model').last().screenshot({path:`${directory}/second-model-line-preview.png`})
 multipleModels=false;await refresh.click();await ready()
 await page.locator('.home-settings-panel').screenshot({path:`${directory}/llm-preview.png`})
 await dashboard.locator('#usage-category-ocr').click();await ready();await page.locator('.home-settings-panel').screenshot({path:`${directory}/ocr-preview.png`})
 await page.setViewportSize({width:390,height:900});await dashboard.locator('.usage-date-trigger').click()
 const bounds=await dashboard.locator('.usage-date-popover').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390)
 await page.keyboard.press('Escape');assert.equal(await dashboard.locator('.usage-date-popover').count(),0)
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>window.innerWidth),false)
 const columns=await dashboard.locator('.usage-charts').first().evaluate(el=>getComputedStyle(el).gridTemplateColumns);assert.equal(columns.split(' ').length,1)
 await page.locator('.home-settings-panel').screenshot({path:`${directory}/mobile-preview.png`})
 await page.evaluate(()=>document.documentElement.dataset.theme='dark');await page.locator('.home-settings-panel').screenshot({path:`${directory}/dark-preview.png`})
 empty=true;await refresh.click();await ready();assert.equal(await dashboard.locator('.usage-model-table').count(),0);assert.equal(await dashboard.locator('.usage-chart-no-data').count(),1)
 assert.deepEqual(errors,[])
 console.log('PASS: LLM/OCR tabs, cache totals, seven date presets and custom ranges, hourly/daily charts, keyboard tooltips, independent dates, current-page ZIP exports, refresh/error/empty states, responsive/dark layouts. Synthetic API only.')
}finally{await browser.close()}
