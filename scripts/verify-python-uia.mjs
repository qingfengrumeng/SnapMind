import {readFile,writeFile,mkdir,rm} from 'node:fs/promises'
import {spawn} from 'node:child_process'
import {resolve} from 'node:path'
import assert from 'node:assert/strict'
const delay=ms=>new Promise(r=>setTimeout(r,ms))
async function worker(body){return new Promise((resolve,reject)=>{const p=spawn('python',['backend/app/windows_uia.py'],{windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,SNAPMIND_PROJECT_DIR:process.cwd()}});let out='',err='';p.stdout.on('data',d=>out+=d);p.stderr.on('data',d=>err+=d);p.on('exit',code=>code?reject(Error(err)):resolve(JSON.parse(out)));p.stdin.end(JSON.stringify(body))})}
{
 const output=resolve('artifacts/image-tools/python-controls');await mkdir(output,{recursive:true});await rm(resolve(output,'fixture.json'),{force:true});await rm(resolve(output,'command.json'),{force:true})
 const fixture=spawn('python',['scripts/windows-control-fixture.py','--output',output],{windowsHide:true,stdio:['ignore','ignore','pipe']});let fixtureError='';fixture.stderr.on('data',d=>fixtureError+=d)
 try{let info;for(let i=0;i<100;i++){try{info=JSON.parse(await readFile(resolve(output,'fixture.json'),'utf8'));break}catch{}if(fixture.exitCode!==null)throw Error(fixtureError);await delay(100)}assert.ok(info,'Fixture unavailable')
  {const controls=await worker({...info,excludePid:0,action:'controls'});assert.ok(controls.find(c=>c.text==='Save'));const input=controls.find(c=>c.controlType==='Edit');assert.ok(input);assert.equal(input.text,'Username');for(const action of ['window','fill','snapshot-start','snapshot-next','snapshot-restore'])await assert.rejects(worker({...info,excludePid:0,action}),'Removed operation must be unsupported');await writeFile(resolve(output,'results.json'),JSON.stringify({controls,removedActionsRejected:true},null,2));console.log('PASS: Python COM controls; window selection and fill removed')}
 }finally{await writeFile(resolve(output,'command.json'),JSON.stringify({action:'close'}));await delay(250);if(fixture.exitCode===null)fixture.kill()}
}
