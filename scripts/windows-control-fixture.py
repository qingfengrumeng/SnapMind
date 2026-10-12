"""Generated Win32 controls for UIA tests, implemented entirely in Python."""
import argparse
import ctypes
from ctypes import wintypes
import json
from pathlib import Path
import win32api,win32con,win32gui

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);parser.add_argument('--snapshot',action='store_true');args=parser.parse_args()
    output=Path(args.output);output.mkdir(parents=True,exist_ok=True)
    user=ctypes.WinDLL('user32');user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p];user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    handles={};description=win32gui.LOGFONT();description.lfFaceName='Microsoft YaHei UI';description.lfHeight=-20;font=win32gui.CreateFontIndirect(description);background=win32gui.CreateSolidBrush(win32api.RGB(250,248,255))
    def window_proc(handle,message,wparam,lparam):
        if message==win32con.WM_TIMER:
            path=output/'command.json'
            if path.exists():
                command=json.loads(path.read_text(encoding='utf-8'));path.unlink()
                if command['action']=='close':win32gui.DestroyWindow(handle)
                elif command['action']=='rename':win32gui.SetWindowText(handles['Save'],'Changed')
                elif command['action']=='move':
                    l,t,r,b=win32gui.GetWindowRect(handle);win32gui.MoveWindow(handle,l+80,t+40,r-l,b-t,True)
            return 0
        if message==win32con.WM_DESTROY:win32gui.PostQuitMessage(0);return 0
        return win32gui.DefWindowProc(handle,message,wparam,lparam)
    window_class=win32gui.WNDCLASS();window_class.hInstance=win32api.GetModuleHandle(None);window_class.lpszClassName='SnapMindPythonFixture';window_class.lpfnWndProc=window_proc;window_class.hbrBackground=background
    win32gui.RegisterClass(window_class)
    width,height=(660,400) if args.snapshot else (540,340)
    style=win32con.WS_OVERLAPPEDWINDOW
    rect=wintypes.RECT(0,0,width,height);user.AdjustWindowRect(ctypes.byref(rect),style,False);outer=[rect.left,rect.top,rect.right,rect.bottom]
    form=win32gui.CreateWindowEx(win32con.WS_EX_TOPMOST,window_class.lpszClassName,'SnapMind generated snapshot fixture' if args.snapshot else 'SnapMind UIA control fixture',style,160,120,outer[2]-outer[0],outer[3]-outer[1],0,0,window_class.hInstance,None)
    def control(class_name,text,x,y,w,h,extra=0):
        hwnd=win32gui.CreateWindowEx(0,class_name,text,win32con.WS_CHILD|win32con.WS_VISIBLE|extra,x,y,w,h,form,0,window_class.hInstance,None)
        win32gui.SendMessage(hwnd,win32con.WM_SETFONT,font,True);return hwnd
    if args.snapshot:
        lst=control('LISTBOX','',25,25,610,345,win32con.WS_VSCROLL|win32con.WS_BORDER|win32con.LBS_NOINTEGRALHEIGHT)
        paragraphs=['框选图片后，可以拖动选区并调整大小。','滚动截图支持向上和向下连续拼接。','识别文字时，保留原文的换行与缩进。','翻译结果覆盖原文位置，保留行列关系。','可将多张截图粘贴到对话中继续提问。','气泡注释应简短，并指向对应内容。','表格复制后，可以粘贴到电子表格中。','保存截图图片，便于整理与再次查看。']
        win32gui.SendMessage(lst,win32con.LB_ADDSTRING,0,'滚动截图验证文档 · 以下均为测试内容')
        for i in range(1,81):win32gui.SendMessage(lst,win32con.LB_ADDSTRING,0,f'第 {i:03d} 条：{paragraphs[(i-1)%len(paragraphs)]}')
        handles['List']=lst
    else:
        handles['Save']=control('BUTTON','Save',40,45,140,42,win32con.BS_PUSHBUTTON)
        handles['Cancel']=control('BUTTON','Cancel',230,45,140,42,win32con.BS_PUSHBUTTON)
        control('STATIC','Username',40,97,150,24)
        handles['Username']=control('EDIT','Synthetic example',40,125,330,34,win32con.WS_BORDER|win32con.ES_AUTOHSCROLL)
        control('STATIC','Output language',40,167,200,24)
        choice=control('COMBOBOX','',40,195,220,180,win32con.CBS_DROPDOWNLIST)
        win32gui.SendMessage(choice,win32con.CB_ADDSTRING,0,'English');win32gui.SendMessage(choice,win32con.CB_SETCURSEL,0,0);handles['Output language']=choice
        handles['Enabled']=control('BUTTON','Enabled',40,265,150,30,win32con.BS_AUTOCHECKBOX)
    # A hidden background launch overrides the first ShowWindow call on Windows.
    win32gui.ShowWindow(form,win32con.SW_SHOW);win32gui.ShowWindow(form,win32con.SW_SHOW);win32gui.UpdateWindow(form)
    if not win32gui.IsWindowVisible(form):raise RuntimeError('Generated fixture is not visible')
    try:win32gui.SetForegroundWindow(form)
    except Exception:pass
    win32gui.PumpWaitingMessages()
    ctypes.WinDLL('dwmapi').DwmFlush()
    origin=win32gui.ClientToScreen(form,(0,0))
    if args.snapshot:
        l,t,r,b=win32gui.GetWindowRect(handles['List']);info={'x':l+4,'y':t+4,'width':r-l-28,'height':b-t-8}
    else:info={'x':origin[0],'y':origin[1],'width':width,'height':height,'expected':[{'text':name,'display':win32gui.GetWindowText(hwnd),'bbox':list(win32gui.GetWindowRect(hwnd))} for name,hwnd in handles.items()]}
    import os
    info['pid']=os.getpid();(output/'fixture.json').write_text(json.dumps(info),encoding='utf-8')
    user.SetTimer.argtypes=[ctypes.c_void_p,ctypes.c_size_t,ctypes.c_uint,ctypes.c_void_p];user.SetTimer(form,1,100,None)
    try:win32gui.PumpMessages()
    finally:win32gui.DeleteObject(font);win32gui.DeleteObject(background)

if __name__=='__main__':main()
