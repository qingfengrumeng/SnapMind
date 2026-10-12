import type {UsageAnalytics,UsageMetrics} from './api'
import {invoke,isTauri} from '@tauri-apps/api/core'
import {usageTokens} from './usage-tokens'
function value(number:number|null|undefined){return String(number??0)}
function md(text:unknown){return String(text).replace(/[\\`*_<>]/g,'\\$&').replace(/\|/g,'\\|').replace(/[\r\n]+/g,' ')}
function cell(text:unknown){const raw=String(text??'');return '"'+(/^[\s]*[=+@-]/.test(raw)?"'"+raw:raw).replace(/"/g,'""')+'"'}
const llmHeaders=['请求次数','输入 Token','输入（命中缓存）','输入（未命中缓存）','输出','总 Token']
function numbers(row:UsageMetrics,kind:UsageAnalytics['kind']){const tokens=usageTokens(row);return kind==='ocr'?[row.requests]:[row.requests,tokens.input,tokens.cached,tokens.uncached,tokens.output,tokens.total]}
function table(headers:string[],rows:unknown[][]){return ['| '+headers.map(md).join(' | ')+' |','| '+headers.map(()=>'---').join(' | ')+' |',...rows.map(row=>'| '+row.map(md).join(' | ')+' |')].join('\n')}
export function usageExportDocuments(data:UsageAnalytics){
 const kind=data.kind.toUpperCase(),period=data.range.start+' ~ '+data.range.end,headers=data.kind==='llm'?llmHeaders:['调用次数']
 const lines=['# SnapMind '+kind+' 使用统计','',`时间范围：${period}（北京时间）`,`时间粒度：${data.range.granularity==='hour'?'小时':'天'}`,'','## 用量汇总','',table(headers,[numbers(data.summary,data.kind).map(value)]),'','## 模型明细','',table(['模型',...headers],data.models.map(row=>[row.model,...numbers(row,data.kind).map(value)])),'','## 使用趋势','',table(['时间',...headers],data.trend.map(point=>[point.key.replace('T',' '),...numbers(point,data.kind).map(value)]))]
 lines.splice(4,0,data.kind==='ocr'?`使用模型数：${data.models.length}`:`缓存命中率：${data.summary.cacheHitRate??0}%`)
 for(const model of data.modelTrends)lines.push('','## '+md(model.model)+' 使用趋势','',table(['时间',...headers],model.points.map(point=>[point.key.replace('T',' '),...numbers(point,data.kind).map(value)])))
 if(data.summary.unbucketedRequests)lines.push('',`${data.summary.unbucketedRequests} 次请求缺少小时信息，已计入汇总，未分配到小时柱形图。`)
 if(data.summary.unreportedRequests)lines.push('',`${data.summary.unreportedRequests} 次请求未上报 Token 用量，已计入请求次数。`)
 const csvRows:unknown[][]=[['记录类型','统计类型','开始日期','结束日期','时区','模型','时间',...headers,'缺少小时明细次数',...(data.kind==='llm'?['缓存命中率（%）']:['使用模型数'])]]
 const append=(type:string,model:string,time:string,row:UsageMetrics)=>csvRows.push([type,kind,data.range.start,data.range.end,data.range.timezone,model,time,...numbers(row,data.kind),row.unbucketedRequests,...(data.kind==='llm'?[row.cacheHitRate??0]:[type==='汇总'?data.models.length:''])])
 append('汇总','','',data.summary);data.models.forEach(row=>append('模型',row.model,'',row));data.trend.forEach(point=>append('总体趋势','',point.key.replace('T',' '),point));data.modelTrends.forEach(model=>model.points.forEach(point=>append('模型趋势',model.model,point.key.replace('T',' '),point)))
 return {markdown:lines.join('\n')+'\n',csv:'\uFEFF'+csvRows.map(row=>row.map(cell).join(',')).join('\r\n')+'\r\n'}
}
const crcTable=Uint32Array.from({length:256},(_,index)=>{let value=index;for(let bit=0;bit<8;bit++)value=value&1?0xedb88320^(value>>>1):value>>>1;return value>>>0})
function crc32(data:Uint8Array){let crc=0xffffffff;for(const byte of data)crc=crcTable[(crc^byte)&255]!^(crc>>>8);return (crc^0xffffffff)>>>0}
function block(length:number){const bytes=new Uint8Array(length);return {bytes,view:new DataView(bytes.buffer)}}
async function compressed(data:Uint8Array<ArrayBuffer>){try{const stream=new Blob([data]).stream().pipeThrough(new CompressionStream('deflate-raw'));const bytes=new Uint8Array(await new Response(stream).arrayBuffer());if(bytes.length<data.length)return {bytes,method:8}}catch{}return {bytes:data,method:0}}
export async function usageArchive(data:UsageAnalytics){
 const documents=usageExportDocuments(data),encoder=new TextEncoder(),local:Uint8Array<ArrayBuffer>[]=[],central:Uint8Array<ArrayBuffer>[]=[],stamp=new Date()
 const time=(stamp.getHours()<<11)|(stamp.getMinutes()<<5)|(stamp.getSeconds()>>1),date=((stamp.getFullYear()-1980)<<9)|((stamp.getMonth()+1)<<5)|stamp.getDate()
 let offset=0
 for(const [name,text] of [['usage.md',documents.markdown],['usage.csv',documents.csv]]){
  const filename=encoder.encode(name),raw=encoder.encode(text),packed=await compressed(raw),crc=crc32(raw),header=block(30),directory=block(46)
  header.view.setUint32(0,0x04034b50,true);header.view.setUint16(4,20,true);header.view.setUint16(6,0x0800,true);header.view.setUint16(8,packed.method,true);header.view.setUint16(10,time,true);header.view.setUint16(12,date,true);header.view.setUint32(14,crc,true);header.view.setUint32(18,packed.bytes.length,true);header.view.setUint32(22,raw.length,true);header.view.setUint16(26,filename.length,true)
  directory.view.setUint32(0,0x02014b50,true);directory.view.setUint16(4,20,true);directory.view.setUint16(6,20,true);directory.view.setUint16(8,0x0800,true);directory.view.setUint16(10,packed.method,true);directory.view.setUint16(12,time,true);directory.view.setUint16(14,date,true);directory.view.setUint32(16,crc,true);directory.view.setUint32(20,packed.bytes.length,true);directory.view.setUint32(24,raw.length,true);directory.view.setUint16(28,filename.length,true);directory.view.setUint32(42,offset,true)
  local.push(header.bytes,filename,packed.bytes);central.push(directory.bytes,filename);offset+=header.bytes.length+filename.length+packed.bytes.length
 }
 const end=block(22),centralLength=central.reduce((sum,bytes)=>sum+bytes.length,0)
 end.view.setUint32(0,0x06054b50,true);end.view.setUint16(8,2,true);end.view.setUint16(10,2,true);end.view.setUint32(12,centralLength,true);end.view.setUint32(16,offset,true)
 const exportedAt=stamp.toISOString().replace(/[-:]/g,'').replace('T','-').replace('Z','')
 return {blob:new Blob([...local,...central,end.bytes],{type:'application/zip'}),filename:`SnapMind-${data.kind.toUpperCase()}-${data.range.start}_${data.range.end}-${exportedAt}.zip`}
}
export async function downloadUsage(data:UsageAnalytics){
 const archive=await usageArchive(data)
 if(isTauri()){
  const bytes=new Uint8Array(await archive.blob.arrayBuffer()),parts:string[]=[]
  for(let offset=0;offset<bytes.length;offset+=8192)parts.push(String.fromCharCode(...bytes.subarray(offset,offset+8192)))
  return await invoke<boolean>('save_usage_archive',{filename:archive.filename,base64Data:btoa(parts.join(''))})?'saved' as const:'cancelled' as const
 }
 const url=URL.createObjectURL(archive.blob),link=document.createElement('a')
 link.href=url;link.download=archive.filename;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),10000)
 return 'download-started' as const
}
