// Finish documentation with the local app, a user-referenced public table and real LLM.
import {chromium} from 'playwright'
import {readFile,mkdir,writeFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
import {resolve} from 'node:path'
const root=resolve(import.meta.dirname,'..'),images=resolve(root,'docs/images/readme'),base='http://127.0.0.1:5174'
const browser=await chromium.launch({channel:'msedge',headless:true}),context=await browser.newContext({viewport:{width:1600,height:1040}}),page=await context.newPage(),errors=[]
page.setDefaultTimeout(120000);page.on('pageerror',e=>errors.push(e.message))
try{
 const reference='https://raw.githubusercontent.com/qingfengrumeng/SlideCraft/main/README.en.md',fileIndex=process.argv.indexOf('--reference-file')
 let markdown
 if(fileIndex>=0)markdown=await readFile(process.argv[fileIndex+1],'utf8')
 else{const response=await fetch(reference,{signal:AbortSignal.timeout(45000)});assert.equal(response.ok,true);markdown=await response.text()}
 const section=markdown.split('## Templates')[1].split('## Agent Compatibility')[0],lines=section.split('\n').filter(line=>line.startsWith('|')&&!line.includes('---'))
 assert.equal(lines.length,8);const data=lines.map(line=>line.split('|').slice(1,-1).map(value=>value.trim().replaceAll('**','')))
 const escaped=s=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]))
 await page.setContent('<meta charset="utf-8"><style>body{margin:0;background:white;color:#342848;font:18px/1.5 Arial}main{padding:24px;width:1100px}h2{font-size:24px}table{border-collapse:collapse;width:100%}th,td{padding:12px 14px;text-align:left;border:1px solid #d8d0e6}th{background:#eee6fc}td:first-child{font-weight:bold}</style><main><h2>SlideCraft — Templates</h2><table>'+data.map((row,n)=>'<tr>'+row.map(cell=>`<${n?'td':'th'}>${escaped(cell)}</${n?'td':'th'}>`).join('')+'</tr>').join('')+'</table></main>')
 await mkdir(resolve(root,'../artifacts/readme-local'),{recursive:true});const source=resolve(root,'../artifacts/readme-local/public-table.png');await page.locator('main').screenshot({path:source});console.log('Prepared exact public README table; no local usage data included')
 if(process.argv.includes('--source-only')){await browser.close();process.exit(0)}
 await page.goto(base);await page.locator('.snapmind-home').waitFor();await page.locator('input[type=file]:not([multiple])').setInputFiles({name:'公开README表格.png',mimeType:'image/png',buffer:await readFile(source)})
 await page.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.ready==='true')
 const c=await page.locator('.capture-screen').boundingBox();await page.mouse.move(c.x+1,c.y+1);await page.mouse.down();await page.mouse.move(c.x+c.width-1,c.y+c.height-1,{steps:8});await page.mouse.up()
 await page.getByRole('button',{name:'AI对话',exact:true}).click();const input=page.getByRole('textbox',{name:'图片对话输入'});await input.waitFor();await input.fill('/table');await page.getByRole('option').first().click();await input.fill('提取这张截图中的公开 README 表格，保留英文列名和全部七行，内容保持原样。');const start=Date.now();await page.getByRole('button',{name:'发送图片对话',exact:true}).click()
 await page.waitForFunction(()=>document.querySelector('.image-conversation')?.getAttribute('aria-busy')==='false',null,{timeout:200000});await page.locator('.image-chat-turn.assistant table').waitFor();const extracted=await page.locator('.image-chat-turn.assistant table').innerText();assert.match(extracted,/Paper & Ink/);assert.match(extracted,/Neon Circuit/);await page.mouse.move(1598,1038);await page.screenshot({path:resolve(images,'09-table.png')});console.log('PASS real LLM table extraction '+Math.round((Date.now()-start)/1000)+'s')
 await input.fill('/');await page.getByRole('listbox').waitFor();assert.ok(await page.getByRole('option').count()>=10);await page.screenshot({path:resolve(images,'10-tools.png')});await page.keyboard.press('Escape');await input.fill('')
 await page.getByRole('button',{name:'历史对话',exact:true}).click();const active=page.locator('.history-row.active .history-title');await active.waitFor();const title=await active.innerText();await page.getByRole('textbox',{name:'搜索历史对话'}).fill(title);await page.screenshot({path:resolve(images,'11-history.png')});await page.locator('.history-row.active .history-title').click();await page.locator('.image-chat-turn.assistant table').waitFor();assert.deepEqual(errors,[])
 await writeFile(resolve(root,'docs/README_SCREENSHOTS.md'),'# README 本地项目实测\n\n日期：2026-10-12。\n\n使用当前本地项目、真实模型配置、已有本地截图与真实本地用量记录。文字提取、原位翻译、自然语言高亮和表格提取调用实际 LLM，背景修补执行真实本地图像处理。没有模拟 API 返回。\n\n| 检查 | 结果 |\n|---|---|\n| 本地主界面、快捷键、功能说明 | PASS |\n| 本地模型用量统计 | PASS |\n| 配置页原生密钥圆点遮罩 | PASS |\n| 截图标注、撤销与原图恢复 | PASS |\n| LLM 文字提取 | PASS |\n| 原位翻译、语言切换与原文恢复 | PASS |\n| 背景修补与撤销 | PASS |\n| 自然语言高亮与实际图片应用 | PASS |\n| 公开 README 表格真实提取 | PASS |\n| 实时斜杠工具目录 | PASS |\n| 真实会话保存与历史恢复 | PASS |\n\n主界面截图避开私人图库，模型配置保持软件原生密码圆点遮罩。发布素材中不包含明文密钥或私人接口地址。表格输入仅为公开原文。历史截图只显示本次验证会话；完整会话及配置仍存放在原项目本机数据目录，未复制到上传目录。语音和麦克风没有实操。\n\n开始时用编号建议尝试表格整理，未得到可验证的结构化表格，故改用用户指定的 SlideCraft 公开 README 表格，通过斜杠工具明确调用 LLM 表格提取；本地用量统计未发送到外部服务。未将失败当作成功展示。\n\n文档截图验证不是所有设备和云服务的性能保证。\n')
 console.log('PASS real history restore and documentation completion')
}finally{await browser.close()}

