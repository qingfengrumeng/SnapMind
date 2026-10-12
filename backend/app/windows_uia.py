"""Native Windows UI Automation through Python COM; no CLR or C# helpers."""
import ctypes
from ctypes import wintypes
from collections import deque
import json
import math
import os
from pathlib import Path
import sys
import time

CONTROL_TYPES={50000:'Button',50002:'CheckBox',50003:'ComboBox',50004:'Edit',50005:'Hyperlink',50007:'ListItem',50011:'MenuItem',50013:'RadioButton',50015:'Slider',50016:'Spinner',50019:'TabItem',50024:'TreeItem'}

def load_uia():
    if os.name!='nt':raise RuntimeError('Windows UI Automation is unavailable')
    # Use a native COM MTA, without loading any .NET runtime.
    sys.coinit_flags=0
    vendor=Path(os.environ.get('SNAPMIND_PROJECT_DIR',Path.cwd()))/'backend'/'vendor'
    if vendor.is_dir():sys.path.insert(0,str(vendor))
    import comtypes.client
    cache=vendor.parent/'data'/'comtypes-gen'
    cache.mkdir(parents=True,exist_ok=True)
    comtypes.client.gen_dir=str(cache)
    module=comtypes.client.GetModule(str(Path(os.environ.get('SystemRoot','C:/Windows'))/'System32'/'UIAutomationCore.dll'))
    automation=comtypes.client.CreateObject('{FF48DBA4-60EF-4201-AA87-54103EEF594E}',interface=module.IUIAutomation)
    return automation,module

def native_windows(exclude_pid):
    user=ctypes.WinDLL('user32',use_last_error=True)
    user.SetThreadDpiAwarenessContext.argtypes=[ctypes.c_void_p]
    user.SetThreadDpiAwarenessContext.restype=ctypes.c_void_p
    user.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))
    user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
    user.IsWindowVisible.argtypes=[wintypes.HWND]
    dwm=ctypes.WinDLL('dwmapi');dwm.DwmGetWindowAttribute.argtypes=[wintypes.HWND,wintypes.DWORD,ctypes.c_void_p,wintypes.DWORD]
    values=[]
    callback_type=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
    @callback_type
    def visit(handle,_):
        pid=wintypes.DWORD();user.GetWindowThreadProcessId(handle,ctypes.byref(pid))
        rect=wintypes.RECT();cloaked=wintypes.DWORD()
        if pid.value!=exclude_pid and user.IsWindowVisible(handle) and user.GetWindowRect(handle,ctypes.byref(rect)):
            if dwm.DwmGetWindowAttribute(handle,14,ctypes.byref(cloaked),4)!=0 or cloaked.value==0:
                if rect.right>rect.left and rect.bottom>rect.top:values.append((int(handle),[rect.left,rect.top,rect.right,rect.bottom]))
        return True
    user.EnumWindows.argtypes=[callback_type,wintypes.LPARAM];user.EnumWindows(visit,0)
    return values

def contains(box,x,y):return box[0]<=x<box[2] and box[1]<=y<box[3]
def intersects(a,b):return min(a[2],b[2])>max(a[0],b[0]) and min(a[3],b[3])>max(a[1],b[1])
def inside(a,b):return b[0]<=a[0]<a[2]<=b[2] and b[1]<=a[1]<a[3]<=b[3]
def bounds(node):
    rect=node.CurrentBoundingRectangle
    return [float(rect.left),float(rect.top),float(rect.right),float(rect.bottom)]
def top_window(windows,x,y):return next((handle for handle,box in windows if contains(box,x,y)),None)
def walk(automation,root,timeout=1.8):
    walker=automation.ControlViewWalker;queue=deque([(root,0)]);start=time.monotonic();count=0
    while queue and count<1800 and time.monotonic()-start<timeout:
        node,depth=queue.popleft();count+=1
        try:
            if node.CurrentIsOffscreen:continue
            yield node
            if depth>=24:continue
            child=walker.GetFirstChildElement(node);siblings=0
            while child and siblings<512 and time.monotonic()-start<timeout:
                queue.append((child,depth+1));child=walker.GetNextSiblingElement(child);siblings+=1
        except Exception:continue

def read_controls(request,automation,windows):
    x,y,width,height=(request[k] for k in ('x','y','width','height'));crop=[x,y,x+width,y+height]
    roots=[]
    for a in (.1,.5,.9):
        for b in (.1,.5,.9):
            handle=top_window(windows,x+width*a,y+height*b)
            if handle and handle not in roots:roots.append(handle)
    output=[];start=time.monotonic()
    for handle in roots:
        if time.monotonic()-start>1.8:break
        try:root=automation.ElementFromHandle(handle)
        except Exception:continue
        for node in walk(automation,root,max(.1,1.8-(time.monotonic()-start))):
            try:
                box=bounds(node);kind=CONTROL_TYPES.get(node.CurrentControlType)
                if not kind or not inside(box,crop):continue
                w,h=box[2]-box[0],box[3]-box[1]
                if not(8<=w<=1400 and 8<=h<=350) or w*h>=width*height*.88:continue
                if top_window(windows,(box[0]+box[2])/2,(box[1]+box[3])/2)!=handle:continue
                # Labels and boundaries only. Never read a password/ValuePattern.
                text='' if node.CurrentIsPassword else (node.CurrentName or '')[:160]
                output.append({'text':text,'controlType':kind,'bbox':[box[0]-x,box[1]-y,box[2]-x,box[3]-y]})
                if len(output)>=300:return output
            except Exception:continue
    return output

def run(request):
    if not isinstance(request,dict) or request.get('action','controls')!='controls':raise ValueError('Unsupported action')
    coordinates=[request.get(k) for k in ('x','y','width','height')]
    if not all(isinstance(v,(int,float)) and not isinstance(v,bool) and math.isfinite(v) for v in coordinates) or min(coordinates[2:])<4:raise ValueError('Invalid crop')
    windows=native_windows(request.get('excludePid',0));automation,module=load_uia()
    return read_controls(request,automation,windows)

if __name__=='__main__':
    try:
        request=json.loads(sys.stdin.read(200_000));result=run(request)
        sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False,allow_nan=False).encode('utf-8'))
    except Exception:
        # Do not return private window contents in errors.
        sys.stderr.write('Windows UI Automation unavailable or target changed\n');sys.exit(1)
