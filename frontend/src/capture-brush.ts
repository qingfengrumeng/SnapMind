export type BrushShape='circle'|'square'
type Point={x:number;y:number}

// Fill the swept brush footprint opaquely, so passing over the same pixels in
// one stroke does not increase the highlight's opacity.
export function paintBrush(g:CanvasRenderingContext2D,from:Point,to:Point,size:number,shape:BrushShape,color:string){
 const radius=size/2;g.save();g.fillStyle=color;g.strokeStyle=color
 if(shape==='circle'){
  g.lineWidth=size;g.lineCap='round';g.beginPath();g.moveTo(from.x,from.y);g.lineTo(to.x,to.y);g.stroke()
  g.beginPath();g.arc(to.x,to.y,radius,0,Math.PI*2);g.fill()
 }else{
  // The convex hull of the two squares covers fast and diagonal movement
  // continuously, while keeping a square footprint at both ends.
  const points=[from,to].flatMap(p=>[-radius,radius].flatMap(x=>[-radius,radius].map(y=>({x:p.x+x,y:p.y+y})))).sort((a,b)=>a.x-b.x||a.y-b.y)
  const cross=(a:Point,b:Point,c:Point)=>(b.x-a.x)*(c.y-a.y)-(b.y-a.y)*(c.x-a.x)
  const half=(items:Point[])=>{const result:Point[]=[];for(const p of items){while(result.length>1&&cross(result[result.length-2]!,result.at(-1)!,p)<=0)result.pop();result.push(p)}return result.slice(0,-1)}
  const hull=[...half(points),...half([...points].reverse())];g.beginPath();hull.forEach((p,i)=>i?g.lineTo(p.x,p.y):g.moveTo(p.x,p.y));g.closePath();g.fill()
 }
 g.restore()
}
