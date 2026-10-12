// Match the previous frame's bottom to the next frame's top. Never append an
// unmatched frame: fixed headers or a changed page should be reported to users.
export function scrollOffset(previous:ImageData,next:ImageData):number|null{
 const {width:w,height:h,data:a}=previous,b=next.data
 if(w!==next.width||h!==next.height)return null
 function error(offset:number){let total=0,count=0;const overlap=h-Math.abs(offset),ay=Math.max(0,offset),by=Math.max(0,-offset);for(let y=0;y<overlap;y+=Math.max(1,Math.floor(overlap/32)))for(let x=4;x<w-4;x+=Math.max(1,Math.floor(w/32))){const i=((y+ay)*w+x)*4,j=((y+by)*w+x)*4;for(let c=0;c<3;c++){total+=Math.abs(a[i+c]!-b[j+c]!);count++}}return count?total/count:255}
 if(error(0)<.8)return 0
 let best=255,shift=0;for(let offset=-(h-Math.max(24,Math.floor(h*.12)));offset<=h-Math.max(24,Math.floor(h*.12));offset++){const e=error(offset);if(e<best){best=e;shift=offset}}
 return best<5?shift:null
}
