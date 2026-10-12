// Reopen only this documentation session. No LLM calls or mocked responses.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {readFile} from 'node:fs/promises'
import {resolve} from 'node:path'
const root=resolve(import.meta.dirname,'..'),base='http://127.0.0.1:5174'
const browser=await chromium.launch({channel:'msedge',headless:true}),page=await browser.newPage({viewport:{width:1600,height:1040}})
try{
 await page.goto(base);await page.locator('.snapmind-home').waitFor()
 const found=await page.evaluate(async()=>{
  const history=await(await fetch('/api/image-history')).json()
  for(const item of history.slice(0,12)){
   const session=await(await fetch('/api/sessions/'+encodeURIComponent(item.id))).json()
   if(!session.messages?.some(m=>m.role==='user'&&m.text==='提取这张截图中的公开 README 表格，保留英文列名和全部七行，内容保持原样。'))continue
   await fetch('/api/sessions/'+encodeURIComponent(item.id)+'/metadata',{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({title:'SlideCraft 表格提取'})})
   return true
  }
  return false
 });assert.equal(found,true,'Only the documentation session may be renamed')
 await page.locator('input[type=file]:not([multiple])').setInputFiles({name:'公开README表格.png',mimeType:'image/png',buffer:await readFile(resolve(root,'../artifacts/readme-local/public-table.png'))})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const bounds=await page.locator('.capture-screen').boundingBox();await page.mouse.move(bounds.x+1,bounds.y+1);await page.mouse.down();await page.mouse.move(bounds.x+bounds.width-1,bounds.y+bounds.height-1,{steps:4});await page.mouse.up();await page.getByRole('button',{name:'AI对话',exact:true}).click();await page.getByRole('button',{name:'历史对话',exact:true}).click();await page.getByRole('textbox',{name:'搜索历史对话'}).fill('SlideCraft 表格提取');await page.getByRole('button',{name:'打开 SlideCraft 表格提取',exact:true}).click()
 const table=page.locator('.image-chat-turn.assistant table');await table.waitFor();assert.match(await table.innerText(),/Paper & Ink/);assert.match(await table.innerText(),/Neon Circuit/)
 const resize=await page.getByRole('button',{name:'调整对话面板 w',exact:true}).boundingBox();await page.mouse.move(resize.x+resize.width/2,resize.y+resize.height/2);await page.mouse.down();await page.mouse.move(700,resize.y+resize.height/2,{steps:8});await page.mouse.up();await table.scrollIntoViewIfNeeded();await page.locator('.capture-overlay').focus();await page.mouse.move(1598,1038);await page.waitForTimeout(350);await page.screenshot({path:resolve(root,'docs/images/readme/09-table.png')})
 await page.getByRole('button',{name:'历史对话',exact:true}).click();await page.getByRole('textbox',{name:'搜索历史对话'}).fill('SlideCraft 表格提取');await page.getByRole('button',{name:'打开 SlideCraft 表格提取',exact:true}).waitFor();await page.screenshot({path:resolve(root,'docs/images/readme/11-history.png')});console.log('PASS documentation-session rename, restore and readable table screenshots; no model calls')
}finally{await browser.close()}
