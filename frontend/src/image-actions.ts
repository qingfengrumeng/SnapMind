import type {Asset} from './types'
import type {ExtractedTable,ImageConversationResult,AiExisting,InlineTranslationResult,ObjectDetection,AiAnnotationResult} from './api'
import {paintTranslation} from './inline-translation'
import {paintObject,tableTsv} from './capture-analysis'
import {paintAi,type AiPaint} from './ai-callouts'
import {desktop,native} from './desktop'
import {canvasPng} from './ui-response'

export async function assetCanvas(asset:Asset){const image=new Image();if(/^https?:/.test(asset.data))image.crossOrigin='anonymous';image.src=asset.data;await image.decode();const canvas=document.createElement('canvas');canvas.width=asset.width;canvas.height=asset.height;canvas.getContext('2d')!.drawImage(image,0,0);return canvas}
export function canvasAsset(canvas:HTMLCanvasElement,source:Asset):Asset{return {...source,data:canvas.toDataURL('image/png'),width:canvas.width,height:canvas.height}}
export async function copyImage(asset:Asset){if(native){await desktop.copyImage(asset);return}const c=await assetCanvas(asset),blob=await new Promise<Blob|null>(r=>c.toBlob(r));if(!blob)throw new Error('无法复制图片');await navigator.clipboard.write([new ClipboardItem({'image/png':blob})])}
export function saveImage(asset:Asset){const a=document.createElement('a');a.href=asset.data;a.download=(asset.name||'SnapMind')+'.png';a.click()}
const escaped=(s:string)=>s.replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!))
export function imageNoteDocument(markdown:string,assets:Asset[]){
 return '<!doctype html><html lang="zh-CN"><meta charset="utf-8"><title>图片笔记</title><style>body{max-width:1000px;margin:32px auto;padding:0 24px;color:#352c45;background:#faf8ff;font:16px/1.7 "Segoe UI","Microsoft YaHei",sans-serif}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}img{max-width:100%;height:auto}figure{margin:24px 0}</style><body><pre>'+escaped(markdown)+'</pre>'+assets.map((a,i)=>'<figure><figcaption>图片 '+(i+1)+'</figcaption><img src="'+escaped(a.data)+'" alt="'+escaped(a.name)+'"></figure>').join('')+'</body></html>'
}
export function saveImageNote(markdown:string,assets:Asset[]){
 const url=URL.createObjectURL(new Blob([imageNoteDocument(markdown,assets)],{type:'text/html;charset=utf-8'})),a=document.createElement('a');a.href=url;a.download='SnapMind-图片笔记.html';a.click();setTimeout(()=>URL.revokeObjectURL(url),10000)
}
const literalCell=(s:string)=>/^[\s]*[=+@-]/.test(s)&&!/^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\s*$/.test(s)?"'"+s:s
export function tableText(table:ExtractedTable,format:'tsv'|'csv'|'markdown'='tsv'){
 const rows=table.rows
 if(format==='csv')return rows.map(r=>r.map(c=>'"'+literalCell(c).replace(/"/g,'""')+'"').join(',')).join('\r\n')
 if(format==='markdown')return rows.map((r,i)=>'| '+r.map(c=>c.replace(/\|/g,'\\|').replace(/\r?\n/g,'<br>')).join(' | ')+' |'+(i===0?'\n| '+r.map(()=>'---').join(' | ')+' |':'')).join('\n')
 return tableTsv(table)
}
export async function copyTable(table:ExtractedTable,format:'excel'|'csv'|'markdown'='excel'){
 const text=tableText(table,format==='excel'?'tsv':format)
 if(format!=='excel'){if(native)await desktop.copyText(text);else await navigator.clipboard.writeText(text);return}
 const html='<html><body><table>'+table.rows.map(row=>'<tr>'+row.map(cell=>'<td style="mso-number-format:\\@">'+escaped(cell).replace(/\r?\n/g,'<br>')+'</td>').join('')+'</tr>').join('')+'</table></body></html>'
 if(native)await desktop.copyTable(text,html)
 else await navigator.clipboard.write([new ClipboardItem({'text/plain':new Blob([text],{type:'text/plain'}),'text/html':new Blob([html],{type:'text/html'})})])
}

export function annotationEdits(existing:AiExisting[],result:AiAnnotationResult){
 let next=existing.map(a=>({...a}));let id=Math.max(0,...next.map(a=>Number(a.id.slice(3))))
 for(const edit of result.annotations){const index=edit.operation==='add'?-1:next.findIndex(a=>a.id===edit.id);if(edit.operation!=='add'&&index<0)throw new Error('标注编号失效，请重新生成');if(edit.operation==='remove'){next.splice(index,1);continue}const item:AiExisting={...edit,id:edit.operation==='add'?'ai-'+(++id):edit.id!,locationSource:edit.locationSource==='existing'&&index>=0?next[index]?.locationSource:edit.locationSource};if(index<0)next.push(item);else next[index]=item}
 return next
}
export async function renderAnnotations(asset:Asset,annotations:AiExisting[]){const canvas=await assetCanvas(asset),g=canvas.getContext('2d')!,occupied:NonNullable<AiPaint['bubble']>[]=[];for(const a of annotations){const layer=paintAi({...a,edgeAnchor:['ocr','uia'].includes(a.locationSource||'')},{x:0,y:0,w:asset.width,h:asset.height},1,occupied);if(layer.ai?.bubble)occupied.push(layer.ai.bubble);g.drawImage(layer.image,layer.x,layer.y)}return {...asset,data:await canvasPng(canvas),width:canvas.width,height:canvas.height}}
export async function applyImageResult(asset:Asset,result:ImageConversationResult):Promise<Asset|undefined>{
 const payload=result.payload
 if(result.assetId!==asset.id)return
 if(['crop','heal','lift','blur','restore_image'].includes(result.action))return {...asset,...payload as {data:string;width:number;height:number}}
 const canvas=await assetCanvas(asset),g=canvas.getContext('2d')!
 if(result.action==='translate'){const painted=paintTranslation(canvas,payload as InlineTranslationResult);g.drawImage(painted.layer,0,0)}
 else if(result.action==='detect'){for(const [i,object] of (payload as ObjectDetection).objects.entries()){const layer=paintObject(object,asset.width,asset.height,1,i);g.drawImage(layer.image,layer.x,layer.y)}}
 else if(['highlight','mosaic'].includes(result.action)){const [l,t,r,b]=(payload as {bbox:number[]}).bbox;if(result.action==='highlight'){g.fillStyle='rgba(255,211,60,.4)';g.fillRect(l,t,r-l,b-t)}else{const small=document.createElement('canvas');small.width=Math.max(1,Math.ceil((r-l)/12));small.height=Math.max(1,Math.ceil((b-t)/12));small.getContext('2d')!.drawImage(canvas,l,t,r-l,b-t,0,0,small.width,small.height);g.imageSmoothingEnabled=false;g.drawImage(small,l,t,r-l,b-t)}}
 else return
 return {...asset,data:await canvasPng(canvas),width:canvas.width,height:canvas.height}
}
