import {desktop,native} from './desktop'

// Restrict the transparent native editor to its visible image and controls.
// The rest of the desktop remains clickable, including other applications.
export function observePreviewRegions(id:string){
 if(!native)return ()=>{}
 let frame=0,disposed=false,busy=false,last=''
 const selector='.capture-screen,.capture-selection,.capture-toolbar,.capture-size,.capture-handle,.floating-editor-close,.capture-process-result,.capture-loupe,.capture-text-editor,.capture-mark-selection,.capture-scroll-preview,.capture-dropdown-menu,.tool-shortcut-popup,.snapmind-tooltip,.native-toast,.image-chat-lightbox,.voice-spirit'
 async function update(){
  frame=0;if(disposed||busy)return
  const regions=Array.from(document.querySelectorAll<HTMLElement>(selector)).filter(el=>getComputedStyle(el).visibility!=='hidden').map(el=>el.getBoundingClientRect()).filter(rect=>rect.width>0&&rect.height>0).map(rect=>({x:Math.max(0,rect.left-8),y:Math.max(0,rect.top-8),width:Math.min(innerWidth,rect.right+8)-Math.max(0,rect.left-8),height:Math.min(innerHeight,rect.bottom+8)-Math.max(0,rect.top-8)})).filter(rect=>rect.width>0&&rect.height>0)
  const signature=JSON.stringify(regions);if(!regions.length||signature===last)return
  busy=true
  try{await desktop.previewRegions(id,regions);last=signature}catch{/* A closing or replaced editor no longer owns the window. */}
  finally{busy=false;if(!disposed)schedule()}
 }
 function schedule(){if(!disposed&&!frame)frame=requestAnimationFrame(update)}
 const observer=new MutationObserver(schedule)
 observer.observe(document.body,{subtree:true,childList:true,attributes:true,attributeFilter:['style','class']})
 window.addEventListener('resize',schedule);schedule()
 return ()=>{disposed=true;observer.disconnect();cancelAnimationFrame(frame);window.removeEventListener('resize',schedule)}
}
