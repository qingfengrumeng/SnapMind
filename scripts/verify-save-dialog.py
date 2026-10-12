"""Control only this workspace's SnapMind ZIP save dialog, using synthetic files."""
import ctypes
from ctypes import wintypes
from pathlib import Path
import sys
import time

root=Path(__file__).resolve().parent.parent
destination=Path(sys.argv[1]).resolve()
assert destination.is_relative_to(root/'artifacts'/'usage-dashboard')
assert destination.suffix=='.zip'
cancel=len(sys.argv)>2 and sys.argv[2]=='cancel'
user=ctypes.WinDLL('user32',use_last_error=True)
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
callback=ctypes.WINFUNCTYPE(wintypes.BOOL,wintypes.HWND,wintypes.LPARAM)
user.GetWindowTextW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user.GetClassNameW.argtypes=[wintypes.HWND,wintypes.LPWSTR,ctypes.c_int]
user.GetWindowThreadProcessId.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.DWORD)]
user.GetDlgItem.argtypes=[wintypes.HWND,ctypes.c_int]
user.GetDlgItem.restype=wintypes.HWND
user.SendMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD]
kernel.OpenProcess.restype=wintypes.HANDLE
kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
user.EnumWindows.argtypes=[callback,wintypes.LPARAM]
user.EnumChildWindows.argtypes=[wintypes.HWND,callback,wintypes.LPARAM]

def text(hwnd,function):
    buffer=ctypes.create_unicode_buffer(1024)
    function(hwnd,buffer,1024)
    return buffer.value

def control_text(hwnd):
    buffer=ctypes.create_unicode_buffer(1024)
    user.SendMessageW(hwnd,0x000d,1024,ctypes.cast(buffer,ctypes.c_void_p).value)
    return buffer.value

def ours(hwnd):
    pid=wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd,ctypes.byref(pid))
    process=kernel.OpenProcess(0x1000,False,pid.value)
    if not process:return False
    try:
        buffer=ctypes.create_unicode_buffer(32768);size=wintypes.DWORD(32768)
        return bool(kernel.QueryFullProcessImageNameW(process,0,buffer,ctypes.byref(size))) and Path(buffer.value)==root/'src-tauri'/'target'/'debug'/'snapmind-desktop.exe'
    finally:kernel.CloseHandle(process)

for attempt in range(100):
    dialogs=[]
    @callback
    def collect(hwnd,_):
        if text(hwnd,user.GetClassNameW)=='#32770' and ours(hwnd):dialogs.append(hwnd)
        return True
    user.EnumWindows(collect,0)
    for dialog in dialogs:
        edits=[]
        @callback
        def child(hwnd,_):
            if text(hwnd,user.GetClassNameW)=='Edit' and control_text(hwnd).startswith('SnapMind-'):edits.append(hwnd)
            return True
        user.EnumChildWindows(dialog,child,0)
        if not edits:continue
        if cancel:
            user.PostMessageW(dialog,0x0111,2,0)
        else:
            buffer=ctypes.create_unicode_buffer(str(destination))
            user.SendMessageW(edits[0],0x000c,0,ctypes.cast(buffer,ctypes.c_void_p).value)
            user.PostMessageW(dialog,0x0111,1,0)
        print('Controlled SnapMind ZIP dialog:', 'cancel' if cancel else 'save')
        sys.exit(0)
    time.sleep(.1)
raise RuntimeError('SnapMind ZIP save dialog not found')
