// Validate the standalone archived report. No model requests or product changes.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {readFile,readdir} from 'node:fs/promises'
import {resolve} from 'node:path'
import {pathToFileURL} from 'node:url'
import {createHash} from 'node:crypto'
const root=resolve('artifacts/location-comparison'),report=JSON.parse(await readFile(resolve(root,'comparison.json'),'utf8'))
assert.equal(report.counts.records,41);assert.equal(report.runs.length,41)
assert.equal(new Set(report.runs.map(r=>r.id)).size,41)
assert.equal(report.runs.filter(r=>r.error==='timeout').length,3)
assert.deepEqual(report.comparisons.map(c=>c.qualified5px),[7,20,56,69,81])
assert.ok(report.comparisons.every(c=>c.expected===85))
for(const source of [...report.sources,...report.fixtures]){
 const bytes=await readFile(resolve(root,source.path))
 assert.equal(createHash('sha256').update(bytes).digest('hex'),source.sha256)
}
assert.equal((await readFile(resolve(root,'all-runs.csv'),'utf8')).trim().split(/\r?\n/).length,42)
assert.ok((await readdir(resolve(root,'history'))).some(name=>name.includes(report.snapshotId)))
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1280,height:1000}}),errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 await page.route(/^https?:\/\//,()=>{throw Error('Standalone report must not send network requests')})
 await page.goto(pathToFileURL(resolve(root,'index.html')).href)
 assert.equal(await page.locator('#runs tr').count(),41)
 assert.equal(await page.locator('#comparison tr').count(),5)
 assert.ok((await page.locator('#comparison').innerText()).includes('95.3%'))
 await page.locator('#ten').click()
 assert.ok((await page.locator('#comparison').innerText()).includes('100.0%'))
 await page.getByLabel('对比场景').selectOption('table')
 const structure=page.locator('#comparison tr').filter({hasText:'PP-StructureV3'})
 assert.ok((await structure.innerText()).includes('100.0%'))
 await page.locator('#five').click();assert.ok((await structure.innerText()).includes('52.0%'))
 await page.getByLabel('对比场景').selectOption('all')
 await page.getByLabel('筛选模型').selectOption('PP-StructureV3')
 assert.equal(await page.locator('#runs tr').count(),8)
 await page.getByLabel('筛选状态').selectOption('failed')
 assert.equal(await page.locator('#runs tr').count(),1)
 assert.ok((await page.locator('#runs').innerText()).includes('60.05s'))
 await page.getByLabel('筛选模型').selectOption('all');await page.getByLabel('筛选状态').selectOption('all')
 await page.locator('#images img').evaluateAll(images=>images.forEach(i=>i.loading='eager'))
 await page.waitForFunction(()=>[...document.querySelectorAll('#images img')].every(i=>i.complete&&i.naturalWidth>0))
 await page.screenshot({path:resolve(root,'overview.png')})
 assert.deepEqual(errors,[])
 console.log('PASS: 41 archived runs, 5 model comparisons, immutable source hashes, complete CSV, offline charts, threshold/scene/model/status filters and image evidence. No API calls.')
}finally{await browser.close()}
