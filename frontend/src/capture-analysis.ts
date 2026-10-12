import type { DetectedObject, ExtractedTable } from './api'

// TSV is understood by Excel's clipboard importer, including quoted multiline cells.
// Keep formula-looking source text literal when pasting into spreadsheets.
export function tableTsv(table:ExtractedTable){
 return table.rows.map(row=>row.map(cell=>{
  let value=cell
  if(/^[\s]*[=+@-]/.test(value)&&!/^\s*[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?\s*$/.test(value))value="'"+value
  return /[\t\r\n"]/.test(value)?'"'+value.replaceAll('"','""')+'"':value
 }).join('\t')).join('\r\n')
}

export function paintObject(object:DetectedObject,sourceWidth:number,sourceHeight:number,scale:number,index:number){
 const [x1,y1,x2,y2]=object.bbox
 if(!object.label.trim()||![x1,y1,x2,y2].every(Number.isFinite)||x1<0||y1<0||x2>sourceWidth||y2>sourceHeight||x2<=x1||y2<=y1)throw new Error('物体位置超出截图范围，请重新识别')
 const padding=Math.ceil(3/scale),x=Math.max(0,Math.floor(x1)-padding),y=Math.max(0,Math.floor(y1)-padding)
 const w=Math.min(sourceWidth-x,Math.ceil(x2)-x+padding),h=Math.min(sourceHeight-y,Math.ceil(y2)-y+padding)
 const image=document.createElement('canvas');image.width=w;image.height=h
 const g=image.getContext('2d')!,stroke=Math.max(1,2/scale)
 g.beginPath();g.ellipse((x1+x2)/2-x,(y1+y2)/2-y,Math.max(.5,(x2-x1)/2),Math.max(.5,(y2-y1)/2),0,0,Math.PI*2)
 g.strokeStyle='#f8faff';g.lineWidth=stroke+1/scale;g.stroke();g.strokeStyle='#2d7df2';g.lineWidth=stroke;g.stroke()
 const size=Math.min(13/scale,Math.max(8,h*.22)),label=`${index+1} ${object.label}`
 g.font=`${size}px "Segoe UI","Microsoft YaHei",sans-serif`;g.textBaseline='top'
 const labelWidth=Math.min(w,g.measureText(label).width+8/scale),labelHeight=Math.min(h,size+5/scale)
 g.fillStyle='#f8faff';g.fillRect(0,0,labelWidth,labelHeight);g.fillStyle='#2265c6';g.fillText(label,3/scale,2/scale,Math.max(1,labelWidth-6/scale))
 return {image,x,y,w,h}
}
