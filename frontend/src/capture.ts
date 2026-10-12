import { uid } from './sessions'
import type { Asset } from './types'

export interface CaptureResult {
  data: string; width: number; height: number
  action: 'copy'|'save'|'pin'|'explain'|'ocr'|'translate'|'formula'|'table'
  copied?: boolean
}
export async function grabScreen(): Promise<Asset> {
  if(!navigator.mediaDevices?.getDisplayMedia) throw new Error('当前浏览器不支持截屏，请使用 Chrome / Edge，或导入图片。')
  const stream=await navigator.mediaDevices.getDisplayMedia({video:{frameRate:1},audio:false})
  try {
    const video=document.createElement('video');video.srcObject=stream;video.muted=true
    await video.play()
    await new Promise<void>(resolve=>requestAnimationFrame(()=>requestAnimationFrame(()=>resolve())))
    if(!video.videoWidth) throw new Error('没有获取到屏幕画面，请重试。')
    const ratio=Math.min(1,3000/video.videoWidth,2000/video.videoHeight)
    const c=document.createElement('canvas');c.width=Math.round(video.videoWidth*ratio);c.height=Math.round(video.videoHeight*ratio)
    c.getContext('2d')!.drawImage(video,0,0,c.width,c.height)
    return {id:uid(),name:'屏幕截图',data:c.toDataURL('image/png'),width:c.width,height:c.height,scenario:'custom'}
  }finally{stream.getTracks().forEach(t=>t.stop())}
}

export async function readCaptureFile(file:File):Promise<Asset> {
  if(!['image/png','image/jpeg','image/webp'].includes(file.type)) throw new Error('请选择 PNG、JPG 或 WebP 图片。')
  if(file.size>8*1024*1024) throw new Error('图片不能超过 8 MB。')
  const data=await new Promise<string>((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result as string);r.onerror=reject;r.readAsDataURL(file)})
  const img=new Image();img.src=data;await img.decode()
  if(img.width>20000||img.height>20000) throw new Error('图片尺寸过大，请缩小后再导入。')
  return {id:uid(),name:file.name.replace(/\.[^.]+$/,''),data,width:img.width,height:img.height,scenario:'custom'}
}
