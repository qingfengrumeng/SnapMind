import ts from 'typescript'
import {readFile} from 'node:fs/promises'
import assert from 'node:assert/strict'
const source=await readFile('frontend/src/scroll-stitch.ts','utf8'),js=ts.transpileModule(source,{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText
const {scrollOffset}=await import('data:text/javascript;base64,'+Buffer.from(js).toString('base64'))
function frame(start,width=120,height=350){const data=new Uint8ClampedArray(width*height*4);let seed=781;const rows=[];for(let y=0;y<start+height;y++){seed=(Math.imul(seed,1664525)+1013904223)>>>0;rows.push(seed)}for(let y=0;y<height;y++)for(let x=0;x<width;x++){const n=(y*width+x)*4,value=rows[y+start];data[n]=((value>>>16)+x)&255;data[n+1]=((value>>>8)+x)&255;data[n+2]=(value+x)&255;data[n+3]=255}return{width,height,data}}
assert.equal(scrollOffset(frame(0),frame(0)),0)
assert.equal(scrollOffset(frame(0),frame(73)),73)
assert.equal(scrollOffset(frame(73),frame(146)),73)
assert.equal(scrollOffset(frame(0),frame(250)),250)
assert.equal(scrollOffset(frame(0),frame(600)),null)
assert.equal(scrollOffset(frame(146),frame(73)),-73)
assert.equal(scrollOffset(frame(250),frame(0)),-250)
assert.equal(scrollOffset(frame(0),frame(0,100)),null)
console.log('PASS: exact overlap offsets, repeated frames, subsequent frames, unmatched content and mismatched dimensions.')
