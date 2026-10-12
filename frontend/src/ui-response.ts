// Let Vue's pending updates paint before CPU work; do not add a fixed delay.
export function afterPaint():Promise<void>{if(document.hidden)return Promise.resolve();return new Promise(resolve=>{requestAnimationFrame(()=>setTimeout(resolve,0))})}

// Browser PNG encoding runs asynchronously, keeping input and animations responsive.
export async function canvasPng(canvas:HTMLCanvasElement):Promise<string>{
 const blob=await new Promise<Blob>((resolve,reject)=>canvas.toBlob(value=>value?resolve(value):reject(new Error('图片编码失败，请重试')),'image/png'))
 return new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result));reader.onerror=()=>reject(new Error('图片读取失败，请重试'));reader.readAsDataURL(blob)})
}
