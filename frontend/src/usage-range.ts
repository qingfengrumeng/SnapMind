export type UsagePreset='today'|'yesterday'|'week'|'month30'|'month'|'lastMonth'|'custom'
export interface UsageRange{preset:UsagePreset;start:string;end:string}
export function beijingToday(){return new Date(Date.now()+8*60*60*1000).toISOString().slice(0,10)}
function shift(day:string,offset:number){const date=new Date(day+'T00:00:00Z');date.setUTCDate(date.getUTCDate()+offset);return date.toISOString().slice(0,10)}
export function presetRange(preset:Exclude<UsagePreset,'custom'>,today=beijingToday()):UsageRange{
 let start=today,end=today
 if(preset==='yesterday')start=end=shift(today,-1)
 if(preset==='week')start=shift(today,-6)
 if(preset==='month30')start=shift(today,-29)
 if(preset==='month')start=today.slice(0,8)+'01'
 if(preset==='lastMonth'){end=shift(today.slice(0,8)+'01',-1);start=end.slice(0,8)+'01'}
 return {preset,start,end}
}
export function validUsageRange(start:string,end:string){
 const first=new Date(start+'T00:00:00Z'),last=new Date(end+'T00:00:00Z')
 return /^\d{4}-\d{2}-\d{2}$/.test(start)&&/^\d{4}-\d{2}-\d{2}$/.test(end)&&Number.isFinite(+first)&&Number.isFinite(+last)&&first.getUTCFullYear()>=1900&&last.getUTCFullYear()<=9998&&first.toISOString().slice(0,10)===start&&last.toISOString().slice(0,10)===end&&+last>=+first&&(+last-+first)/86400000<=365
}
