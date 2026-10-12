// Synthetic text and images; mocked model and session endpoints only.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir} from 'node:fs/promises'
const browser=await chromium.launch({channel:'msedge',headless:true})
try{
 const page=await browser.newPage({viewport:{width:1200,height:1000}}),saved=new Map(),calls=[],errors=[]
 page.on('pageerror',e=>errors.push(e.message))
 let fail=false
 await page.route('**/api/**',r=>{const path=new URL(r.request().url()).pathname;if(path==='/api/capture/conversation'){const body=r.request().postDataJSON();calls.push(body);return fail?r.fulfill({status:500,json:{detail:'Synthetic failure'}}):r.fulfill({json:{action:'chat',assetId:null,answer:'Synthetic answer',payload:{}}})}if(path.startsWith('/api/sessions/')&&r.request().method()==='PUT'){const s=r.request().postDataJSON();saved.set(s.id,s);return r.fulfill({json:{}})}return r.fulfill({json:path==='/api/sessions'?[...saved.values()]:{tools:[],items:[]}})})
 await page.goto('http://127.0.0.1:5174')
 await page.evaluate(async()=>{const [{default:Chat},{createApp}]=await Promise.all([import('/src/components/ImageConversation.vue'),import('/node_modules/.vite/deps/vue.js')]);const host=document.createElement('div');host.style.cssText='position:fixed;z-index:1000;left:50%;top:20px;transform:translateX(-50%);width:560px;height:760px;background:white;border:1px solid #e5d6fa;border-radius:18px;overflow:hidden';document.body.append(host);createApp(Chat).mount(host)})
 const input=page.getByRole('textbox',{name:'图片对话输入'}),chips=page.locator('.image-chat-input-box .text-attachment-chip'),send=page.getByRole('button',{name:'发送图片对话'})
 await input.waitFor()
 async function paste(text){return input.evaluate((el,text)=>{const data=new DataTransfer();data.setData('text/plain',text);const event=new ClipboardEvent('paste',{clipboardData:data,bubbles:true,cancelable:true});el.dispatchEvent(event);return event.defaultPrevented},text)}
 assert.equal(await paste('字'.repeat(800)),false);assert.equal(await chips.count(),0)
 assert.equal(await paste('😀'.repeat(800)),false,'Count characters rather than UTF-16 code units')
 await input.fill('已有问题')
 assert.equal(await paste('字'.repeat(801)),true);assert.equal(await chips.count(),1);assert.equal(await input.inputValue(),'已有问题')
 await chips.locator('button').last().click();assert.equal(await chips.count(),0)
 const content='# Synthetic source\n'+('中文😀 <script>window.bad=true</script>\n'.repeat(250))+'END OF FULL TEXT'
 await paste(content);const name=await chips.locator('strong').textContent();assert.match(name,/^粘贴内容-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2}\.txt$/)
 assert.match(await chips.locator('small').textContent(),/KB/)
 await chips.locator('button').first().click();const dialog=page.getByRole('dialog',{name:'文本预览 '+name});await dialog.waitFor();assert.equal(await dialog.locator('pre').textContent(),content);assert.equal(await page.evaluate(()=>window.bad),undefined)
 await mkdir('artifacts/text-attachments',{recursive:true});await page.screenshot({path:'artifacts/text-attachments/preview.png'})
 await dialog.getByRole('button',{name:'关闭文本预览'}).press('Escape');assert.equal(await dialog.count(),0);assert.equal(await page.locator('.image-conversation').count(),1);assert.equal(await input.inputValue(),'已有问题')
 await page.screenshot({path:'artifacts/text-attachments/composer.png'})
 fail=true;await send.click();await page.getByRole('alert').waitFor();assert.equal(await chips.count(),1);assert.equal(await input.inputValue(),'已有问题','Failure keeps draft and attachment')
 fail=false;await send.click();await page.getByText('Synthetic answer',{exact:true}).last().waitFor();assert.equal(await chips.count(),0);assert.ok(calls.at(-1).prompt.includes(content));assert.equal(calls.at(-1).action,undefined,'Natural-language requests go through agent intent recognition')
 await page.waitForFunction(()=>!document.querySelector('.image-conversation').getAttribute('aria-busy')||document.querySelector('.image-conversation').getAttribute('aria-busy')==='false')
 assert.equal([...saved.keys()].filter(id=>id.startsWith('imagechat-')).length,1,'Screenshot conversation saves its messages and attachments to one stable local session');assert.ok(calls.at(-1).sessionId.startsWith('imagechat-'));assert.equal(await page.locator('.image-chat-session,.image-chat-history').count(),0)
 await page.locator('.sent-text-attachments button').click();assert.equal(await page.locator('.text-attachment-content').textContent(),content)
 await page.locator('.text-attachment-lightbox button').click();await paste(content);assert.equal(await send.isEnabled(),true,'Attachment alone can be sent')
 await send.click();await page.getByText('Synthetic answer',{exact:true}).last().waitFor();assert.ok(calls.at(-1).prompt.includes(content))
 await input.fill('保留草稿');await paste('x'.repeat(100001));assert.equal(await chips.count(),0);assert.equal(await input.inputValue(),'保留草稿');assert.deepEqual(errors,[])
 console.log('PASS: 800-character boundary, Unicode count, long paste attachment and exact plain-text preview, removal, failure/retry, full request contents, local conversation history and attachment-only Send. Mocked API only.')
}finally{await browser.close()}
