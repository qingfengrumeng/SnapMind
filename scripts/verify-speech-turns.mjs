// Pure timing/cleanup checks; no microphone, network or model calls.
import assert from 'node:assert/strict'
import {createSpeechTurns,isSpeechFiller} from '../frontend/src/speech-turns.ts'
const sleep=ms=>new Promise(r=>setTimeout(r,ms)),turns=[]
const input=createSpeechTurns(text=>turns.push(text),25)
input.push('请把截图里的文字');await sleep(10);input.speechStarted();await sleep(35)
assert.deepEqual(turns,[],'Resumed speech must hold the partial query')
input.push('原位翻译成英文');await sleep(40)
assert.deepEqual(turns,['请把截图里的文字 原位翻译成英文'])
input.push('撤销刚才的操作');await sleep(40)
assert.equal(turns.at(-1),'撤销刚才的操作','Separate turns must not inherit old text')
input.push('取消后的内容');input.reset();await sleep(40)
assert.equal(turns.length,2,'Hangup/cancel must suppress pending turns')
for(const text of ['嗯。','嗯，嗯。','呃……','啊','哦','hmm.','um','...']){
 assert.equal(isSpeechFiller(text),true)
 input.push(text);await sleep(40)
}
assert.equal(turns.length,2,'Filler-only recognition never submits an automatic turn')
for(const text of ['撤销','好','不','嗯，请撤销刚才的操作','解释截图'])assert.equal(isSpeechFiller(text),false,'Short commands and content following a hesitation stay valid')
input.push('嗯，请撤销刚才的操作');await sleep(40);assert.equal(turns.at(-1),'嗯，请撤销刚才的操作')
console.log('PASS: resumed VAD fragments join once, normal turn commits, subsequent turns remain separate, cancel clears pending callbacks.')
