// Run against the current local SnapMind project with its real API and data.
// Usage: node scripts/capture-readme-local.mjs --image <reviewed-local-image>
// No mocked API responses, no audio capture. Creates a real documentation conversation.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {mkdir,readFile,writeFile} from 'node:fs/promises'
import {resolve} from 'node:path'
const root=resolve(import.meta.dirname,'..'),folder=resolve(root,'docs/images/readme'),base=process.env.SNAPMIND_DOCS_URL||'http://127.0.0.1:5174'
const imageArg=process.argv.indexOf('--image'),input=imageArg>=0?process.argv[imageArg+1]:undefined
if(!input)throw Error('Provide a local screenshot already reviewed for publication with --image')
await mkdir(folder,{recursive:true})
const browser=await chromium.launch({channel:'msedge',headless:true}),rows=[],errors=[]
const context=await browser.newContext({viewport:{width:1600,height:1040},deviceScaleFactor:1}),page=await context.newPage()
page.setDefaultTimeout(120000);page.on('pageerror',e=>errors.push(e.message))
const started=Date.now(),button=name=>page.getByRole('button',{name,exact:true}),screen=page.locator('.capture-screen')
async function shot(name,selector,clip){await page.evaluate(()=>document.fonts.ready);if(await page.locator('.capture-overlay').count())await page.locator('.capture-overlay').focus();await page.mouse.move(1598,1038);await page.waitForTimeout(350);if(selector)await page.locator(selector).screenshot({path:resolve(folder,name+'.png')});else await page.screenshot({path:resolve(folder,name+'.png'),clip});console.log('Captured '+name)}
async function check(name,fn){const t=Date.now();await fn();rows.push({name,status:'PASS',seconds:Math.round((Date.now()-t)/100)/10});console.log('PASS '+name)}
const click=name=>button(name).click()
try{
 await page.goto(base);await page.locator('.snapmind-home').waitFor()
 await check('真实本地主界面',async()=>{const home=await page.locator('.snapmind-home').boundingBox(),banner=await page.locator('.launcher-banner').boundingBox();await shot('01-home',undefined,{x:home.x,y:home.y,width:home.width,height:banner.y+banner.height-home.y+20})})
 if(!process.argv.includes('--skip-ui')){
 await click('设置与工具')
 await check('真实快捷键与功能说明',async()=>{await page.locator('#general-shortcuts').scrollIntoViewIfNeeded();await shot('02-settings','.snapmind-home');await page.getByRole('tab',{name:'功能',exact:true}).click();await page.locator('.function-card').first().waitFor();await shot('03-functions','.snapmind-home')})
 await page.getByRole('tab',{name:'使用统计',exact:true}).click()
 await check('真实本地模型用量统计',async()=>{await page.locator('.usage-summary-cards').waitFor();await shot('13-usage','.snapmind-home')})
 await page.getByRole('tab',{name:'模型配置',exact:true}).click()
 await check('真实模型配置界面，密钥使用原生遮罩',async()=>{
  await page.locator('.model-profile').first().waitFor();await page.locator('.model-profile-expand').first().click();await page.locator('.model-profile-form').first().waitFor()
  assert.equal(await page.locator('.model-profile.expanded input[type=password]').count(),1)
  await shot('12-models','.model-profile.expanded')
 })
 await click('关闭设置面板')
 if(process.argv.includes('--settings-only')){console.log('Configuration screenshots updated with native password masking');await browser.close();process.exit(0)}
 }
 await page.locator('input[type=file][accept="image/png,image/jpeg,image/webp"]:not([multiple])').setInputFiles({name:'截图示例.png',mimeType:'image/png',buffer:await readFile(input)})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const bounds=await screen.boundingBox(),size=await screen.evaluate(c=>({width:c.width,height:c.height})),point=(x,y)=>({x:bounds.x+x*bounds.width/size.width,y:bounds.y+y*bounds.height/size.height})
 const drag=async(x,y,x2,y2)=>{const a=point(x,y),b=point(x2,y2);await page.mouse.move(a.x,a.y);await page.mouse.down();await page.mouse.move(b.x,b.y,{steps:12});await page.mouse.up()}
 await drag(0,0,size.width-1,size.height-1)
 const original=await screen.evaluate(c=>c.toDataURL())
 await check('真实本地截图标注与撤销',async()=>{await click('截图矩形');await drag(78,245,size.width-55,290);await click('截图箭头');await drag(370,345,260,286);assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original);await shot('04-annotate');await click('撤销截图标注');await click('撤销截图标注');assert.equal(await screen.evaluate(c=>c.toDataURL()),original)})
 await check('本地截图真实 LLM 文字提取',async()=>{await click('提取文字');await page.waitForFunction(()=>document.querySelector('.capture-process-result')?.getAttribute('aria-busy')==='false');assert.equal(await page.locator('.capture-process-error').count(),0);const text=await page.getByRole('textbox',{name:'处理结果'}).inputValue();assert.match(text,/DeepSeek/);await shot('05-ocr');await click('关闭处理结果')})
 await check('本地截图真实原位翻译及原文切换',async()=>{await click('翻译');await click('翻译语言');await page.getByRole('option',{name:'English',exact:true}).click();await page.getByLabel('截图原位译文',{exact:true}).waitFor();const texts=await page.locator('.capture-translated-line').allTextContents();assert.ok(texts.some(t=>/[A-Za-z]{4}/.test(t)));assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original);await shot('06-translation');await click('查看原文');assert.equal(await screen.evaluate(c=>c.toDataURL()),original);await click('撤销截图标注')})
 await check('本地截图真实背景修补与撤销',async()=>{await click('截图涂抹消除');await click('涂抹消除画刷 40');await drag(90,353,365,353);await page.waitForFunction(()=>document.querySelector('[aria-label="撤销截图标注"]')?.disabled===false);assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original);await shot('07-erase');await click('撤销截图标注');assert.equal(await screen.evaluate(c=>c.toDataURL()),original)})
 await click('AI对话');await page.getByRole('textbox',{name:'图片对话输入'}).waitFor()
 const send=async text=>{await page.getByRole('textbox',{name:'图片对话输入'}).fill(text);await click('发送图片对话');await page.waitForFunction(()=>document.querySelector('.image-conversation')?.getAttribute('aria-busy')==='false',null,{timeout:200000});assert.equal(await page.locator('.image-chat-error').count(),0)}
 await check('真实 LLM 意图识别与截图高亮',async()=>{await send('请高亮截图中“换个问题”这一行，完成后一句话回复。');assert.notEqual(await screen.evaluate(c=>c.toDataURL()),original);await shot('08-agent')})
 await check('真实 LLM 表格整理',async()=>{await send('请调用表格提取工具，把截图中两条编号建议整理为序号、操作、说明三列，保留截图的原文，不补充截图没有的信息。');await page.locator('.image-chat-turn.assistant table').last().waitFor();const text=await page.locator('.image-chat-turn.assistant table').last().innerText();assert.match(text,/DeepSeek/);await shot('09-table')})
 await check('真实工具目录',async()=>{await page.getByRole('textbox',{name:'图片对话输入'}).fill('/');await page.getByRole('listbox').waitFor();assert.ok(await page.getByRole('option').count()>=10);await shot('10-tools');await page.keyboard.press('Escape');await page.getByRole('textbox',{name:'图片对话输入'}).fill('')})
 await check('真实会话保存与历史恢复',async()=>{
  await click('历史对话');await page.locator('.history-title').first().waitFor()
  const active=page.locator('.history-row.active .history-title');await active.waitFor();const label=await active.innerText()
  await page.getByRole('textbox',{name:'搜索历史对话'}).fill(label);await shot('11-history');await page.locator('.history-row.active .history-title').click();await page.locator('.image-chat-turn.assistant table').last().waitFor()
 })
 assert.deepEqual(errors,[])
 const report=['# README 本地项目实测','','日期：2026-10-12。', '', '运行当前本地项目，使用现有本地后端、模型配置、本地截图与真实 LLM。没有模拟 API 返回。主界面截图避开私人图库；模型配置输入内容已遮蔽；历史截图仅显示本次验证会话。语音未实操。','','表格展示来自对实际截图中的编号建议进行结构化整理；不是虚构的商品表格。测试会话保存于原项目本地数据，不复制到上传目录。','','| 功能 | 结果 | 本次耗时 |','|---|---|---:|',...rows.map(r=>`| ${r.name} | ${r.status} | ${r.seconds} 秒 |`),'',`整轮 ${Math.round((Date.now()-started)/1000)} 秒，包含加载、截图及人工等待。耗时不是性能保证。`,'','重新截图时传入经过隐私检查的本地截图；本脚本会调用已配置的模型并创建真实会话，语音与麦克风不会启动。']
 await writeFile(resolve(root,'docs/README_SCREENSHOTS.md'),report.join('\n')+'\n');console.log('Local project documentation checks passed')
}finally{await browser.close()}
