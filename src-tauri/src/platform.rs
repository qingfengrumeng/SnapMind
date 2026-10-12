//! Windows desktop capture and clipboard. All GDI handles are released before returning.
use base64::{engine::general_purpose::STANDARD, Engine};
use std::io::Cursor;

fn encode_png_bytes(width:u32,height:u32,color:png::ColorType,pixels:&[u8])->Result<Vec<u8>,String>{
    let mut bytes=Vec::new();
    {let mut encoder=png::Encoder::new(&mut bytes,width,height);encoder.set_color(color);encoder.set_depth(png::BitDepth::Eight);encoder.set_compression(png::Compression::Fast);encoder.set_filter(png::FilterType::Sub);encoder.set_adaptive_filter(png::AdaptiveFilterType::NonAdaptive);encoder.write_header().map_err(|e|e.to_string())?.write_image_data(pixels).map_err(|e|e.to_string())?;}
    Ok(bytes)
}
#[cfg(test)]
pub fn encode_png(width:u32,height:u32,rgba:&[u8])->Result<String,String>{Ok(format!("data:image/png;base64,{}",STANDARD.encode(encode_png_bytes(width,height,png::ColorType::Rgba,rgba)?)))}
pub fn decode_png(data:&str)->Result<(u32,u32,Vec<u8>,Vec<u8>),String>{
    if data.len()>12_000_000{return Err("截图超过当前会话的图片大小上限".into())}
    let raw=STANDARD.decode(data.strip_prefix("data:image/png;base64,").ok_or("仅接受 PNG 截图")?).map_err(|e|e.to_string())?;
    let(w,h,rgba)=decode_png_pixels(&raw)?;Ok((w,h,rgba,raw))
}
pub fn decode_png_pixels(raw:&[u8])->Result<(u32,u32,Vec<u8>),String>{
    let mut decoder=png::Decoder::new(Cursor::new(raw));decoder.set_transformations(png::Transformations::EXPAND|png::Transformations::STRIP_16);
    let mut reader=decoder.read_info().map_err(|e|e.to_string())?;
    let pixels=reader.info().width as usize*reader.info().height as usize;
    if pixels>40_000_000{return Err("图片分辨率超过处理上限".into())}
    let mut buf=vec![0;reader.output_buffer_size()];let info=reader.next_frame(&mut buf).map_err(|e|e.to_string())?;
    let channels=match info.color_type{png::ColorType::Rgba=>4,png::ColorType::Rgb=>3,png::ColorType::GrayscaleAlpha=>2,png::ColorType::Grayscale=>1,_=>return Err("不支持的 PNG 颜色格式".into())};
    let mut rgba=Vec::with_capacity(pixels*4);for p in buf[..info.buffer_size()].chunks_exact(channels){match channels{4=>rgba.extend_from_slice(p),3=>rgba.extend_from_slice(&[p[0],p[1],p[2],255]),2=>rgba.extend_from_slice(&[p[0],p[0],p[0],p[1]]),_=>rgba.extend_from_slice(&[p[0],p[0],p[0],255])}}
    Ok((info.width,info.height,rgba))
}

#[cfg(windows)]
pub fn cursor()->(i32,i32){use windows_sys::Win32::{Foundation::POINT,UI::WindowsAndMessaging::GetCursorPos};let mut p=POINT{x:0,y:0};unsafe{GetCursorPos(&mut p);}(p.x,p.y)}
#[cfg(not(windows))]
pub fn cursor()->(i32,i32){(0,0)}

/// Wait for the compositor to apply hidden-window updates, rather than sleeping a fixed 220 ms.
#[cfg(windows)]
pub fn synchronize_desktop(){unsafe{let _=windows_sys::Win32::Graphics::Dwm::DwmFlush();}}
#[cfg(not(windows))]
pub fn synchronize_desktop(){}

#[cfg(windows)]
pub fn foreground_window()->isize{unsafe{windows_sys::Win32::UI::WindowsAndMessaging::GetForegroundWindow() as isize}}
#[cfg(not(windows))]
pub fn foreground_window()->isize{0}
#[cfg(windows)]
pub fn restore_foreground(handle:isize){use windows_sys::Win32::UI::WindowsAndMessaging::*;unsafe{if handle!=0&&IsWindow(handle as _)!=0{let _=SetForegroundWindow(handle as _);}}}
#[cfg(not(windows))]
pub fn restore_foreground(_:isize){}

/// The OS owns a successfully assigned region; temporary GDI objects stay ours.
#[cfg(windows)]
pub fn preview_regions(handle:isize,rects:Option<&[[i32;4]]>)->Result<(),String>{
    use windows_sys::Win32::Graphics::Gdi::{CreateRectRgn,CombineRgn,DeleteObject,SetWindowRgn,RGN_OR};
    unsafe{
        let Some(rects)=rects else{if SetWindowRgn(handle as _,std::ptr::null_mut(),1)==0{return Err("无法恢复截图窗口范围".into())}return Ok(())};
        let region=CreateRectRgn(0,0,0,0);if region.is_null(){return Err("无法创建贴图范围".into())}
        for [left,top,right,bottom] in rects{
            let part=CreateRectRgn(*left,*top,*right,*bottom);
            if part.is_null(){DeleteObject(region as _);return Err("无法创建贴图区域".into())}
            let merged=CombineRgn(region,region,part,RGN_OR);DeleteObject(part as _);
            if merged==0{DeleteObject(region as _);return Err("无法合并贴图区域".into())}
        }
        if SetWindowRgn(handle as _,region,1)==0{DeleteObject(region as _);return Err("无法设置贴图范围".into())}
    }
    Ok(())
}

#[cfg(windows)]
pub fn order_without_activation(handle:isize,behind:isize)->Result<(),String>{
    use windows_sys::Win32::UI::WindowsAndMessaging::*;
    unsafe{let after=if behind!=0{behind as _}else{HWND_TOPMOST};if SetWindowPos(handle as _,after,0,0,0,0,SWP_NOMOVE|SWP_NOSIZE|SWP_NOACTIVATE)==0{return Err("无法排列内容窗口".into())}}
    Ok(())
}

#[cfg(windows)]
pub fn disable_window_transitions(handle:isize){use windows_sys::Win32::Graphics::Dwm::*;let disabled=1i32;unsafe{let _=DwmSetWindowAttribute(handle as _,DWMWA_TRANSITIONS_FORCEDISABLED as u32,&disabled as *const _ as _,std::mem::size_of_val(&disabled) as u32);}}
#[cfg(windows)]
pub fn hide_window(handle:isize){unsafe{windows_sys::Win32::UI::WindowsAndMessaging::ShowWindow(handle as _,windows_sys::Win32::UI::WindowsAndMessaging::SW_HIDE);}}

/// A screenshot must cover the physical pixels exactly; invisible resize borders
/// on an undecorated Windows window otherwise shrink/offset the canvas viewport.
#[cfg(windows)]
pub fn position_capture(handle:isize,x:i32,y:i32,width:u32,height:u32)->Result<(),String>{
    use windows_sys::Win32::UI::WindowsAndMessaging::*;
    use windows_sys::Win32::{Foundation::{RECT,POINT},Graphics::Gdi::ClientToScreen};
    unsafe{
        let hwnd=handle as _;
        // Keep Tao's styles intact: changing them here makes show()/hide() rewrite
        // the frame and shifts the WebView at the moment it becomes visible.
        if SetWindowPos(hwnd,HWND_TOPMOST,x,y,width as i32,height as i32,SWP_NOACTIVATE)==0{return Err("无法设置截图窗口边界".into())}
        // Winit also customizes WM_NCCALCSIZE, so removing styles alone does not
        // eliminate every non-client inset. Align the actual client area, not the outer bounds.
        let mut outer:RECT=std::mem::zeroed();let mut client:RECT=std::mem::zeroed();let mut origin=POINT{x:0,y:0};
        if GetWindowRect(hwnd,&mut outer)==0||GetClientRect(hwnd,&mut client)==0||ClientToScreen(hwnd,&mut origin)==0{return Err("无法读取截图窗口边界".into())}
        let extra_w=(outer.right-outer.left)-(client.right-client.left);
        let extra_h=(outer.bottom-outer.top)-(client.bottom-client.top);
        if SetWindowPos(hwnd,HWND_TOPMOST,x-(origin.x-outer.left),y-(origin.y-outer.top),width as i32+extra_w,height as i32+extra_h,SWP_NOACTIVATE)==0{return Err("无法对齐截图画面".into())}
    }
    Ok(())
}

#[cfg(windows)]
fn capture_rgb(x:i32,y:i32,width:u32,height:u32)->Result<Vec<u8>,String>{
    use windows_sys::Win32::Graphics::Gdi::*;
    if width==0||height==0||width as u64*height as u64>40_000_000{return Err("显示器尺寸不支持".into())}
    let mut rgb=Vec::with_capacity(width as usize*height as usize*3);
    unsafe {
        let screen=GetDC(std::ptr::null_mut());if screen.is_null(){return Err("无法访问屏幕".into())}
        let dc=CreateCompatibleDC(screen);if dc.is_null(){ReleaseDC(std::ptr::null_mut(),screen);return Err("无法创建截图上下文".into())}
        // Capture directly into CPU-readable top-down pixels. Avoid GetDIBits and
        // the full-screen BGRA staging/alpha passes before PNG encoding.
        let mut info:BITMAPINFO=std::mem::zeroed();info.bmiHeader.biSize=std::mem::size_of::<BITMAPINFOHEADER>() as u32;info.bmiHeader.biWidth=width as i32;info.bmiHeader.biHeight=-(height as i32);info.bmiHeader.biPlanes=1;info.bmiHeader.biBitCount=32;info.bmiHeader.biCompression=BI_RGB;
        let mut bits=std::ptr::null_mut();
        let bitmap=CreateDIBSection(screen,&info,DIB_RGB_COLORS,&mut bits,std::ptr::null_mut(),0);if bitmap.is_null(){DeleteDC(dc);ReleaseDC(std::ptr::null_mut(),screen);return Err("无法创建截图位图".into())}
        let old=SelectObject(dc,bitmap as _);
        let copied=BitBlt(dc,0,0,width as i32,height as i32,screen,x,y,SRCCOPY|CAPTUREBLT);
        // GDI may batch writes; flush before reading the DIB's memory.
        let flushed=GdiFlush();
        let valid=copied!=0&&flushed!=0&&!bits.is_null();
        if valid{for p in std::slice::from_raw_parts(bits as *const u8,width as usize*height as usize*4).chunks_exact(4){rgb.extend_from_slice(&[p[2],p[1],p[0]]);}}
        SelectObject(dc,old);
        DeleteObject(bitmap as _);DeleteDC(dc);ReleaseDC(std::ptr::null_mut(),screen);
        if !valid{return Err("截图失败，请尝试普通桌面窗口；受保护的画面可能无法截取".into())}
    }
    Ok(rgb)
}
#[cfg(not(windows))]
fn capture_rgb(_:i32,_:i32,_:u32,_:u32)->Result<Vec<u8>,String>{Err("当前原生截图仅实现 Windows".into())}

pub fn capture_image(x:i32,y:i32,width:u32,height:u32)->Result<Vec<u8>,String>{
    let pixels=capture_rgb(x,y,width,height)?;
    encode_png_bytes(width,height,png::ColorType::Rgb,&pixels)
}

#[cfg(all(test,windows))]
mod capture_benchmark{
 use super::*;
 #[test]#[ignore="Reads current desktop pixels; performance check only, no files written"]
 fn screenshot_stages(){
  for _ in 0..3{
   let start=std::time::Instant::now();let pixels=capture_rgb(0,0,2560,1440).unwrap();let read=start.elapsed();
   let start=std::time::Instant::now();let raw=encode_png_bytes(2560,1440,png::ColorType::Rgb,&pixels).unwrap();let encode=start.elapsed();
   let start=std::time::Instant::now();let (w,h,rgba)=decode_png_pixels(&raw).unwrap();assert_eq!((w,h),(2560,1440));assert_eq!(rgba.len(),2560*1440*4);
   println!("read_ms={} encode_ms={} decode_ms={} bytes={}",read.as_millis(),encode.as_millis(),start.elapsed().as_millis(),raw.len());
  }
 }
}

pub fn scroll_frame(x:i32,y:i32,width:u32,height:u32)->Result<String,String>{
 Ok(format!("data:image/png;base64,{}",STANDARD.encode(capture_image(x,y,width,height)?)))
}

#[cfg(windows)]
pub fn capture_under_overlay(handle:isize,x:i32,y:i32,width:u32,height:u32)->Result<Vec<u8>,String>{
    static GATE:std::sync::Mutex<()>=std::sync::Mutex::new(());
    let _gate=GATE.lock().map_err(|_|"像素核对忙碌".to_string())?;
    use windows_sys::Win32::UI::WindowsAndMessaging::{GetWindowDisplayAffinity,SetWindowDisplayAffinity};
    struct Restore(isize,u32);
    impl Drop for Restore{fn drop(&mut self){unsafe{SetWindowDisplayAffinity(self.0 as _,self.1);}synchronize_desktop();}}
    let mut previous=0;
    unsafe{if GetWindowDisplayAffinity(handle as _,&mut previous)==0||SetWindowDisplayAffinity(handle as _,0x11)==0{return Err("无法核对底层窗口像素".into())}}
    let _restore=Restore(handle,previous);synchronize_desktop();capture_image(x,y,width,height)
}
#[cfg(not(windows))]
pub fn capture_under_overlay(_:isize,_:i32,_:i32,_:u32,_:u32)->Result<Vec<u8>,String>{Err("UIA unavailable".into())}

#[cfg(windows)]
pub fn copy(data:&str,owner:isize)->Result<(),String>{
    use windows_sys::Win32::{System::{DataExchange::*,Memory::*},Foundation::{GlobalFree,HGLOBAL}};
    let (w,h,rgba,png)=decode_png(data)?;
    // Conventional bottom-up 24-bit DIB plus registered PNG, for image consumers
    // that do not accept a top-down 32-bit BI_RGB bitmap.
    let stride=(w as usize*3+3)&!3;let mut dib=vec![0u8;40+stride*h as usize];
    dib[0..4].copy_from_slice(&40u32.to_le_bytes());dib[4..8].copy_from_slice(&(w as i32).to_le_bytes());dib[8..12].copy_from_slice(&(h as i32).to_le_bytes());dib[12..14].copy_from_slice(&1u16.to_le_bytes());dib[14..16].copy_from_slice(&24u16.to_le_bytes());dib[20..24].copy_from_slice(&((stride*h as usize) as u32).to_le_bytes());
    for y in 0..h as usize{for x in 0..w as usize{let s=(y*w as usize+x)*4;let d=40+(h as usize-1-y)*stride+x*3;dib[d..d+3].copy_from_slice(&[rgba[s+2],rgba[s+1],rgba[s]]);}}
    unsafe fn allocate(bytes:&[u8])->Result<HGLOBAL,String>{
        let memory=GlobalAlloc(GMEM_MOVEABLE,bytes.len());if memory.is_null(){return Err("剪贴板内存分配失败".into())}
        let target=GlobalLock(memory);if target.is_null(){GlobalFree(memory);return Err("剪贴板内存访问失败".into())}
        std::ptr::copy_nonoverlapping(bytes.as_ptr(),target as *mut u8,bytes.len());GlobalUnlock(memory);Ok(memory)
    }
    unsafe{
        if owner==0{return Err("找不到剪贴板所属窗口".into())}
        let mut opened=false;for _ in 0..10{if OpenClipboard(owner as _)!=0{opened=true;break}std::thread::sleep(std::time::Duration::from_millis(20));}if !opened{return Err("剪贴板正在被其他程序占用，请重试".into())}
        let memory=match allocate(&dib){Ok(m)=>m,Err(e)=>{CloseClipboard();return Err(e)}};
        let png_memory=match allocate(&png){Ok(m)=>m,Err(e)=>{GlobalFree(memory);CloseClipboard();return Err(e)}};
        let png_format=RegisterClipboardFormatW([b'P' as u16,b'N' as u16,b'G' as u16,0].as_ptr());
        if EmptyClipboard()==0{GlobalFree(memory);GlobalFree(png_memory);CloseClipboard();return Err("无法打开剪贴板写入".into())}
        let dib_ok=!SetClipboardData(8,memory as _).is_null();if !dib_ok{GlobalFree(memory);}
        let png_ok=png_format!=0&&!SetClipboardData(png_format,png_memory as _).is_null();if !png_ok{GlobalFree(png_memory);}
        CloseClipboard();if !dib_ok&&!png_ok{return Err("无法写入系统剪贴板".into())}
    }Ok(())
}
#[cfg(not(windows))]
pub fn copy(_:&str,_:isize)->Result<(),String>{Err("当前原生剪贴板仅实现 Windows".into())}

#[cfg(test)]
mod tests{use super::*;#[test]fn png_roundtrip(){let data=encode_png(2,1,&[255,0,0,255,0,255,0,255]).unwrap();let(w,h,p,_)=decode_png(&data).unwrap();assert_eq!((w,h),(2,1));assert_eq!(p,vec![255,0,0,255,0,255,0,255]);}#[test]fn rejects_non_png(){assert!(decode_png("data:image/svg+xml;base64,aaa").is_err());}}

#[cfg(windows)]
pub fn copy_text(text:&str,owner:isize)->Result<(),String>{
 use windows_sys::Win32::{System::{DataExchange::*,Memory::*},Foundation::GlobalFree};
 let words:Vec<u16>=text.encode_utf16().chain(std::iter::once(0)).collect();
 unsafe{
  if owner==0{return Err("找不到剪贴板所属窗口".into())}
  let mut opened=false;for _ in 0..10{if OpenClipboard(owner as _)!=0{opened=true;break}std::thread::sleep(std::time::Duration::from_millis(20))}if !opened{return Err("剪贴板正在被占用".into())}
  let memory=GlobalAlloc(GMEM_MOVEABLE,words.len()*2);if memory.is_null(){CloseClipboard();return Err("剪贴板内存分配失败".into())}
  let target=GlobalLock(memory);if target.is_null(){GlobalFree(memory);CloseClipboard();return Err("剪贴板内存访问失败".into())}
  std::ptr::copy_nonoverlapping(words.as_ptr(),target as *mut u16,words.len());GlobalUnlock(memory);
  let ok=EmptyClipboard()!=0&&!SetClipboardData(13,memory as _).is_null();if !ok{GlobalFree(memory);}CloseClipboard();if !ok{return Err("无法写入剪贴板".into())}
 }Ok(())
}
#[cfg(not(windows))]
pub fn copy_text(_:&str,_:isize)->Result<(),String>{Err("当前原生剪贴板仅支持 Windows".into())}

pub fn table_html(html:&str)->String{
 let prefix="Version:1.0\r\nStartHTML:0000000000\r\nEndHTML:0000000000\r\nStartFragment:0000000000\r\nEndFragment:0000000000\r\n";
 let body=format!("<html><body><!--StartFragment-->{html}<!--EndFragment--></body></html>");
 let start=prefix.len();let end=start+body.len();let fragment=start+body.find("<!--StartFragment-->").unwrap()+20;let finish=start+body.find("<!--EndFragment-->").unwrap();
 format!("Version:1.0\r\nStartHTML:{start:010}\r\nEndHTML:{end:010}\r\nStartFragment:{fragment:010}\r\nEndFragment:{finish:010}\r\n{body}")
}
#[cfg(test)]
mod table_tests{
 use super::*;
 #[test]fn html_offsets_are_utf8_byte_offsets(){let value=table_html("<table><tr><td>中文 001</td></tr></table>");let field=|name:&str|->usize{value.lines().find(|line|line.starts_with(name)).unwrap().split(':').nth(1).unwrap().parse().unwrap()};let bytes=value.as_bytes();let start=field("StartHTML");let end=field("EndHTML");let fragment=field("StartFragment");let finish=field("EndFragment");assert_eq!(&bytes[start..start+6],b"<html>");assert_eq!(end,bytes.len());assert_eq!(std::str::from_utf8(&bytes[fragment..finish]).unwrap(),"<table><tr><td>中文 001</td></tr></table>");}
}
#[cfg(windows)]
pub fn copy_table(text:&str,html:&str,owner:isize)->Result<(),String>{
 use windows_sys::Win32::{System::{DataExchange::*,Memory::*},Foundation::GlobalFree};
 let utf16:Vec<u16>=text.encode_utf16().chain(std::iter::once(0)).collect();let content=table_html(html);let mut encoded=content.into_bytes();encoded.push(0);
 unsafe{
  let mut opened=false;for _ in 0..10{if OpenClipboard(owner as _)!=0{opened=true;break}std::thread::sleep(std::time::Duration::from_millis(20))}if !opened{return Err("剪贴板正在被占用".into())}
  let plain=GlobalAlloc(GMEM_MOVEABLE,utf16.len()*2);let rich=GlobalAlloc(GMEM_MOVEABLE,encoded.len());if plain.is_null()||rich.is_null(){if !plain.is_null(){GlobalFree(plain);}if !rich.is_null(){GlobalFree(rich);}CloseClipboard();return Err("剪贴板内存分配失败".into())}
  let p=GlobalLock(plain);let h=GlobalLock(rich);if p.is_null()||h.is_null(){if !p.is_null(){GlobalUnlock(plain);}if !h.is_null(){GlobalUnlock(rich);}GlobalFree(plain);GlobalFree(rich);CloseClipboard();return Err("无法写入剪贴板内存".into())}
  std::ptr::copy_nonoverlapping(utf16.as_ptr(),p as *mut u16,utf16.len());std::ptr::copy_nonoverlapping(encoded.as_ptr(),h as *mut u8,encoded.len());GlobalUnlock(plain);GlobalUnlock(rich);
  let format:Vec<u16>="HTML Format".encode_utf16().chain(std::iter::once(0)).collect();let html_format=RegisterClipboardFormatW(format.as_ptr());if EmptyClipboard()==0{GlobalFree(plain);GlobalFree(rich);CloseClipboard();return Err("无法打开剪贴板写入".into())}
  let plain_ok=!SetClipboardData(13,plain as _).is_null();let html_ok=html_format!=0&&!SetClipboardData(html_format,rich as _).is_null();if !plain_ok{GlobalFree(plain);}if !html_ok{GlobalFree(rich);}CloseClipboard();if !plain_ok||!html_ok{return Err("表格剪贴板格式写入不完整".into())}
 }Ok(())
}
#[cfg(not(windows))]
pub fn copy_table(text:&str,_:&str,owner:isize)->Result<(),String>{copy_text(text,owner)}
