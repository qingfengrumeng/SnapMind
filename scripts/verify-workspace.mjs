import {chromium} from 'playwright'
import {randomUUID} from 'node:crypto'
import assert from 'node:assert/strict'
const browser=await chromium.launch({channel:'msedge',headless:true})
const context=await browser.newContext({viewport:{width:1440,height:960},acceptDownloads:true})
const page=await context.newPage();page.setDefaultTimeout(60000)
const created=new Set(),errors=[]
page.on('pageerror',e=>errors.push(e.message))
const original=await (await context.request.get('http://127.0.0.1:5173/api/sessions')).json()
const baseline=new Set(original.map(s=>s.id))
const names={formula:'UI · 公式测试',table:'UI · 表格测试'}
page.on('response',async r=>{if(r.request().method()==='PUT'&&r.url().includes('/api/sessions/')&&r.ok()){const s=await r.json();if(!baseline.has(s.id))created.add(s.id)}})
const workspace=async()=>{await page.getByRole('button',{name:'设置与工具',exact:true}).click();await page.getByRole('tab',{name:'截图工具',exact:true}).click();await page.getByRole('button',{name:'AI 历史',exact:true}).click();await page.locator('.floating-workspace').waitFor()}
const select=async(type)=>page.locator('.history-select').filter({hasText:names[type]}).click()
try {
 for(const scenario of ['formula','table']){
  const seed=original.find(s=>s.scenario===scenario);assert.ok(seed,'需要内置 '+scenario+' 示例')
  const id=randomUUID();created.add(id)
  const s={...seed,id,title:names[scenario],rows:[{label:'7 月',value:128},{label:'8 月',value:156},{label:'9 月',value:182}],formula:'x+y',messages:[{id:randomUUID(),role:'user',text:'测试示例',sources:[seed.assets[0].id]},{id:randomUUID(),role:'assistant',text:'交互测试用示例结果',kind:scenario,demo:true,sources:[seed.assets[0].id]}]}
  const r=await context.request.put('http://127.0.0.1:5173/api/sessions/'+id,{data:s});assert.equal(r.ok(),true)
 }
 await page.goto('http://127.0.0.1:5173/');await workspace();await select('formula')
 await page.getByRole('button',{name:'校对公式'}).click();await page.locator('.formula-edit textarea').fill('\\frac{')
 await page.getByRole('button',{name:'应用修改'}).click();await page.locator('.formula-edit .error-text').waitFor()
 await page.locator('.formula-edit textarea').fill('E=mc^2');await page.getByRole('button',{name:'应用修改'}).click()
 await page.waitForTimeout(800);await page.reload();await workspace()
 assert.match(await page.locator('.formula-render').innerText(),/E/)
 const tex=page.waitForEvent('download');await page.getByRole('button',{name:'导出 TEX'}).click();assert.equal((await tex).suggestedFilename(),'attention.tex')
 await select('table');const cell=page.getByRole('spinbutton',{name:'第2行销售额'});await cell.fill('200');await cell.press('Tab')
 assert.match(await page.locator('.table-stat').innerText(),/510/)
 assert.equal(await page.locator('.bar-item>div').nth(1).evaluate(e=>parseFloat(e.style.height)),120)
 for(const [label,filename] of [['CSV','销售数据.csv'],['图表','销售图表.svg']]){const download=page.waitForEvent('download');await page.getByRole('button',{name:label,exact:true}).click();assert.equal((await download).suggestedFilename(),filename)}
 await page.waitForTimeout(800);await page.reload();await workspace()
 assert.equal(await page.getByRole('spinbutton',{name:'第2行销售额'}).inputValue(),'200')
 await page.getByRole('button',{name:/新建会话/}).click()
 const image=await page.evaluate(()=>{const c=document.createElement('canvas');c.width=320;c.height=180;c.getContext('2d').fillRect(0,0,320,180);return c.toDataURL().split(',')[1]})
 await page.locator('input[type=file][multiple]').setInputFiles({name:'UI-temporary-image.png',mimeType:'image/png',buffer:Buffer.from(image,'base64')})
 await page.getByRole('textbox',{name:'对话消息'}).fill('解释这张图片');await page.getByRole('button',{name:'发送消息',exact:true}).click()
 await page.locator('.message.assistant .message-text').filter({hasText:'尚未接入多模态模型'}).waitFor();await page.locator('.generating').waitFor({state:'detached'})
 assert.equal(await page.locator('.formula-result').count(),0)
 await page.getByRole('textbox',{name:'对话消息'}).fill('再试一次');await page.getByRole('button',{name:'发送消息',exact:true}).click();await page.getByRole('button',{name:'停止生成'}).click()
 await page.locator('.generating').waitFor({state:'detached'})
 await page.getByRole('textbox',{name:'搜索历史会话'}).fill('UI-temporary-image')
 await page.getByRole('button',{name:'会话操作'}).click();await page.getByRole('button',{name:'重命名',exact:true}).click()
 await page.getByRole('textbox',{name:'会话名称'}).fill('UI 临时验证');await page.getByRole('button',{name:'保存名称'}).click()
 await page.getByRole('textbox',{name:'搜索历史会话'}).fill('UI 临时验证');await page.getByRole('button',{name:'会话操作'}).click()
 await page.getByRole('button',{name:'删除会话',exact:true}).click();await page.getByRole('button',{name:'删除会话',exact:true}).click()
 await page.getByRole('textbox',{name:'搜索历史会话'}).fill('');await select('formula')
 await page.getByRole('button',{name:'截图相册',exact:true}).click();assert.ok(await page.locator('.gallery-card').count()>=2)
 await page.getByRole('button',{name:'关闭弹窗'}).click();await page.getByRole('button',{name:'返回截图工具'}).click()
 assert.equal(await page.locator('.main-layout').count(),0)
 assert.deepEqual(errors,[])
 await page.waitForTimeout(800)
 console.log('PASS: optional AI workspace, formula validation/edit/persistence/export, editable table/chart/export, custom-image boundary, streaming/cancel, history rename/search/delete, gallery, return to screenshot tool; no browser errors. Only isolated test sessions were changed.')
}finally{for(const id of created)await context.request.delete('http://127.0.0.1:5173/api/sessions/'+id);await browser.close()}
