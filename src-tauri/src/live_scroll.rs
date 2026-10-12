//! During live capture, native wheel input reaches the original application.
//! Hooks consume only capture controls; the hook thread never captures images.
use serde::Deserialize;
#[derive(Clone,Deserialize)]
pub struct Bounds {pub x:i32,pub y:i32,pub width:i32,pub height:i32}
#[derive(Clone,Deserialize)]
#[serde(rename_all="camelCase")]
pub struct KeyBinding {pub key_code:u32,pub ctrl:bool,pub alt:bool,pub shift:bool,pub meta:bool,pub action:usize}
impl KeyBinding {fn matches(&self,key:u32,ctrl:bool,alt:bool,shift:bool,meta:bool)->bool{self.key_code==key&&self.ctrl==ctrl&&self.alt==alt&&self.shift==shift&&self.meta==meta}}
pub fn default_keys()->Vec<KeyBinding>{vec![KeyBinding{key_code:27,ctrl:false,alt:false,shift:false,meta:false,action:2},KeyBinding{key_code:13,ctrl:false,alt:false,shift:false,meta:false,action:3},KeyBinding{key_code:83,ctrl:true,alt:false,shift:false,meta:false,action:1}]}
#[cfg(windows)]
mod win {
 use super::{Bounds,KeyBinding};
 use std::sync::{Mutex,OnceLock,mpsc,atomic::{AtomicU32,Ordering}};
 use tauri::Emitter;
 use windows_sys::Win32::{Foundation::*,UI::WindowsAndMessaging::*,System::{LibraryLoader::GetModuleHandleW,Threading::GetCurrentThreadId}};
 struct State {overlay:isize,target:isize,region:RECT,buttons:Vec<Bounds>,keys:Vec<KeyBinding>,pressed:Option<usize>,sender:mpsc::SyncSender<usize>}
 static STATE:OnceLock<Mutex<Option<State>>>=OnceLock::new();
 static THREAD:AtomicU32=AtomicU32::new(0);
 static WORKER:Mutex<Option<std::thread::JoinHandle<()>>>=Mutex::new(None);
 fn state()->&'static Mutex<Option<State>>{STATE.get_or_init(||Mutex::new(None))}
 unsafe extern "system" fn mouse(code:i32,w:WPARAM,l:LPARAM)->LRESULT {
  if code>=0 {if let Ok(mut guard)=state().try_lock(){if let Some(s)=guard.as_mut(){
   let event=&*(l as *const MSLLHOOKSTRUCT);
   if event.pt.x<s.region.left||event.pt.x>=s.region.right||event.pt.y<s.region.top||event.pt.y>=s.region.bottom{return CallNextHookEx(std::ptr::null_mut(),code,w,l)}
   let hit=s.buttons.iter().position(|b|event.pt.x>=b.x&&event.pt.y>=b.y&&event.pt.x<b.x+b.width&&event.pt.y<b.y+b.height);
   if w as u32==WM_LBUTTONDOWN {s.pressed=hit;return 1}
   if w as u32==WM_LBUTTONUP {if let Some(i)=s.pressed.take(){if hit==Some(i){let _=s.sender.try_send(i);}}return 1}
   if w as u32==WM_RBUTTONDOWN {let _=s.sender.try_send(2);return 1}
   if w as u32==WM_RBUTTONUP{return 1}
  }}}
  CallNextHookEx(std::ptr::null_mut(),code,w,l)
 }
 unsafe extern "system" fn keyboard(code:i32,w:WPARAM,l:LPARAM)->LRESULT {
  if code>=0 {if let Ok(guard)=state().try_lock(){if let Some(s)=guard.as_ref(){
   if GetForegroundWindow()!=s.target as _ {return CallNextHookEx(std::ptr::null_mut(),code,w,l)}
   let event=&*(l as *const KBDLLHOOKSTRUCT);
   let down=|key|windows_sys::Win32::UI::Input::KeyboardAndMouse::GetAsyncKeyState(key)<0;
   let action=s.keys.iter().find(|binding|binding.matches(event.vkCode,down(17),down(18),down(16),down(91)||down(92))).map(|binding|binding.action);
   if let Some(i)=action {if w as u32==WM_KEYDOWN||w as u32==WM_SYSKEYDOWN {let _=s.sender.try_send(i);}return 1}
  }}}
  CallNextHookEx(std::ptr::null_mut(),code,w,l)
 }
 pub fn start(app:tauri::AppHandle,overlay:isize,target:isize,x:i32,y:i32,mut buttons:Vec<Bounds>,keys:Vec<KeyBinding>)->Result<(),String>{
  if target==0||unsafe{IsWindow(target as _)}==0{return Err("原始窗口已关闭，请重新截图".into())}
  if buttons.len()!=4||buttons.iter().any(|b|b.width<=0||b.height<=0){return Err("滚动截图按钮尚未就绪".into())}
  if keys.len()>4||keys.iter().any(|k|k.action>3||k.key_code==0||k.key_code>255){return Err("滚动截图快捷键无效".into())}
  for b in &mut buttons{b.x+=x;b.y+=y;}
  {let mut guard=state().lock().unwrap();if let Some(s)=guard.as_mut(){s.buttons=buttons;s.keys=keys;return Ok(())}}
  unsafe{if SetWindowDisplayAffinity(overlay as _,0x11)==0{return Err("系统不支持实时滚动截图".into())}}
  let (sender,receiver)=mpsc::sync_channel(8);let (ready,wait)=mpsc::sync_channel(1);
  let mut region:RECT=unsafe{std::mem::zeroed()};unsafe{GetWindowRect(overlay as _,&mut region);}
  *state().lock().unwrap()=Some(State{overlay,target,region,buttons,keys,pressed:None,sender});
  std::thread::spawn(move||{while let Ok(i)=receiver.recv(){let _=app.emit_to("capture","desktop:scroll-action",i);}});
  *WORKER.lock().unwrap()=Some(std::thread::spawn(move||unsafe{
   let mut message:MSG=std::mem::zeroed();PeekMessageW(&mut message,std::ptr::null_mut(),0,0,PM_NOREMOVE);
   THREAD.store(GetCurrentThreadId(),Ordering::SeqCst);
   let module=GetModuleHandleW(std::ptr::null());
   let mh=SetWindowsHookExW(WH_MOUSE_LL,Some(mouse),module,0);let kh=SetWindowsHookExW(WH_KEYBOARD_LL,Some(keyboard),module,0);
   let success=!mh.is_null()&&!kh.is_null();let _=ready.send(success);
   if success{while GetMessageW(&mut message,std::ptr::null_mut(),0,0)>0{TranslateMessage(&message);DispatchMessageW(&message);}}
   if !mh.is_null(){UnhookWindowsHookEx(mh);}if !kh.is_null(){UnhookWindowsHookEx(kh);}
  }));
  if wait.recv().unwrap_or(false){Ok(())}else{stop();Err("无法启用滚动截图控制".into())}
 }
 pub fn stop(){
  if let Some(s)=state().lock().unwrap().take(){unsafe{SetWindowDisplayAffinity(s.overlay as _,0);}}
  let thread=THREAD.swap(0,Ordering::SeqCst);if thread!=0{unsafe{PostThreadMessageW(thread,WM_QUIT,0,0);}}
  if let Some(worker)=WORKER.lock().unwrap().take(){let _=worker.join();}
 }
}
#[cfg(windows)]pub use win::{start,stop};
#[cfg(not(windows))]pub fn start(_:tauri::AppHandle,_:isize,_:isize,_:i32,_:i32,_:Vec<Bounds>,_:Vec<KeyBinding>)->Result<(),String>{Err("实时滚动截图仅支持 Windows".into())}
#[cfg(not(windows))]pub fn stop(){}
#[cfg(test)]mod key_tests{use super::*;#[test]fn configured_chords_match_exactly(){let key=KeyBinding{key_code:54,ctrl:true,alt:true,shift:false,meta:false,action:1};assert!(key.matches(54,true,true,false,false));assert!(!key.matches(54,false,true,false,false));assert!(!key.matches(54,true,true,true,false));assert!(!key.matches(83,true,true,false,false));}#[test]fn defaults_and_disabled_keys(){assert_eq!(default_keys().iter().find(|k|k.matches(27,false,false,false,false)).map(|k|k.action),Some(2));assert!(!default_keys().iter().any(|k|k.matches(27,true,false,false,false)));let none:Vec<KeyBinding>=vec![];assert!(!none.iter().any(|k|k.matches(13,false,false,false,false)));}}
