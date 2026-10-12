#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]
mod platform;
mod live_scroll;
mod accessibility;
use serde::{Deserialize, Serialize};
use std::{sync::{Arc,Mutex},time::{SystemTime,UNIX_EPOCH}};
use tauri::{Emitter,Manager,LogicalSize,PhysicalPosition,PhysicalSize};
use tauri_plugin_dialog::DialogExt;
use base64::{engine::general_purpose::STANDARD, Engine};
use tauri_plugin_global_shortcut::{GlobalShortcutExt,ShortcutState,Shortcut,Modifiers};
use tauri::tray::{MouseButton,MouseButtonState,TrayIconEvent};

#[derive(Clone,Serialize,Deserialize)]
struct Asset {id:String,name:String,data:String,width:u32,height:u32,scenario:String}
#[derive(Clone,Serialize)]
#[serde(rename_all="camelCase")]
struct Frame {asset:Asset,x:i32,y:i32,scale_factor:f64,floating_preview:bool}
#[derive(Clone,Serialize,Default)]
#[serde(rename_all="camelCase")]
struct Runtime {frame:Option<Frame>,asset:Option<Asset>,session_id:Option<String>,capture_active:bool,shortcut_available:bool,capture_shortcut:String}
#[derive(Serialize,Deserialize)]
#[serde(rename_all="camelCase")]
struct Preferences {capture_shortcut:String}
struct PreferencesUpdate(Mutex<()>);
#[derive(Default)]
struct DesktopState {runtime:Runtime,previous_windows:Vec<String>,monitor:Option<(i32,i32,u32,u32,f64)>,tray_opening:bool,shortcut_recording:bool,previous_foreground:isize,capture_image:Option<(String,Arc<Vec<u8>>)>,pending_completion:Option<String>,image_ready:bool,workspace_ready:bool}
#[derive(Deserialize)]
struct ResultImage {data:String,width:u32,height:u32,action:String}
type Store=Mutex<DesktopState>;
fn error(e:impl std::fmt::Display)->String{e.to_string()}
fn clock_id()->String{format!("capture-{}",SystemTime::now().duration_since(UNIX_EPOCH).unwrap_or_default().as_nanos())}
fn hide_tray(app:&tauri::AppHandle){if let Some(window)=app.get_webview_window("tray"){let _=window.hide();}}
fn clipboard_owner(app:&tauri::AppHandle)->isize{#[cfg(windows)]{app.get_webview_window("main").and_then(|w|w.hwnd().ok()).map(|h|h.0 as isize).unwrap_or(0)}#[cfg(not(windows))]{let _=app;0}}
#[tauri::command]
fn copy_capture_text(app:tauri::AppHandle,text:String)->Result<(),String>{if text.len()>200_000{return Err("文本过长".into())}platform::copy_text(&text,clipboard_owner(&app))}
#[tauri::command]
fn copy_image_asset(app:tauri::AppHandle,asset:Asset)->Result<(),String>{if asset.data.len()>16_000_000{return Err("图片过大".into())}platform::copy(&asset.data,clipboard_owner(&app))}
#[tauri::command]
fn copy_table_content(app:tauri::AppHandle,text:String,html:String)->Result<(),String>{if text.len()>400_000||html.len()>800_000{return Err("表格过大".into())}platform::copy_table(&text,&html,clipboard_owner(&app))}
#[tauri::command]
fn open_image_entity(url:String)->Result<(),String>{
 if url.len()>20000||url.chars().any(|c|c.is_control())||!(url.starts_with("http://")||url.starts_with("https://")||url.starts_with("mailto:")||url.starts_with("tel:")){return Err("链接类型不支持".into())}
 #[cfg(windows)]{use std::os::windows::process::CommandExt;std::process::Command::new("rundll32.exe").args(["url.dll,FileProtocolHandler",&url]).creation_flags(0x08000000).spawn().map_err(error)?;Ok(())}
 #[cfg(not(windows))]{Err("此操作需要 Windows 桌面端".into())}
}
#[tauri::command]
fn transform_pinned_image(app:tauri::AppHandle,window:tauri::WebviewWindow,asset:Asset)->Result<(),String>{
 if window.label()!="image"||asset.data.len()>16_000_000{return Err("无效的贴图变换".into())}
 let (w,h,_,_)=platform::decode_png(&asset.data)?;if w!=asset.width||h!=asset.height{return Err("图片尺寸不一致".into())}
 {app.state::<Store>().lock().map_err(error)?.runtime.asset=Some(asset.clone());}
 app.emit_to("image","desktop:asset-ready",asset.clone()).map_err(error)?;show_pinned_image(&app,&asset)
}
#[tauri::command]
async fn capture_control_targets(app:tauri::AppHandle,window:tauri::WebviewWindow,id:String,x:u32,y:u32,width:u32,height:u32)->Result<Vec<accessibility::Control>,String>{
 if window.label()!="capture"{return Err("仅截图窗口可读取控件边界".into())}
 let (origin_x,origin_y,frame_width,frame_height,bytes)={let managed=app.state::<Store>();let s=managed.lock().map_err(error)?;
  if !s.runtime.capture_active{return Ok(vec![])}
  let frame=s.runtime.frame.as_ref().ok_or("截图已结束")?;
  // Preview/uploaded/previous screenshots have no live desktop identity.
  let image=match &s.capture_image{Some((image_id,image)) if image_id==&id&&frame.asset.id==id=>image.clone(),_=>return Ok(vec![])};
  (frame.x,frame.y,frame.asset.width,frame.asset.height,image)
 };
 if width<8||height<8||x.checked_add(width).map_or(true,|v|v>frame_width)||y.checked_add(height).map_or(true,|v|v>frame_height){return Err("控件定位选区无效".into())}
 #[cfg(windows)]let overlay=window.hwnd().map_err(error)?.0 as isize;
 #[cfg(not(windows))]let overlay=0;
 let frame_id=id.clone();
 let controls=tauri::async_runtime::spawn_blocking(move||->Result<Vec<accessibility::Control>,String>{
  let candidates=accessibility::read_controls(origin_x+x as i32,origin_y+y as i32,width,height)?;
  if candidates.is_empty(){return Ok(vec![])}
  let (fw,fh,frozen)=platform::decode_png_pixels(&bytes)?;if fw!=frame_width||fh!=frame_height{return Ok(vec![])}
  let live=platform::capture_under_overlay(overlay,origin_x+x as i32,origin_y+y as i32,width,height)?;
  let (_,_,live)=platform::decode_png_pixels(&live)?;
  let mut cropped=Vec::with_capacity(width as usize*height as usize*4);
  for row in y..y+height{let start=(row as usize*fw as usize+x as usize)*4;cropped.extend_from_slice(&frozen[start..start+width as usize*4]);}
  Ok(candidates.into_iter().filter(|c|accessibility::stable_pixels(&cropped,&live,width,height,c.bbox)).collect())
 }).await.map_err(error)??;
 let managed=app.state::<Store>();let s=managed.lock().map_err(error)?;
 if !s.runtime.capture_active||s.capture_image.as_ref().map(|(id,_)|id)!=Some(&frame_id){return Ok(vec![])}
 Ok(controls)
}
#[tauri::command]
async fn capture_scroll_step(app:tauri::AppHandle,window:tauri::WebviewWindow,x:u32,y:u32,width:u32,height:u32)->Result<String,String>{
 if window.label()!="capture"{return Err("仅截图窗口可滚动截图".into())}
 let (mx,my,mw,mh)={let state=app.state::<Store>();let s=state.lock().map_err(error)?;if !s.runtime.capture_active{return Err("请先开始截图".into())}let (mx,my,mw,mh,_)=s.monitor.ok_or("未找到截图屏幕")?;(mx,my,mw,mh)};
 if width<20||height<80||x.checked_add(width).map_or(true,|v|v>mw)||y.checked_add(height).map_or(true,|v|v>mh){return Err("请框选可滚动正文区域，高度至少 80 像素".into())}
 tauri::async_runtime::spawn_blocking(move||platform::scroll_frame(mx+x as i32,my+y as i32,width,height)).await.map_err(error)?
}
#[tauri::command]
fn set_live_scroll(app:tauri::AppHandle,window:tauri::WebviewWindow,active:bool,buttons:Vec<live_scroll::Bounds>,keys:Option<Vec<live_scroll::KeyBinding>>)->Result<(),String>{
 if window.label()!="capture"{return Err("仅截图窗口可操作".into())}
 if !active{live_scroll::stop();window.set_ignore_cursor_events(false).map_err(error)?;if app.state::<Store>().lock().map_err(error)?.runtime.capture_active{let _=window.set_focus();}return Ok(())}
 let (mx,my,target)={let managed=app.state::<Store>();let state=managed.lock().map_err(error)?;if !state.runtime.capture_active{return Err("截图已结束".into())}let (mx,my,_,_,_)=state.monitor.ok_or("未找到屏幕")?;(mx,my,state.previous_foreground)};
 #[cfg(windows)]let handle=window.hwnd().map_err(error)?.0 as isize;
 #[cfg(not(windows))]let handle=0;
 live_scroll::start(app,handle,target,mx,my,buttons,keys.unwrap_or_else(live_scroll::default_keys))?;
 if let Err(e)=window.set_ignore_cursor_events(true){live_scroll::stop();return Err(error(e))}
 platform::restore_foreground(target);Ok(())
}
fn position_capture(win:&tauri::WebviewWindow,x:i32,y:i32,w:u32,h:u32)->Result<(),String>{
    #[cfg(windows)]{let handle=win.hwnd().map_err(error)?.0 as isize;platform::preview_regions(handle,None)?;platform::position_capture(handle,x,y,w,h)}
    #[cfg(not(windows))]{win.set_position(PhysicalPosition::new(x,y)).map_err(error)?;win.set_size(PhysicalSize::new(w,h)).map_err(error)}
}
fn restore(app:&tauri::AppHandle){
    live_scroll::stop();
    if let Some(w)=app.get_webview_window("capture"){let _=w.set_ignore_cursor_events(false);}
    let (labels,foreground)={let managed=app.state::<Store>();let mut state=managed.lock().unwrap();state.runtime.capture_active=false;state.runtime.frame=None;state.capture_image=None;state.pending_completion=None;(std::mem::take(&mut state.previous_windows),std::mem::take(&mut state.previous_foreground))};
    for label in labels{if let Some(w)=app.get_webview_window(&label){let _=w.show();}}
    platform::restore_foreground(foreground);
    platform::synchronize_desktop();
    if let Some(w)=app.get_webview_window("capture"){let _=w.hide();}
    let _=app.emit_to("capture","desktop:capture-closed",());
}

fn show_content(app:&tauri::AppHandle,win:&tauri::WebviewWindow)->Result<(),String>{
    // Always update Tao's visibility flags. Raw SWP_SHOWWINDOW leaves hide()
    // believing the window is already hidden and also leaves WebView visibility stale.
    win.show().map_err(error)?;
    #[cfg(windows)]{
        let pending=app.state::<Store>().lock().map_err(error)?.pending_completion.is_some();
        let behind=if pending{app.get_webview_window("capture").and_then(|w|w.hwnd().ok()).map(|h|h.0 as isize).unwrap_or(0)}else{0};
        platform::order_without_activation(win.hwnd().map_err(error)?.0 as isize,behind)
    }
    #[cfg(not(windows))]{let _=app;win.show().map_err(error)}
}

#[tauri::command]
fn hide_desktop_window(window:tauri::WebviewWindow)->Result<(),String>{
    window.hide().map_err(error)?;
    // Also recover windows shown by the previous raw Win32 implementation.
    #[cfg(windows)]{platform::hide_window(window.hwnd().map_err(error)?.0 as isize);}
    Ok(())
}

#[tauri::command]
fn capture_content_ready(app:tauri::AppHandle,window:tauri::WebviewWindow,id:String)->Result<(),String>{
    let foreground={let managed=app.state::<Store>();let mut state=managed.lock().map_err(error)?;
        if state.pending_completion.as_deref()!=Some(id.as_str()){return Ok(())}
        match window.label(){"image"=>state.image_ready=true,"workspace"=>state.workspace_ready=true,_=>return Err("仅内容窗口可确认就绪".into())}
        if !state.image_ready||!state.workspace_ready{return Ok(())}
        state.pending_completion=None;state.runtime.capture_active=false;state.runtime.frame=None;state.capture_image=None;state.previous_windows.clear();std::mem::take(&mut state.previous_foreground)
    };
    // Prepare the original foreground underneath the frozen screen, then reveal
    // the fully rendered image/workspace together without an intermediate desktop frame.
    platform::restore_foreground(foreground);platform::synchronize_desktop();
    if let Some(w)=app.get_webview_window("capture"){w.hide().map_err(error)?;}
    app.emit_to("capture","desktop:capture-closed",()).map_err(error)
}
async fn capture_start(app:tauri::AppHandle)->Result<(),String>{
    if app.state::<Store>().lock().map_err(error)?.runtime.capture_active{return Ok(())}
    let (cx,cy)=platform::cursor();let monitors=app.available_monitors().map_err(error)?;
    let selected=monitors.into_iter().find(|m|{let p=m.position();let s=m.size();cx>=p.x&&cy>=p.y&&cx<p.x+s.width as i32&&cy<p.y+s.height as i32});
    let monitor=match selected{Some(m)=>m,None=>app.primary_monitor().map_err(error)?.ok_or("未找到可截图的显示器")?};
    let (x,y,width,height,scale)=(monitor.position().x,monitor.position().y,monitor.size().width,monitor.size().height,monitor.scale_factor());
    {let state=app.state::<Store>();let mut s=state.lock().map_err(error)?;if s.runtime.capture_active{return Ok(())}s.runtime.capture_active=true;s.monitor=Some((x,y,width,height,scale));s.previous_windows.clear();s.previous_foreground=platform::foreground_window();}
    hide_tray(&app);
    // Capture the visible desktop without hiding/reopening its windows.
    // Prepare the existing capture window before delivering the in-memory image.
    let capture_window=match app.get_webview_window("capture"){Some(window)=>window,None=>{restore(&app);return Err("截图窗口未初始化".into())}};
    let worker=tauri::async_runtime::spawn_blocking(move||{platform::synchronize_desktop();platform::capture_image(x,y,width,height)});
    // The overlay is still hidden; position it while the worker reads/encodes pixels.
    if let Err(e)=position_capture(&capture_window,x,y,width,height){let _=worker.await;restore(&app);return Err(error(e))}
    let image=worker.await.map_err(error);
    let bytes=match image{Ok(Ok(data))=>data,Ok(Err(e))|Err(e)=>{restore(&app);return Err(e)}};
    let id=clock_id();let data=format!("http://snapmind-frame.localhost/{id}");
    let frame=Frame{asset:Asset{id:id.clone(),name:"屏幕截图".into(),data,width,height,scenario:"custom".into()},x,y,scale_factor:scale,floating_preview:false};
    {let managed=app.state::<Store>();let mut state=managed.lock().unwrap();state.capture_image=Some((id,Arc::new(bytes)));state.runtime.frame=Some(frame.clone());}
    let show=(||->Result<(),String>{app.emit_to("capture","desktop:capture-ready",frame).map_err(error)?;Ok(())})();
    if show.is_err(){restore(&app);}show
}
#[tauri::command]
fn show_capture_when_ready(app:tauri::AppHandle,window:tauri::WebviewWindow,id:String)->Result<(),String>{
    if window.label()!="capture"{return Err("仅截图窗口可确认画面就绪".into())}
    let state=app.state::<Store>();let s=state.lock().map_err(error)?;
    if !s.runtime.capture_active||s.runtime.frame.as_ref().map(|f|f.asset.id.as_str())!=Some(id.as_str()){return Ok(())}
    drop(s);
    window.show().map_err(error)?;window.set_focus().map_err(error)?;Ok(())
}
#[tauri::command]
async fn begin_capture(app:tauri::AppHandle)->Result<(),String>{capture_start(app).await}
#[tauri::command]
async fn begin_preview_capture(app:tauri::AppHandle,asset:Asset,floating_preview:Option<bool>)->Result<(),String>{
    if app.state::<Store>().lock().map_err(error)?.runtime.capture_active{return Ok(())}
    hide_tray(&app);
    let(w,h,_,_)=platform::decode_png(&asset.data)?;if w!=asset.width||h!=asset.height{return Err("图片尺寸不匹配".into())}
    let mon=app.primary_monitor().map_err(error)?.ok_or("未找到显示器")?;
    let x=mon.position().x;let y=mon.position().y;let mw=mon.size().width;let mh=mon.size().height;let scale=mon.scale_factor();
    let floating_preview=floating_preview.unwrap_or(false);
    let mut visible=Vec::new();for label in ["main","image","workspace"]{if floating_preview&&label!="image"{continue}if let Some(win)=app.get_webview_window(label){if win.is_visible().unwrap_or(false){visible.push(label.to_string());let _=win.hide();}}}
    let frame=Frame{asset,x,y,scale_factor:scale,floating_preview};{let state=app.state::<Store>();let mut s=state.lock().map_err(error)?;s.runtime.capture_active=true;s.runtime.frame=Some(frame.clone());s.capture_image=None;s.previous_windows=visible;s.previous_foreground=platform::foreground_window();s.monitor=Some((x,y,mw,mh,scale));}
    let win=app.get_webview_window("capture").ok_or("截图窗口不存在")?;position_capture(&win,x,y,mw,mh)?;app.emit_to("capture","desktop:capture-ready",frame).map_err(error)?;Ok(())
}
#[tauri::command]
async fn edit_desktop_image(app:tauri::AppHandle)->Result<(),String>{let asset=app.state::<Store>().lock().map_err(error)?.runtime.asset.clone().ok_or("没有截图")?;begin_preview_capture(app,asset,Some(true)).await}

#[derive(Deserialize)]
struct PreviewRegion{x:f64,y:f64,width:f64,height:f64}
#[tauri::command]
fn set_preview_regions(app:tauri::AppHandle,window:tauri::WebviewWindow,id:String,regions:Vec<PreviewRegion>)->Result<(),String>{
    if window.label()!="capture"||regions.len()>64{return Err("无效的贴图区域".into())}
    let current={let managed=app.state::<Store>();let state=managed.lock().map_err(error)?;state.runtime.capture_active&&state.runtime.frame.as_ref().map(|f|f.floating_preview&&f.asset.id==id).unwrap_or(false)};
    if !current{return Ok(())}
    if regions.iter().any(|r|![r.x,r.y,r.width,r.height].iter().all(|v|v.is_finite())||r.x<0.||r.y<0.||r.width<=0.||r.height<=0.){return Err("贴图区域超出范围".into())}
    let scale=window.scale_factor().map_err(error)?;
    let bounds=window.inner_size().map_err(error)?;
    let physical:Vec<[i32;4]>=regions.iter().map(|r|[(r.x*scale).floor().clamp(0.,bounds.width as f64) as i32,(r.y*scale).floor().clamp(0.,bounds.height as f64) as i32,((r.x+r.width)*scale).ceil().clamp(0.,bounds.width as f64) as i32,((r.y+r.height)*scale).ceil().clamp(0.,bounds.height as f64) as i32]).filter(|r|r[2]>r[0]&&r[3]>r[1]).collect();
    if physical.is_empty(){return Ok(())}
    #[cfg(windows)]{platform::preview_regions(window.hwnd().map_err(error)?.0 as isize,Some(&physical))?;}
    Ok(())
}
#[tauri::command]
fn cancel_capture(app:tauri::AppHandle,preview_bounds:Option<PreviewRegion>)->Result<(),String>{
    // Closing an image editor collapses it back to a pin, without saving edits.
    let preview=app.state::<Store>().lock().map_err(error)?.runtime.frame.clone().filter(|f|f.floating_preview);
    if let (Some(frame),Some(bounds))=(preview,preview_bounds){
        if ![bounds.x,bounds.y,bounds.width,bounds.height].iter().all(|v|v.is_finite())||bounds.width<=0.||bounds.height<=0.{return Err("图片边界无效".into())}
        let win=app.get_webview_window("image").ok_or("贴图窗口不存在")?;
        let width=(bounds.width*frame.scale_factor).round().max(1.) as u32;let height=(bounds.height*frame.scale_factor).round().max(1.) as u32;
        win.set_size(PhysicalSize::new(width,height)).map_err(error)?;
        position_capture(&win,frame.x+(bounds.x*frame.scale_factor).round() as i32,frame.y+(bounds.y*frame.scale_factor).round() as i32,width,height)?;
        app.state::<Store>().lock().map_err(error)?.runtime.asset=Some(frame.asset.clone());
        app.emit_to("image","desktop:asset-ready",frame.asset).map_err(error)?;
        restore(&app);show_content(&app,&win)?;
    }else{restore(&app)}
    Ok(())
}
#[tauri::command]
fn get_desktop_state(state:tauri::State<'_,Store>)->Result<Runtime,String>{Ok(state.lock().map_err(error)?.runtime.clone())}

#[tauri::command]
async fn finish_capture(app:tauri::AppHandle,result:ResultImage)->Result<(),String>{
    let (w,h,_,_)=platform::decode_png(&result.data)?;if w!=result.width||h!=result.height{return Err("截图尺寸与图像不一致".into())}
    if !["copy","save","pin"].contains(&result.action.as_str()){return Err("当前仅支持复制、保存和贴图".into())}
    let name=app.state::<Store>().lock().unwrap().runtime.frame.as_ref().map(|f|f.asset.name.clone()).unwrap_or("截图".into());
    let asset=Asset{id:clock_id(),name,data:result.data,width:w,height:h,scenario:"custom".into()};
    let notice=match platform::copy(&asset.data,clipboard_owner(&app)){
        Ok(())=>None,
        Err(e) if result.action=="copy"=>return Err(format!("复制截图失败：{e}。截图仍保留，请重试。")),
        Err(e)=>Some(e)
    };
    {let state=app.state::<Store>();let mut s=state.lock().map_err(error)?;
        if !s.runtime.capture_active||s.pending_completion.is_some(){return Err("当前截图已结束或正在完成".into())}
        s.runtime.asset=Some(asset.clone());s.pending_completion=if result.action=="pin"{Some(asset.id.clone())}else{None};s.image_ready=false;s.workspace_ready=true;
    }
    if result.action!="pin"{restore(&app);}
    app.emit_to("main","desktop:capture-finished",serde_json::json!({"asset":asset,"action":result.action,"notice":notice})).map_err(error)?;
    if result.action!="pin"{return Ok(())}
    let timeout_app=app.clone();let timeout_id=asset.id.clone();
    tauri::async_runtime::spawn(async move{let _=tauri::async_runtime::spawn_blocking(||std::thread::sleep(std::time::Duration::from_secs(8))).await;
        if timeout_app.state::<Store>().lock().map(|s|s.pending_completion.as_deref()==Some(timeout_id.as_str())).unwrap_or(false){restore(&timeout_app);let _=timeout_app.emit_to("main","desktop:error","内容窗口加载超时，截图已保留");}
    });
    Ok(())
}

fn show_pinned_image(app:&tauri::AppHandle,asset:&Asset)->Result<(),String>{
    let m=app.state::<Store>().lock().unwrap().monitor;
    let (mx,my,mw,mh,scale)=if let Some(m)=m{m}else{let mon=app.primary_monitor().map_err(error)?.ok_or("未找到显示器")?;(mon.position().x,mon.position().y,mon.size().width,mon.size().height,mon.scale_factor())};
    let sw=mw as f64/scale;let sh=mh as f64/scale;let image_width=(sw-48.).min(560.).min((sh-80.)*asset.width as f64/asset.height as f64).max(1.);
    let image_height=image_width*asset.height as f64/asset.width as f64;let left=((sw-image_width)/2.).max(12.);let top=40.;
    if let Some(win)=app.get_webview_window("image"){win.set_size(LogicalSize::new(image_width,image_height)).map_err(error)?;win.set_position(PhysicalPosition::new(mx+(left*scale) as i32,my+(top*scale) as i32)).map_err(error)?;show_content(app,&win)?;}
    Ok(())
}
#[tauri::command]
fn set_desktop_session(app:tauri::AppHandle,session_id:String,asset:Option<Asset>,action:Option<String>,notify_workspace:bool)->Result<(),String>{
    if session_id.len()>80{return Err("无效会话 ID".into())}
    {let state=app.state::<Store>();let mut s=state.lock().map_err(error)?;s.runtime.session_id=Some(session_id.clone());s.runtime.asset=asset.clone();}
    app.emit_to("image","desktop:asset-ready",asset.clone()).map_err(error)?;
    let pending=app.state::<Store>().lock().map_err(error)?.pending_completion.is_some();
    if pending{if let Some(ref a)=asset{show_pinned_image(&app,a)?;}}
    let _=(action,notify_workspace);
    if asset.is_none(){if let Some(w)=app.get_webview_window("image"){let _=w.hide();}}
    Ok(())
}
#[tauri::command]
fn zoom_desktop_image(app:tauri::AppHandle,window:tauri::WebviewWindow,factor:f64)->Result<(),String>{
    if window.label()!="image"||!factor.is_finite()||factor<=0.{return Err("无效的贴图缩放操作".into())}
    let asset=app.state::<Store>().lock().map_err(error)?.runtime.asset.clone().ok_or("没有贴图")?;
    let monitor=window.current_monitor().map_err(error)?.ok_or("未找到显示器")?;let area=monitor.work_area();
    let size=window.inner_size().map_err(error)?;let position=window.outer_position().map_err(error)?;
    let max_scale=((area.size.width as f64-32.)/asset.width as f64).min((area.size.height as f64-32.)/asset.height as f64);
    let min_scale=(64./asset.width.max(asset.height) as f64).min(max_scale);
    let image_scale=(size.width as f64/asset.width as f64*factor).clamp(min_scale,max_scale);
    let width=(asset.width as f64*image_scale).round().max(1.) as u32;let height=(asset.height as f64*image_scale).round().max(1.) as u32;
    let x=(position.x+(size.width as i32-width as i32)/2).clamp(area.position.x,area.position.x+(area.size.width-width) as i32);
    let y=(position.y+(size.height as i32-height as i32)/2).clamp(area.position.y,area.position.y+(area.size.height-height) as i32);
    window.set_size(PhysicalSize::new(width,height)).map_err(error)?;window.set_position(PhysicalPosition::new(x,y)).map_err(error)
}
#[tauri::command]
fn show_launcher(app:tauri::AppHandle)->Result<(),String>{hide_tray(&app);let w=app.get_webview_window("main").ok_or("主窗口不存在")?;w.unminimize().map_err(error)?;w.show().map_err(error)?;w.set_focus().map_err(error)?;Ok(())}
fn show_tray_at(app:&tauri::AppHandle,x:i32,y:i32)->Result<(),String>{
    if app.state::<Store>().lock().map_err(error)?.runtime.capture_active{return Ok(())}
    let monitor=app.available_monitors().map_err(error)?.into_iter().find(|m|{let p=m.position();let s=m.size();x>=p.x&&y>=p.y&&x<p.x+s.width as i32&&y<p.y+s.height as i32}).or(app.primary_monitor().map_err(error)?).ok_or("未找到显示器")?;
    let window=if let Some(window)=app.get_webview_window("tray"){window}else{tauri::WebviewWindowBuilder::new(app,"tray",tauri::WebviewUrl::App("index.html?desktop=tray".into())).title("SnapMind 快捷工具").inner_size(140.0,136.0).decorations(false).resizable(false).skip_taskbar(true).always_on_top(true).visible(false).build().map_err(error)?};
    let area=monitor.work_area();let scale=monitor.scale_factor();let margin=(8.0*scale).round() as i32;
    let width=((140.0*scale).round() as u32).min(area.size.width.saturating_sub((margin*2) as u32));let height=((136.0*scale).round() as u32).min(area.size.height.saturating_sub((margin*2) as u32));
    let left=(x-width as i32+margin).clamp(area.position.x+margin,area.position.x+area.size.width as i32-width as i32-margin);
    let top=(y-height as i32-margin).clamp(area.position.y+margin,area.position.y+area.size.height as i32-height as i32-margin);
    app.state::<Store>().lock().map_err(error)?.tray_opening=true;
    let result=(||{window.set_position(PhysicalPosition::new(left,top)).map_err(error)?;window.show().map_err(error)?;window.set_size(PhysicalSize::new(width,height)).map_err(error)?;window.set_focus().map_err(error)?;Ok(())})();
    app.state::<Store>().lock().map_err(error)?.tray_opening=false;result
}
#[tauri::command]
async fn show_tray_tools(app:tauri::AppHandle)->Result<(),String>{let(x,y)=platform::cursor();show_tray_at(&app,x,y)}
fn storage_home()->Result<std::path::PathBuf,String>{
    if let Some(path)=std::env::var_os("SNAPMIND_HOME"){return Ok(std::path::PathBuf::from(path))}
    if let Some(path)=std::env::var_os("SNAPMIND_DATA_DIR"){return Ok(std::path::PathBuf::from(path).join("snapmind"))}
    let project=std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR")).parent().ok_or("项目目录不存在")?.to_path_buf();
    let path=project.join(".snapmind");let legacy=project.join("snapmind");
    if legacy.exists(){
        if path.exists(){return Err("snapmind 与 .snapmind 同时存在，迁移已停止以避免覆盖数据".into())}
        std::fs::rename(legacy,&path).map_err(error)?;
    }
    Ok(path)
}
fn shortcut_path(app:&tauri::AppHandle)->Result<std::path::PathBuf,String>{
    let path=storage_home()?.join("preferences.json");
    if !path.exists(){
        std::fs::create_dir_all(path.parent().ok_or("设置目录不存在")?).map_err(error)?;
        let legacy=app.path().app_config_dir().map_err(error)?.join("preferences.json");
        if std::env::var_os("SNAPMIND_HOME").is_none()&&std::env::var_os("SNAPMIND_DATA_DIR").is_none()&&legacy.exists(){std::fs::copy(legacy,&path).map_err(error)?;}
    }
    Ok(path)
}
fn validate_shortcut(value:&str)->Result<Shortcut,String>{
    if value.len()>64{return Err("快捷键格式不正确".into())}
    let shortcut=value.parse::<Shortcut>().map_err(|_|"请使用 Ctrl、Alt 或 Win 搭配字母、数字或功能键".to_string())?;
    if !shortcut.mods.intersects(Modifiers::CONTROL|Modifiers::ALT|Modifiers::SUPER){return Err("快捷键需要包含 Ctrl、Alt 或 Win".into())}Ok(shortcut)
}
#[tauri::command]
fn set_shortcut_recording(state:tauri::State<'_,Store>,recording:bool)->Result<(),String>{state.lock().map_err(error)?.shortcut_recording=recording;Ok(())}
#[tauri::command]
async fn set_capture_shortcut(app:tauri::AppHandle,shortcut:String)->Result<(),String>{
    let update=app.state::<PreferencesUpdate>();let _guard=update.0.lock().map_err(error)?;
    let next=validate_shortcut(&shortcut)?;
    let old=app.state::<Store>().lock().map_err(error)?.runtime.capture_shortcut.clone();
    let already_registered=app.global_shortcut().is_registered(next);
    if !already_registered{app.global_shortcut().register(next).map_err(|e|format!("无法注册该快捷键，可能已被其他软件占用：{e}"))?;}
    let persist=(||->Result<(),String>{let path=shortcut_path(&app)?;std::fs::create_dir_all(path.parent().ok_or("设置目录不存在")?).map_err(error)?;std::fs::write(path,serde_json::to_vec_pretty(&Preferences{capture_shortcut:shortcut.clone()}).map_err(error)?).map_err(error)})();
    if let Err(e)=persist{if !already_registered{let _=app.global_shortcut().unregister(next);}return Err(format!("保存快捷键失败：{e}"));}
    if let Ok(previous)=old.parse::<Shortcut>(){if previous!=next&&app.global_shortcut().is_registered(previous){let _=app.global_shortcut().unregister(previous);}}
    {let managed=app.state::<Store>();let mut state=managed.lock().map_err(error)?;state.runtime.capture_shortcut=shortcut.clone();state.runtime.shortcut_available=true;}
    app.emit("desktop:shortcut-changed",shortcut).map_err(error)
}
#[tauri::command]
async fn desktop_tool_action(app:tauri::AppHandle,action:String)->Result<(),String>{
    hide_tray(&app);
    match action.as_str(){
        "capture"=>capture_start(app).await,
        "quit"=>{app.exit(0);Ok(())},
        "launcher"|"gallery"|"settings"|"model-settings"=>{show_launcher(app.clone())?;app.emit_to("main","desktop:launcher-action",action).map_err(error)},
        _=>Err("未知的工具操作".into())
    }
}
#[tauri::command]
fn desktop_copy(app:tauri::AppHandle,state:tauri::State<'_,Store>)->Result<(),String>{let data=state.lock().map_err(error)?.runtime.asset.as_ref().ok_or("没有截图")?.data.clone();platform::copy(&data,clipboard_owner(&app))}
#[tauri::command]
async fn desktop_save(app:tauri::AppHandle)->Result<bool,String>{
    let data=app.state::<Store>().lock().map_err(error)?.runtime.asset.as_ref().ok_or("没有截图")?.data.clone();let(_,_,_,raw)=platform::decode_png(&data)?;
    tauri::async_runtime::spawn_blocking(move||{let path=app.dialog().file().add_filter("PNG 图像",&["png"]).set_file_name("SnapMind.png").blocking_save_file();if let Some(path)=path{std::fs::write(path.into_path().map_err(error)?,raw).map_err(error)?;Ok(true)}else{Ok(false)}}).await.map_err(error)?
}
#[tauri::command]
async fn save_usage_archive(app:tauri::AppHandle,filename:String,base64_data:String)->Result<bool,String>{
    if filename.len()>180||!filename.ends_with(".zip")||!filename.bytes().all(|c|c.is_ascii_alphanumeric()||b"-_.".contains(&c))||base64_data.len()>64_000_000{return Err("导出文件无效或过大".into())}
    let raw=STANDARD.decode(base64_data).map_err(|_|"无法读取导出文件".to_string())?;
    if !raw.starts_with(b"PK\x03\x04"){return Err("导出文件不是有效的 ZIP 压缩包".into())}
    tauri::async_runtime::spawn_blocking(move||{
        let selected=app.dialog().file().add_filter("ZIP 压缩包",&["zip"]).set_file_name(&filename).blocking_save_file();
        match selected{
            Some(path)=>{std::fs::write(path.into_path().map_err(|_|"保存位置无效".to_string())?,raw).map_err(|_|"无法保存文件，请检查保存位置是否可写".to_string())?;Ok(true)},
            None=>Ok(false)
        }
    }).await.map_err(|_|"保存文件失败，请重试".to_string())?
}
#[tauri::command]
fn native_status(app:tauri::AppHandle)->Result<serde_json::Value,String>{let state=app.state::<Store>().lock().map_err(error)?.runtime.clone();let windows=app.webview_windows().into_iter().map(|(name,w)|{(name,serde_json::json!({"visible":w.is_visible().unwrap_or(false),"size":w.inner_size().ok(),"position":w.outer_position().ok()}))}).collect::<serde_json::Map<_,_>>();Ok(serde_json::json!({"windows":windows,"captureActive":state.capture_active,"shortcutAvailable":state.shortcut_available,"sessionId":state.session_id,"hasAsset":state.asset.is_some()}))}

fn main(){
    let mut context=tauri::generate_context!();
    let browser=storage_home().expect("SnapMind storage directory").join("cache/browser");
    std::fs::create_dir_all(&browser).expect("SnapMind browser data directory");
    context.config_mut().app.app_directories_override=Some(tauri::utils::config::AppDirectoriesOverride::Directories(tauri::utils::config::AppDirectoryOverrides{
        local_data:Some(browser),cache:Some(storage_home().unwrap().join("cache")),log:Some(storage_home().unwrap().join("logs")),..Default::default()
    }));
    let icon=tauri::image::Image::from_bytes(include_bytes!("../icons/icon.png")).expect("SnapMind logo must be a valid PNG");
    context.set_default_window_icon(Some(icon));
    tauri::Builder::default().manage(Store::default()).manage(PreferencesUpdate(Mutex::new(())))
    .register_uri_scheme_protocol("snapmind-frame",|context,request|{
        let id=request.uri().path().trim_start_matches('/');
        let bytes=context.app_handle().state::<Store>().lock().ok().and_then(|state|state.capture_image.as_ref().filter(|(current,_)|current==id).map(|(_,bytes)|Arc::clone(bytes)));
        match bytes{Some(bytes)=>tauri::http::Response::builder().header("Content-Type","image/png").header("Access-Control-Allow-Origin","*").header("Cache-Control","no-store").body(bytes.as_ref().clone()).unwrap(),None=>tauri::http::Response::builder().status(404).header("Access-Control-Allow-Origin","*").body(Vec::new()).unwrap()}
    })
    .plugin(tauri_plugin_dialog::init())
    .plugin(tauri_plugin_global_shortcut::Builder::new().with_handler(|app,_,event|{if event.state()==ShortcutState::Pressed&&!app.state::<Store>().lock().map(|state|state.shortcut_recording).unwrap_or(true){let app=app.clone();tauri::async_runtime::spawn(async move{if let Err(e)=capture_start(app.clone()).await{let _=app.emit_to("main","desktop:error",e);}});}}).build())
    .invoke_handler(tauri::generate_handler![copy_image_asset,copy_table_content,open_image_entity,transform_pinned_image,capture_control_targets,set_live_scroll,capture_scroll_step,copy_capture_text,zoom_desktop_image,hide_desktop_window,capture_content_ready,show_capture_when_ready,begin_capture,begin_preview_capture,set_preview_regions,edit_desktop_image,cancel_capture,get_desktop_state,finish_capture,set_desktop_session,show_launcher,show_tray_tools,set_capture_shortcut,set_shortcut_recording,desktop_tool_action,desktop_copy,desktop_save,save_usage_archive,native_status])
    .setup(|app|{
        let shortcut=shortcut_path(app.handle()).ok().and_then(|path|std::fs::read(path).ok()).and_then(|data|serde_json::from_slice::<Preferences>(&data).ok()).map(|p|p.capture_shortcut).filter(|value|validate_shortcut(value).is_ok()).unwrap_or_else(||"Alt+Z".into());
        #[cfg(windows)]
        for label in ["capture","image","workspace"]{if let Some(win)=app.get_webview_window(label){if let Ok(hwnd)=win.hwnd(){platform::disable_window_transitions(hwnd.0 as isize);}}}
        let registration=app.global_shortcut().register(shortcut.as_str());{let managed=app.state::<Store>();let mut state=managed.lock().unwrap();state.runtime.shortcut_available=registration.is_ok();state.runtime.capture_shortcut=shortcut;}
        if let Err(e)=registration{eprintln!("Capture shortcut unavailable: {e}");}
        let icon=app.default_window_icon().cloned().ok_or("SnapMind application icon is missing")?;
        tauri::tray::TrayIconBuilder::with_id("snapmind").icon(icon).tooltip("SnapMind · 左键打开 / 右键工具").show_menu_on_left_click(false).on_tray_icon_event(|tray,event|{
            if let TrayIconEvent::Click{button,button_state:MouseButtonState::Up,position,..}=event{
                let app=tray.app_handle().clone();
                // WebView2 window creation must run outside the Windows event handler.
                tauri::async_runtime::spawn(async move{let result=match button{MouseButton::Left=>show_launcher(app.clone()),MouseButton::Right=>show_tray_at(&app,position.x.round() as i32,position.y.round() as i32),_=>Ok(())};if let Err(message)=result{let _=app.emit_to("main","desktop:error",message);}});
            }
        }).build(app)?;
        Ok(())
    })
    .on_window_event(|window,event|{match event{tauri::WindowEvent::CloseRequested{api,..}=>{api.prevent_close();let _=window.hide();},tauri::WindowEvent::Focused(false) if window.label()=="tray"=>{let opening=window.state::<Store>().lock().map(|state|state.tray_opening).unwrap_or(false);if !opening&&window.is_visible().unwrap_or(false)&&!window.is_focused().unwrap_or(false){let _=window.hide();}},_=>{}}})
    .run(context).expect("SnapMind desktop could not start");
}
