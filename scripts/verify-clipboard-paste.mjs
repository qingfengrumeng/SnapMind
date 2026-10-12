// Run after verify-capture-completion.mjs, which copies a synthetic 120x80 purple crop.
// Ctrl+V uses the actual Windows clipboard in a separate, temporary browser window.
import {chromium} from 'playwright'
import assert from 'node:assert/strict'
const expected=process.argv[2]?JSON.parse(process.argv[2]):{width:120,height:80,pixel:[117,56,238,255]}
const browser=await chromium.launch({channel:'msedge',headless:false,args:['--window-size=500,350']})
try{
 const page=await browser.newPage()
 await page.setContent('<div contenteditable="true" id="target" style="padding:30px">SnapMind clipboard test</div>')
 await page.evaluate(()=>{
  document.querySelector('#target').addEventListener('paste',async e=>{
   e.preventDefault()
   const file=Array.from(e.clipboardData.items).find(item=>item.kind==='file'&&item.type.startsWith('image/'))?.getAsFile()
   if(!file){window.pasted={error:'Clipboard did not contain an image'};return}
   const bitmap=await createImageBitmap(file),canvas=document.createElement('canvas');canvas.width=bitmap.width;canvas.height=bitmap.height
   canvas.getContext('2d').drawImage(bitmap,0,0)
   window.pasted={width:bitmap.width,height:bitmap.height,pixel:Array.from(canvas.getContext('2d').getImageData(0,0,1,1).data)}
   bitmap.close()
  })
 })
 await page.locator('#target').click()
 await page.keyboard.press('Control+V')
 await page.waitForFunction(()=>window.pasted,{},{timeout:5000})
 assert.deepEqual(await page.evaluate(()=>window.pasted),expected)
 console.log('PASS: Ctrl+V pastes the completed crop with exact dimensions and pixels in another application window.')
}finally{await browser.close()}
