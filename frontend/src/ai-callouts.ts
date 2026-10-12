import type {AiAnnotation} from './api'
export type Bounds={x:number;y:number;w:number;h:number}
export type AiPaint=AiAnnotation&{bubble?:Bounds;edgeAnchor?:boolean;anchor?:{x:number;y:number}}
export function aiAnchor(spec:AiPaint){return spec.anchor||{x:(spec.bbox[0]+spec.bbox[2])/2,y:(spec.bbox[1]+spec.bbox[3])/2}}

function overlap(a:Bounds,b:Bounds){return Math.max(0,Math.min(a.x+a.w,b.x+b.w)-Math.max(a.x,b.x))*Math.max(0,Math.min(a.y+a.h,b.y+b.h)-Math.max(a.y,b.y))}
function clampBox(r:Bounds,b:Bounds){return {...r,x:Math.max(b.x,Math.min(r.x,b.x+b.w-r.w)),y:Math.max(b.y,Math.min(r.y,b.y+b.h-r.h))}}
export function moveBubble(spec:AiPaint,dx:number,dy:number,bounds:Bounds):AiPaint{
 if(!spec.bubble)return spec
 return {...spec,bubble:clampBox({...spec.bubble,x:spec.bubble.x+dx,y:spec.bubble.y+dy},bounds)}
}

export function paintAi(spec:AiPaint,bounds:Bounds,scale:number,occupied:Bounds[]=[]){
 const [l,t,r,b]=spec.bbox
 if(![l,t,r,b].every(Number.isFinite)||l<bounds.x||t<bounds.y||r>bounds.x+bounds.w||b>bounds.y+bounds.h||r<=l||b<=t)throw new Error('AI 标注位置超出截图，请重试')
 const layer=document.createElement('canvas');layer.width=1;layer.height=1
 const g=layer.getContext('2d')!;let origin={x:bounds.x,y:bounds.y}
 const unit=1/Math.max(.1,scale),target={x:l,y:t,w:r-l,h:b-t},cx=(l+r)/2,cy=(t+b)/2
 let updated:AiPaint={...spec}
 function area(rect:Bounds){const left=Math.max(bounds.x,Math.floor(rect.x)),top=Math.max(bounds.y,Math.floor(rect.y)),right=Math.min(bounds.x+bounds.w,Math.ceil(rect.x+rect.w)),bottom=Math.min(bounds.y+bounds.h,Math.ceil(rect.y+rect.h));origin={x:left,y:top};layer.width=Math.max(1,right-left);layer.height=Math.max(1,bottom-top);g.translate(-left,-top)}
 if(spec.kind==='callout'){
  const text=spec.text.replace(/\s+/g,' ').trim().slice(0,40);if(!text)throw new Error('注释内容为空')
  const size=Math.max(8,Math.min(16*unit,bounds.h/5)),pad=10*unit,maxText=Math.max(size,Math.min(180*unit,bounds.w-pad*2))
  g.font=`${size}px "Segoe UI","Microsoft YaHei UI","Microsoft YaHei",sans-serif`
  const lines:string[]=[];let line=''
  for(const char of text){if(line&&g.measureText(line+char).width>maxText){lines.push(line);line=''}line+=char}if(line)lines.push(line)
  const width=Math.min(bounds.w,Math.max(65*unit,...lines.map(s=>g.measureText(s).width+pad*2))),height=Math.min(bounds.h,lines.length*size*1.45+pad*2),gap=16*unit
  const candidates=[{x:r+gap,y:cy-height/2,w:width,h:height},{x:l-gap-width,y:cy-height/2,w:width,h:height},{x:cx-width/2,y:t-gap-height,w:width,h:height},{x:cx-width/2,y:b+gap,w:width,h:height}].map(c=>clampBox(c,bounds))
  const score=(c:Bounds)=>overlap(c,target)*2+occupied.reduce((n,o)=>n+overlap(c,o)*4,0)
  const bubble=spec.bubble?clampBox({...spec.bubble,w:width,h:height},bounds):candidates.reduce((a,c)=>score(c)<score(a)?c:a)
  const endX=Math.max(bubble.x,Math.min(cx,bubble.x+bubble.w)),endY=Math.max(bubble.y,Math.min(cy,bubble.y+bubble.h))
  const anchor=spec.anchor||(spec.edgeAnchor?{
   x:Math.max(bounds.x+3*unit,Math.min(bounds.x+bounds.w-3*unit,endX>r?r+4*unit:endX<l?l-4*unit:Math.max(l,Math.min(r,endX)))),
   y:Math.max(bounds.y+3*unit,Math.min(bounds.y+bounds.h-3*unit,endY>b?b+4*unit:endY<t?t-4*unit:Math.max(t,Math.min(b,endY))))
  }:{x:cx,y:cy})
  updated={...spec,text,bubble,anchor:spec.edgeAnchor?anchor:spec.anchor}
  const margin=4*unit
  area({x:Math.min(anchor.x,bubble.x)-margin,y:Math.min(anchor.y,bubble.y)-margin,w:Math.max(anchor.x,bubble.x+bubble.w)-Math.min(anchor.x,bubble.x)+margin*2,h:Math.max(anchor.y,bubble.y+bubble.h)-Math.min(anchor.y,bubble.y)+margin*2})
  g.font=`${size}px "Segoe UI","Microsoft YaHei UI","Microsoft YaHei",sans-serif`
  g.strokeStyle='#9255df';g.lineWidth=1.7*unit;g.beginPath();g.moveTo(anchor.x,anchor.y);g.lineTo(endX,endY);g.stroke()
  g.fillStyle='#9255df';g.beginPath();g.arc(anchor.x,anchor.y,3*unit,0,Math.PI*2);g.fill()
  g.fillStyle='#fcf8ff';g.strokeStyle='#ba95ee';g.lineWidth=unit;g.beginPath();g.roundRect(bubble.x,bubble.y,bubble.w,bubble.h,Math.min(11*unit,bubble.h/3));g.fill();g.stroke()
  g.fillStyle='#603887';g.textBaseline='top';lines.forEach((s,i)=>g.fillText(s,bubble.x+pad,bubble.y+pad+i*size*1.45,Math.max(1,width-pad*2)))
 }else if(['rectangle','arrow','highlight','text','number'].includes(spec.kind)){
  const pad=5*unit;area({x:l-pad,y:t-pad,w:r-l+pad*2,h:b-t+pad*2});g.lineWidth=2*unit;g.strokeStyle='#8b45ed';g.fillStyle='#8b45ed';g.lineCap='round';g.lineJoin='round'
  if(spec.kind==='rectangle'){g.strokeRect(l,t,r-l,b-t)}
  else if(spec.kind==='highlight'){g.fillStyle='rgba(255,212,55,.38)';g.fillRect(l,t,r-l,b-t)}
  else if(spec.kind==='arrow'){const endX=r-3*unit,endY=cy,startX=l+3*unit,len=Math.min(14*unit,target.w*.25);g.beginPath();g.moveTo(startX,endY);g.lineTo(endX,endY);g.lineTo(endX-len,endY-len*.55);g.moveTo(endX,endY);g.lineTo(endX-len,endY+len*.55);g.stroke()}
  else if(spec.kind==='number'){const radius=Math.min(12*unit,target.w/2,target.h/2);g.beginPath();g.arc(cx,cy,radius,0,Math.PI*2);g.fill();g.fillStyle='#fff';g.font=`${Math.max(6,radius*1.2)}px "Segoe UI",sans-serif`;g.textAlign='center';g.textBaseline='middle';g.fillText(spec.text||'1',cx,cy)}
  else{g.font=`${Math.max(8,Math.min(20*unit,target.h*.8))}px "Segoe UI","Microsoft YaHei",sans-serif`;g.textBaseline='middle';g.fillText(spec.text.slice(0,40),l,cy,target.w)}
 }else{
  const size=Math.max(10*unit,Math.min(35*unit,target.w*.55,target.h*.55)),line=Math.max(2*unit,size*.13)
  // An ellipse through a long, shallow text box crosses the first/last letters.
  // Text uses an outside frame so the annotation never strikes through the ink.
  const textFrame=['ocr','uia'].includes(spec.locationSource||''),pad=textFrame?6*unit:0
  const frame={x:l-pad,y:t-pad,w:r-l+pad*2,h:b-t+pad*2}
  const margin=4*unit
  area(spec.kind==='circle'?{x:frame.x-margin,y:frame.y-margin,w:frame.w+margin*2,h:frame.h+margin*2}:{x:cx-size-margin,y:cy-size-margin,w:size*2+margin*2,h:size*2+margin*2})
  g.lineCap='round';g.lineJoin='round';g.beginPath()
  if(spec.kind==='circle'){if(textFrame)g.roundRect(frame.x,frame.y,frame.w,frame.h,Math.min(6*unit,frame.h/2));else g.ellipse(cx,cy,target.w/2,target.h/2,0,0,Math.PI*2);g.strokeStyle='#fcf8ff';g.lineWidth=3.5*unit;g.stroke();g.strokeStyle='#8b45ed';g.lineWidth=2*unit;g.stroke()}
  else{
   if(spec.kind==='check'){g.moveTo(cx-size*.48,cy);g.lineTo(cx-size*.12,cy+size*.35);g.lineTo(cx+size*.5,cy-size*.42)}
   else{g.moveTo(cx-size*.4,cy-size*.4);g.lineTo(cx+size*.4,cy+size*.4);g.moveTo(cx+size*.4,cy-size*.4);g.lineTo(cx-size*.4,cy+size*.4)}
   g.strokeStyle='#ffffff';g.lineWidth=line+2*unit;g.stroke();g.strokeStyle=spec.kind==='check'?'#20b779':'#f05263';g.lineWidth=line;g.stroke()
  }
 }
 // Tight immutable image layers make independent hit-testing and undo practical.
 const pixels=g.getImageData(0,0,layer.width,layer.height).data;let left=layer.width,top=layer.height,right=-1,bottom=-1
 for(let y=0;y<layer.height;y++)for(let x=0;x<layer.width;x++)if(pixels[(y*layer.width+x)*4+3]){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y)}
 if(right<left)throw new Error('截图太小，无法添加标注')
 const image=document.createElement('canvas');image.width=right-left+1;image.height=bottom-top+1;image.getContext('2d')!.drawImage(layer,left,top,image.width,image.height,0,0,image.width,image.height)
 return {image,x:origin.x+left,y:origin.y+top,w:image.width,h:image.height,ai:updated}
}
