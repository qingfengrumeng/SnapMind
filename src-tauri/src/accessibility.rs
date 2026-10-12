//! UIA labels and bounds are usable only while the frozen screenshot still matches.
use serde::{Deserialize,Serialize};

#[derive(Clone,Deserialize,Serialize)]
#[serde(rename_all="camelCase")]
pub struct Control {pub id:String,pub text:String,pub control_type:String,pub bbox:[f64;4]}
#[derive(Deserialize)]
#[serde(rename_all="camelCase")]
struct RawControl {text:String,control_type:String,bbox:[f64;4]}

pub fn stable_pixels(frozen:&[u8],live:&[u8],width:u32,height:u32,box_:[f64;4])->bool {
    if frozen.len()!=width as usize*height as usize*4 || live.len()!=frozen.len() || box_.iter().any(|v|!v.is_finite()){return false}
    let [l,t,r,b]=box_;if l<0.||t<0.||r>width as f64||b>height as f64||r-l<4.||b-t<4.{return false}
    let mut changed=0;let mut total=0;
    for y in t.floor() as u32..b.ceil() as u32 {for x in l.floor() as u32..r.ceil() as u32 {
        let i=(y as usize*width as usize+x as usize)*4;total+=1;
        if (0..3).any(|c|frozen[i+c].abs_diff(live[i+c])>18){changed+=1;}
    }}
    // Exact UIA correction is conservative: caret/antialias changes may pass;
    // a moved window, new content, or an overlay covering a control may not.
    total>0 && changed*1000<=total*3
}


#[cfg(windows)]
fn python_worker(request:serde_json::Value)->Result<serde_json::Value,String>{
 use std::{io::{Write,Read},os::windows::process::CommandExt,process::{Command,Stdio},time::{Duration,Instant}};
 let cwd=std::env::current_dir().map_err(|e|e.to_string())?;
 let root=if cwd.join("backend/app").is_dir(){cwd}else{std::env::current_exe().map_err(|e|e.to_string())?.ancestors().find(|p|p.join("backend/app").is_dir()).ok_or("Python backend directory unavailable")?.to_path_buf()};
 let local=root.join(".venv/Scripts/python.exe");let interpreter=std::env::var("SNAPMIND_PYTHON").unwrap_or_else(|_|if local.is_file(){local.to_string_lossy().to_string()}else{"python".into()});
 let mut child=Command::new(interpreter).arg(root.join("backend/app/windows_uia.py")).current_dir(&root).env("SNAPMIND_PROJECT_DIR",&root).creation_flags(0x08000000).stdin(Stdio::piped()).stdout(Stdio::piped()).stderr(Stdio::null()).spawn().map_err(|_|"Python UIA worker could not start".to_string())?;
 if let Some(mut input)=child.stdin.take(){if input.write_all(request.to_string().as_bytes()).is_err(){let _=child.kill();let _=child.wait();return Err("Python UIA request failed".into())}}
 let output=child.stdout.take().ok_or("Python UIA output unavailable")?;let reader=std::thread::spawn(move||{let mut bytes=Vec::new();let _=output.take(200_000).read_to_end(&mut bytes);bytes});let start=Instant::now();
 let status=loop{match child.try_wait(){Ok(Some(status))=>break status,Ok(None)=>{},Err(_)=>{let _=child.kill();let _=child.wait();let _=reader.join();return Err("Python UIA worker failed".into())}}if start.elapsed()>Duration::from_secs(7){let _=child.kill();let _=child.wait();let _=reader.join();return Err("Python UIA timeout".into())}std::thread::sleep(Duration::from_millis(20))};
 let bytes=reader.join().unwrap_or_default();if !status.success(){return Err("应用不支持此操作，或窗口位置已变化，请重新截图".into())}serde_json::from_slice(&bytes).map_err(|_|"Python UIA returned an invalid result".into())
}
#[cfg(windows)]
pub fn read_controls(x:i32,y:i32,width:u32,height:u32)->Result<Vec<Control>,String>{
 let result=python_worker(serde_json::json!({"action":"controls","x":x,"y":y,"width":width,"height":height,"excludePid":std::process::id()}))?;
 let raw:Vec<RawControl>=serde_json::from_value(result).map_err(|_|"Python UIA bounds unavailable".to_string())?;
 Ok(raw.into_iter().take(300).enumerate().map(|(i,c)|Control{id:format!("control-{}",i+1),text:c.text,control_type:c.control_type,bbox:c.bbox}).collect())
}
#[cfg(not(windows))]
pub fn read_controls(_:i32,_:i32,_:u32,_:u32)->Result<Vec<Control>,String>{Ok(vec![])}
#[cfg(test)]
mod tests {
 use super::*;
 #[test]fn stable_and_changed_control_pixels(){let a=vec![220;100*40*4];assert!(stable_pixels(&a,&a,100,40,[2.,2.,90.,35.]));let mut b=a.clone();for y in 5..15{for x in 5..40{b[(y*100+x)*4]=0;}}assert!(!stable_pixels(&a,&b,100,40,[2.,2.,90.,35.]));}
 #[test]fn invalid_and_offscreen_boxes(){let a=vec![1;400];for b in [[0.,0.,11.,4.],[0.,0.,3.,5.],[f64::NAN,0.,5.,5.],[-1.,0.,5.,5.]]{assert!(!stable_pixels(&a,&a,10,10,b));}}
}
