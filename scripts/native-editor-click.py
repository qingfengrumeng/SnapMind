"""Click a synthetic editor control only after checking its owning workspace window."""
import ctypes
import json
import sys
import time
from pathlib import Path
from ctypes import wintypes as W

u = ctypes.WinDLL('user32', use_last_error=True)
k = ctypes.WinDLL('kernel32', use_last_error=True)
u.SetProcessDpiAwarenessContext.argtypes = [W.HANDLE]
u.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
u.GetWindowTextW.argtypes = [W.HWND, W.LPWSTR, ctypes.c_int]
u.GetWindowThreadProcessId.argtypes = [W.HWND, ctypes.POINTER(W.DWORD)]
k.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
k.OpenProcess.restype = W.HANDLE
k.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
k.CloseHandle.argtypes = [W.HANDLE]
u.ClientToScreen.argtypes = [W.HWND, ctypes.POINTER(W.POINT)]
u.GetClientRect.argtypes = [W.HWND, ctypes.POINTER(W.RECT)]
u.IsWindowVisible.argtypes = [W.HWND]
u.WindowFromPoint.argtypes = [W.POINT]
u.WindowFromPoint.restype = W.HWND
u.GetAncestor.argtypes = [W.HWND, W.UINT]
u.GetAncestor.restype = W.HWND
u.GetCursorPos.argtypes = [ctypes.POINTER(W.POINT)]
callback_type = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
expected = str(Path('src-tauri/target/debug/snapmind-desktop.exe').resolve()).casefold()
windows = {}

@callback_type
def inspect(hwnd, _):
    pid = W.DWORD()
    u.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = k.OpenProcess(0x1000, False, pid.value)
    if not process:
        return True
    try:
        path = ctypes.create_unicode_buffer(32768)
        size = W.DWORD(len(path))
        if not k.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)) or path.value.casefold() != expected:
            return True
    finally:
        k.CloseHandle(process)
    title = ctypes.create_unicode_buffer(256)
    u.GetWindowTextW(hwnd, title, len(title))
    windows[title.value] = hwnd
    return True

u.EnumWindows.argtypes = [callback_type, W.LPARAM]
u.EnumWindows(inspect, 0)
request = json.load(sys.stdin)
capture = windows['SnapMind \u533a\u57df\u622a\u56fe']
origin = W.POINT()
u.ClientToScreen(capture, ctypes.byref(origin))
point = W.POINT(origin.x + round(request['x']), origin.y + round(request['y']))
assert u.IsWindowVisible(capture), 'Editor window must be visible'
assert u.GetAncestor(u.WindowFromPoint(point), 2) == capture, 'Refusing to click another window'
previous = W.POINT()
u.GetCursorPos(ctypes.byref(previous))
try:
    u.SetCursorPos(point.x, point.y)
    u.mouse_event(2, 0, 0, 0, 0)
    time.sleep(.05)
    u.mouse_event(4, 0, 0, 0, 0)
    time.sleep(.7)
finally:
    u.SetCursorPos(previous.x, previous.y)
print(json.dumps({'captureVisible': bool(u.IsWindowVisible(capture))}))
