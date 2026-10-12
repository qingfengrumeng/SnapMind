// Synthetic fixtures and mocked OCR/LLM APIs only; native text copying is exercised.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const browser=await chromium.connectOverCDP('http://127.0.0.1:9223')
const pages=browser.contexts()[0].pages(),main=pages.find(p=>p.url().includes('5174')&&!p.url().includes('desktop=')),capture=pages.find(p=>p.url().includes('desktop=capture'))
const invoke=(command,args)=>main.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})
const stored=await capture.evaluate(()=>localStorage.getItem('snapmind.capture.shortcuts'))
const requests=[]
await capture.route('**/api/capture/process',async route=>{
 const body=route.request().postDataJSON();requests.push(body)
 await route.fulfill({json:{text:body.action==='ocr'?'SNAPMIND OCR TEST 123':'Synthetic '+body.action,mode:'model'}})
})
await capture.route('**/api/capture/locate',route=>{const body=route.request().postDataJSON();return route.fulfill({json:{regions:[{id:'text-1',text:'SNAPMIND OCR TEST 123',bbox:[40,30,490,65],granularity:'line',page:0}],width:body.asset.width,height:body.asset.height,mode:'paddleocr',coordinateSpace:'image-pixels',fallback:false}})})
await capture.route('**/api/capture/translate-inline',route=>{const body=route.request().postDataJSON();requests.push(body);return route.fulfill({json:{lines:body.lines.map(l=>({...l,sourceText:l.text,text:'Synthetic translate'})),width:body.asset.width,height:body.asset.height,language:body.language,coordinateSpace:'image-pixels'}})})
try{
 const asset=await main.evaluate(()=>{const c=document.createElement('canvas');c.width=800;c.height=500;const g=c.getContext('2d');g.fillStyle='white';g.fillRect(0,0,800,500);g.fillStyle='black';g.font='32px Arial';g.fillText('SNAPMIND OCR TEST 123',100,120);g.fillStyle='#2d7df2';g.fillRect(100,300,80,80);return{id:'capture-tools-'+Date.now(),name:'Synthetic tools',data:c.toDataURL('image/png'),width:800,height:500,scenario:'custom'}})
 await invoke('begin_preview_capture',{asset})
 await capture.waitForFunction(id=>document.querySelector('.capture-overlay')?.dataset.sourceId===id&&document.querySelector('.capture-overlay')?.dataset.ready==='true',asset.id)
 for(let n=0;n<50&&!(await invoke('native_status')).windows.capture.visible;n++)await main.waitForTimeout(20)
 await capture.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))
 const box=await capture.locator('.capture-screen').boundingBox(),point=(x,y)=>({x:box.x+x*box.width/800,y:box.y+y*box.height/500})
 async function clickPoint(x,y){const p=point(x,y);await capture.mouse.click(p.x,p.y)}
 const a=point(60,60),z=point(740,440);await capture.mouse.move(a.x,a.y);await capture.mouse.down();await capture.mouse.move(z.x,z.y);await capture.mouse.up()
 await capture.getByRole('button',{name:'截图序号',exact:true}).click()
 const sequence=capture.getByRole('spinbutton',{name:'起始序号'});await sequence.fill('7');await clickPoint(250,250);assert.equal(await sequence.inputValue(),'8');await capture.getByRole('button',{name:'撤销截图标注'}).click();assert.equal(await sequence.inputValue(),'7')
 await capture.getByRole('button',{name:'截图取色',exact:true}).click();const blue=point(140,340);await capture.mouse.move(blue.x,blue.y);await capture.waitForFunction(()=>document.querySelector('.capture-loupe-color strong')?.textContent==='#2D7DF2')
 await capture.keyboard.press('Shift');assert.equal(await capture.locator('.capture-loupe-color strong').textContent(),'RGB(45, 125, 242)');await capture.keyboard.press('q')
 await capture.getByRole('button',{name:'提取文字',exact:true}).click();await capture.getByRole('textbox',{name:'处理结果'}).waitFor({timeout:60000});assert.match(await capture.getByRole('textbox',{name:'处理结果'}).inputValue(),/123/)
 await capture.getByRole('button',{name:'复制结果'}).click();await capture.getByRole('button',{name:'关闭处理结果'}).click()
 await capture.getByRole('button',{name:'翻译',exact:true}).click();await capture.getByLabel('截图原位译文').waitFor();await capture.getByRole('button',{name:'翻译语言',exact:true}).click();await capture.getByRole('listbox').getByRole('option',{name:'English',exact:true}).click();await capture.getByLabel('截图原位译文').waitFor();assert.equal(await capture.locator('.capture-translated-line').innerText(),'Synthetic translate');assert.equal(requests.at(-1).language,'en');assert.equal(await capture.locator('.capture-process-result').count(),0)
 await capture.keyboard.press('Escape');assert.equal(await capture.locator('.capture-process-result').count(),0);assert.equal((await invoke('get_desktop_state')).captureActive,true)
 assert.equal(await capture.getByRole('button',{name:'工具快捷键',exact:true}).count(),0)
 assert.equal(await capture.getByRole('button',{name:'保存截图',exact:true}).isEnabled(),true)
 console.log('PASS: editable sequence and undo, RGB/HEX picker, result copying and inline translation with language selection. Synthetic fixtures and mocked APIs.')
}finally{
 await capture.unroute('**/api/capture/process');await capture.unroute('**/api/capture/locate');await capture.unroute('**/api/capture/translate-inline');await invoke('cancel_capture').catch(()=>{});await capture.evaluate(value=>value===null?localStorage.removeItem('snapmind.capture.shortcuts'):localStorage.setItem('snapmind.capture.shortcuts',value),stored);await browser.close()
}
