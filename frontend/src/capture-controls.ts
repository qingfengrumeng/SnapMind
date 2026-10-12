import {native,desktop} from './desktop'
import type {ControlTarget} from './api'
type Rect={x:number;y:number;w:number;h:number}
type Reader=(id:string,rect:Rect)=>Promise<ControlTarget[]>
export async function captureControls(id:string,bounds:Rect,modified:Rect[],read:Reader|undefined=native?desktop.controls:undefined):Promise<ControlTarget[]>{
 if(!read)return []
 const rect={x:Math.floor(bounds.x),y:Math.floor(bounds.y),w:Math.floor(bounds.w),h:Math.floor(bounds.h)}
 try{
  const controls=await read(id,rect),dx=rect.x-bounds.x,dy=rect.y-bounds.y
  return controls.slice(0,300).map(c=>({...c,bbox:c.bbox.map((v,i)=>v+(i%2===0?dx:dy)) as ControlTarget['bbox']})).filter(c=>{
   const [l,t,r,b]=c.bbox;if(!c.bbox.every(Number.isFinite)||l<0||t<0||r>rect.w||b>rect.h||r<=l||b<=t)return false
   // Drawn text, translation and redactions are not part of the live UI.
   return !modified.some(m=>Math.max(l+bounds.x,m.x)<Math.min(r+bounds.x,m.x+m.w)&&Math.max(t+bounds.y,m.y)<Math.min(b+bounds.y,m.y+m.h))
  })
 }catch{return []}
}
