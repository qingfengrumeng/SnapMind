import type {InlineTranslationResult} from './api'
export interface PaintedTranslationLine{ id:string;text:string;sourceText:string;x:number;y:number;width:number;height:number;fontSize:number;color:string }
export const translationFont='"Segoe UI", "Microsoft YaHei UI", "Microsoft YaHei", sans-serif'
function luminance(c:number[]){return c[0]!*0.299+c[1]!*0.587+c[2]!*0.114}
function rgb(c:number[]){return `rgb(${c.map(v=>Math.round(v)).join(',')})`}
function dominant(samples:number[][]){const bins=new Map<string,number[][]>();for(const sample of samples){const key=sample.map(v=>Math.floor(v/16)).join(',');const bin=bins.get(key)||[];bin.push(sample);bins.set(key,bin)}const group=[...bins.values()].sort((a,b)=>b.length-a.length)[0]||[[250,250,250]];return [0,1,2].map(i=>group.reduce((sum,p)=>sum+p[i]!,0)/group.length)}
export function paintTranslation(source:HTMLCanvasElement,result:InlineTranslationResult){
 const layer=document.createElement('canvas');layer.width=source.width;layer.height=source.height
 const g=layer.getContext('2d')!,pixels=source.getContext('2d')!.getImageData(0,0,source.width,source.height),lines:PaintedTranslationLine[]=[]
 const pixel=(x:number,y:number)=>{const index=(Math.max(0,Math.min(source.height-1,y))*source.width+Math.max(0,Math.min(source.width-1,x)))*4;return [...pixels.data.slice(index,index+3)]}
 for(const line of result.lines){
  const [left,top,right,bottom]=line.bbox
  const x=Math.max(0,Math.floor(left!)-1),y=Math.max(0,Math.floor(top!)-1),r=Math.min(source.width,Math.ceil(right!)+1),b=Math.min(source.height,Math.ceil(bottom!)+1),width=r-x,height=b-y
  if(width<1||height<1)continue
  const border:number[][]=[];for(let px=x;px<r;px+=Math.max(1,Math.floor(width/100))){border.push(pixel(px,y-2),pixel(px,b+1))}for(let py=y;py<b;py+=2)border.push(pixel(x-2,py),pixel(r+1,py))
  const background=dominant(border),ink:number[][]=[]
  for(let py=y;py<b;py+=1)for(let px=x;px<r;px+=Math.max(1,Math.floor(width/200))){const p=pixel(px,py);if(Math.max(...p.map((v,i)=>Math.abs(v-background[i]!)))>70)ink.push(p)}
  const foreground=ink.length?dominant(ink):luminance(background)>140?[35,30,43]:[249,247,252]
  g.fillStyle=rgb(background);g.fillRect(x,y,width,height)
  const originalSize=Math.max(4,height-2);g.font=`${originalSize}px ${translationFont}`
  const text=line.text.replace(/\r?\n/g,' '),fontSize=Math.min(originalSize,originalSize*(width-2)/Math.max(1,g.measureText(text).width))
  g.font=`${Math.max(1,fontSize)}px ${translationFont}`;g.textBaseline='top';g.fillStyle=rgb(foreground)
  const textY=y+(height-fontSize)/2;g.fillText(text,x+1,textY)
  lines.push({id:line.id,text,sourceText:line.sourceText,x:x+1,y:textY,width:Math.max(1,width-2),height:Math.max(1,fontSize),fontSize:Math.max(1,fontSize),color:rgb(foreground)})
 }
 return {layer,lines}
}
export function translationRows(lines:PaintedTranslationLine[]){
 const rows:PaintedTranslationLine[][]=[]
 for(const line of [...lines].sort((a,b)=>a.y-b.y||a.x-b.x)){
  const row=rows.find(r=>Math.abs((r[0]!.y+r[0]!.height/2)-(line.y+line.height/2))<=Math.min(r[0]!.height,line.height)*.5)
  if(row)row.push(line);else rows.push([line])
 }
 return rows.map(row=>row.sort((a,b)=>a.x-b.x))
}
export function translationPlainText(lines:PaintedTranslationLine[]){return translationRows(lines).map(row=>row.map(l=>l.text).join('\t')).join('\n')}
