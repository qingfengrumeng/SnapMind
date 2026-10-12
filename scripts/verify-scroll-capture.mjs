import {chromium} from 'playwright'
import assert from 'node:assert/strict'
import {execFileSync} from 'node:child_process'
const host=await chromium.connectOverCDP('http://127.0.0.1:9223'),pages=host.contexts()[0].pages(),main=pages.find(p=>p.url().includes('5174')&&!p.url().includes('desktop=')),capture=pages.find(p=>p.url().includes('desktop=capture'))
const invoke=(command,args)=>main.evaluate(({command,args})=>window.__TAURI_INTERNALS__.invoke(command,args),{command,args})
if((await invoke('get_desktop_state')).captureActive){await host.close();throw Error('Finish the current screenshot before running verification')}
const browser=await chromium.launch({channel:'msedge',headless:false,args:['--window-position=180,100','--window-size=1100,800']})
try{
 await capture.reload()
 const pageErrors=[];capture.on('pageerror',e=>pageErrors.push(e.message))
 const page=await browser.newPage({viewport:{width:1000,height:650}})
 await page.setContent('<title>SnapMind scroll fixture</title><style>body{margin:0}#marker{position:fixed;left:0;top:0;bottom:0;width:24px;background:rgb(228,20,51)}canvas{display:block;margin-left:24px}</style><div id="marker"></div><canvas width="1000" height="6000"></canvas>')
 await page.evaluate(()=>{const c=document.querySelector('canvas'),g=c.getContext('2d');g.fillStyle='#f8f9fb';g.fillRect(0,0,1000,6000);g.font='16px Consolas';g.fillStyle='#3b414a';let seed=781;for(let y=0;y<6000;y+=24){let words='';for(let x=0;x<80;x++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;words+=String.fromCharCode(97+(seed%26))}g.fillText(`${String(y/24+1).padStart(3,'0')}  ${words}`,15,y+18)}})
 await page.evaluate(()=>scrollTo(0,200));await page.bringToFront();await page.mouse.click(100,100);console.log(execFileSync('python',['scripts/focus-scroll-fixture.py']).toString());await page.waitForTimeout(300)
 await invoke('begin_capture');const id=(await invoke('get_desktop_state')).frame.asset.id;await capture.waitForFunction(id=>document.querySelector('.capture-overlay')?.dataset.sourceId===id&&document.querySelector('.capture-overlay')?.dataset.ready==='true',id)
 for(let n=0;n<50&&!(await invoke('native_status')).windows.capture.visible;n++)await main.waitForTimeout(20)
 await capture.evaluate(()=>new Promise(r=>requestAnimationFrame(()=>requestAnimationFrame(r))))
 const rect=await capture.locator('.capture-screen').evaluate(c=>{const d=c.getContext('2d').getImageData(0,0,c.width,c.height).data;let x=-1,y=-1;for(let j=0;j<c.height&&x<0;j++)for(let i=0;i<c.width;i++){const n=(j*c.width+i)*4;if(d[n]===228&&d[n+1]===20&&d[n+2]===51){x=i;y=j;break}}if(x<0)throw Error('Synthetic marker not found');return{x:x+70,y:y+60,w:500,h:350}})
 const box=await capture.locator('.capture-screen').boundingBox(),size=await capture.locator('.capture-screen').evaluate(c=>({w:c.width,h:c.height})),point=(x,y)=>({x:box.x+x*box.width/size.w,y:box.y+y*box.height/size.h})
 const a=point(rect.x,rect.y),z=point(rect.x+rect.w,rect.y+rect.h);await capture.mouse.move(a.x,a.y);await capture.mouse.down();await capture.mouse.move(z.x,z.y);await capture.mouse.up()
 await capture.getByRole('button',{name:'\u6eda\u52a8\u622a\u56fe',exact:true}).click()
 const bar=capture.locator('.scroll-capture-toolbar');await capture.waitForFunction(()=>document.querySelector('.capture-overlay')?.classList.contains('scroll-live')&&Number(document.querySelector('.scroll-capture-toolbar')?.dataset.height)>0,undefined,{timeout:5000})
 assert.equal(await bar.getByRole('button').count(),4);assert.equal(await capture.locator('.capture-tool-options').count(),0)
 const center=point(rect.x+rect.w/2,rect.y+rect.h/2),scale=(await invoke('get_desktop_state')).frame.scaleFactor
 let maxScroll=await page.evaluate(()=>scrollY),minScroll=maxScroll
 const origin=(await invoke('get_desktop_state')).frame
 const physical=p=>({x:Math.round(p.x*scale+origin.x),y:Math.round(p.y*scale+origin.y)})
 async function input(mode,p,delta){const q=physical(p);return JSON.parse(execFileSync('python',['scripts/scroll-user-input.py',mode,String(q.x),String(q.y),String(delta||0)]).toString())}
 let foreground
 async function wheel(delta){const report=await input('wheel',center,-delta);foreground??=report.foreground;assert.equal(report.foreground,foreground,'Original application must retain focus');await page.waitForTimeout(500);const y=await page.evaluate(()=>scrollY);maxScroll=Math.max(maxScroll,y);minScroll=Math.min(minScroll,y);const after=await input('inspect',center);assert.deepEqual(after,report,'Background sampling must not move the pointer or change foreground');assert.equal(await capture.locator('.scroll-capture-message').count(),0);assert.equal(await bar.getByRole('button').count(),4);return y}
 const start=await page.evaluate(()=>scrollY);const down=await wheel(120);assert.ok(down>start);await wheel(120)
 let height=Number(await bar.getAttribute('data-height'));const beforeUp=await page.evaluate(()=>scrollY),up=await wheel(-120);assert.ok(up<beforeUp);assert.equal(Number(await bar.getAttribute('data-height')),height,'Backtracking must not duplicate previously captured rows');await wheel(-120);await wheel(-120);for(let n=0;n<5&&minScroll>=start;n++)await wheel(-120);height=Number(await bar.getAttribute('data-height'));assert.ok(minScroll<start,'Scrolling above the initial viewport must prepend new content')
 await input('burst',center,-60);await page.waitForTimeout(600);maxScroll=Math.max(maxScroll,await page.evaluate(()=>scrollY));height=Number(await bar.getAttribute('data-height'));assert.equal(await capture.locator('.scroll-capture-message').count(),0,'Continuous wheel input must stitch automatically');assert.equal(await capture.locator('.capture-screen').evaluate((c,r)=>c.getContext('2d').getImageData(r.x+10,r.y+10,1,1).data[3],rect),0,'Live selection must expose the actual page, not frozen screenshots')
 assert.ok(Math.abs(height-350-Math.round((maxScroll-minScroll)*scale))<=2,'Stitch length must match the captured physical scroll range')
 const image=capture.getByRole('img',{name:'\u5df2\u62fc\u63a5\u7684\u957f\u622a\u56fe'});await image.evaluate(i=>i.decode());assert.ok(await image.evaluate(i=>i.naturalHeight)<=330)
 const edit=await bar.getByRole('button',{name:'\u7f16\u8f91\u957f\u622a\u56fe'}).boundingBox();await input('click',{x:edit.x+edit.width/2,y:edit.y+edit.height/2});await capture.waitForFunction(()=>document.querySelector('.capture-overlay')?.dataset.sourceId.endsWith('-edit')&&document.querySelector('.capture-overlay')?.dataset.ready==='true')
 assert.equal(await capture.locator('.scroll-capture-toolbar').count(),0);assert.equal(await capture.locator('.capture-screen').evaluate(c=>c.height),height);assert.equal(await capture.locator('.capture-handle').count(),8)
 await invoke('cancel_capture');await page.bringToFront();console.log(execFileSync('python',['scripts/focus-scroll-fixture.py']).toString());await invoke('begin_capture');const second=(await invoke('get_desktop_state')).frame.asset.id;await capture.waitForFunction(id=>document.querySelector('.capture-overlay')?.dataset.sourceId===id&&document.querySelector('.capture-overlay')?.dataset.ready==='true',second);await capture.mouse.move(a.x,a.y);await capture.mouse.down();await capture.mouse.move(z.x,z.y);await capture.mouse.up();await capture.getByRole('button',{name:'\u6eda\u52a8\u622a\u56fe',exact:true}).click();await capture.waitForFunction(()=>document.querySelector('.capture-overlay')?.classList.contains('scroll-live'));
 const done=await capture.getByRole('button',{name:'\u5b8c\u6210\u5e76\u590d\u5236\u957f\u622a\u56fe',exact:true}).boundingBox();await input('click',{x:done.x+done.width/2,y:done.y+done.height/2});await capture.waitForFunction(()=>!document.querySelector('.capture-overlay'));assert.equal((await invoke('get_desktop_state')).captureActive,false);assert.equal((await invoke('native_status')).windows.capture.visible,false)
 assert.deepEqual(pageErrors,[])
 console.log('PASS: click-to-start wheel scrolling, four compact controls, automatic thumbnail, bidirectional scrolling without duplicate rows and full long-image editing. Height:',height)

}finally{await invoke('cancel_capture').catch(()=>{});await browser.close();await host.close()}
