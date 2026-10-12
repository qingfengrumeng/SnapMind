import {isTauri,invoke} from '@tauri-apps/api/core'
import {getCurrentWindow,LogicalSize} from '@tauri-apps/api/window'
import {listen,type UnlistenFn} from '@tauri-apps/api/event'
import type {Asset} from './types'
import type {CaptureResult} from './capture'
import type {ToolAction} from './tool-actions'
import type {LiveScrollKey} from './tool-shortcuts'
export const native=isTauri()
export const desktopRole=native?(new URLSearchParams(location.search).get('desktop')||'main'):'browser'
export interface DesktopFrame{asset:Asset;x:number;y:number;scaleFactor:number;floatingPreview?:boolean}
export interface DesktopRuntime{frame?:DesktopFrame;asset?:Asset;sessionId?:string;captureActive:boolean;shortcutAvailable:boolean;captureShortcut:string}
async function pngAsset(asset:Asset):Promise<Asset>{if(asset.data.startsWith('data:image/png;'))return asset;const img=new Image();img.src=asset.data;await img.decode();const c=document.createElement('canvas');c.width=asset.width;c.height=asset.height;c.getContext('2d')!.drawImage(img,0,0);return {...asset,data:c.toDataURL('image/png')}}
export const desktop={
 copyImage:async(asset:Asset)=>invoke<void>('copy_image_asset',{asset:await pngAsset(asset)}),
 copyTable:(text:string,html:string)=>invoke<void>('copy_table_content',{text,html}),
 openEntity:(url:string)=>invoke<void>('open_image_entity',{url}),
 transformPin:async(asset:Asset)=>invoke<void>('transform_pinned_image',{asset:await pngAsset(asset)}),
 controls:(id:string,rect:{x:number;y:number;w:number;h:number})=>invoke<import('./api').ControlTarget[]>('capture_control_targets',{id,x:rect.x,y:rect.y,width:rect.w,height:rect.h}),
 copyText:(text:string)=>invoke<void>('copy_capture_text',{text}),
 scrollFrame:(rect:{x:number;y:number;w:number;h:number})=>invoke<string>('capture_scroll_step',{x:rect.x,y:rect.y,width:rect.w,height:rect.h}),
 liveScroll:(active:boolean,buttons:{x:number;y:number;width:number;height:number}[]=[],keys:LiveScrollKey[]=[])=>invoke<void>('set_live_scroll',{active,buttons,keys}),
 state:()=>invoke<DesktopRuntime>('get_desktop_state'),
 capture:()=>invoke<void>('begin_capture'),
 captureReady:(id:string)=>invoke<void>('show_capture_when_ready',{id}),
 contentReady:(id:string)=>invoke<void>('capture_content_ready',{id}),
 preview:async(asset:Asset,floatingPreview=false)=>invoke<void>('begin_preview_capture',{asset:await pngAsset(asset),floatingPreview}),
 previewRegions:(id:string,regions:{x:number;y:number;width:number;height:number}[])=>invoke<void>('set_preview_regions',{id,regions}),
 edit:()=>invoke<void>('edit_desktop_image'),
 cancel:()=>{const image=document.querySelector('.floating-preview-editor .capture-screen')?.getBoundingClientRect();return invoke<void>('cancel_capture',{previewBounds:image?{x:image.x,y:image.y,width:image.width,height:image.height}:null})},
 finish:(result:CaptureResult)=>invoke<void>('finish_capture',{result}),
 session:async(sessionId:string,asset:Asset|undefined,action?:string,notifyWorkspace=true)=>invoke<void>('set_desktop_session',{sessionId,asset:asset?await pngAsset(asset):null,action:action||null,notifyWorkspace}),
 launcher:()=>invoke<void>('show_launcher'),
 toolAction:(action:ToolAction)=>invoke<void>('desktop_tool_action',{action}),
 setShortcut:(shortcut:string)=>invoke<void>('set_capture_shortcut',{shortcut}),
 shortcutRecording:(recording:boolean)=>invoke<void>('set_shortcut_recording',{recording}),
 onFocus:(handler:(focused:boolean)=>void)=>getCurrentWindow().onFocusChanged(e=>handler(e.payload)),
 copy:()=>invoke<void>('desktop_copy'),
 save:()=>invoke<boolean>('desktop_save'),
 hide:()=>invoke<void>('hide_desktop_window'),
 minimize:()=>getCurrentWindow().minimize(),
 drag:()=>getCurrentWindow().startDragging(),
 resize:(direction:'North'|'South'|'East'|'West'|'NorthWest'|'NorthEast'|'SouthWest'|'SouthEast')=>getCurrentWindow().startResizeDragging(direction),
 size:(width:number,height:number)=>getCurrentWindow().setSize(new LogicalSize(width,height)),
 zoomImage:(factor:number)=>invoke<void>('zoom_desktop_image',{factor}),
 listen:<T>(event:string,handler:(payload:T)=>void|Promise<void>):Promise<UnlistenFn>=>listen<T>(event,e=>handler(e.payload))
}
if(native){document.documentElement.dataset.desktop=desktopRole}
