"""Read only the clipping region of this workspace's capture window."""
import ctypes
import json
import sys
from pathlib import Path
from ctypes import wintypes

user = ctypes.WinDLL('user32', use_last_error=True)
user.SetProcessDpiAwarenessContext.argtypes = [wintypes.HANDLE]
user.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
gdi = ctypes.WinDLL('gdi32', use_last_error=True)
kernel = ctypes.WinDLL('kernel32', use_last_error=True)
user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
kernel.OpenProcess.restype = wintypes.HANDLE
kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes = [wintypes.HANDLE]
user.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
gdi.CreateRectRgn.argtypes = [ctypes.c_int] * 4
gdi.CreateRectRgn.restype = wintypes.HANDLE
user.GetWindowRgn.argtypes = [wintypes.HWND, wintypes.HANDLE]
gdi.PtInRegion.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_int]
gdi.DeleteObject.argtypes = [wintypes.HANDLE]
request = json.load(sys.stdin)
expected = str(Path('src-tauri/target/debug/snapmind-desktop.exe').resolve()).casefold()
result = None
callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

@callback_type
def inspect(hwnd, _):
    global result
    title = ctypes.create_unicode_buffer(256)
    user.GetWindowTextW(hwnd, title, len(title))
    if title.value != 'SnapMind \u533a\u57df\u622a\u56fe':
        return True
    pid = wintypes.DWORD()
    user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel.OpenProcess(0x1000, False, pid.value)
    if not process:
        return True
    try:
        path = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(path))
        if not kernel.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)) or path.value.casefold() != expected:
            return True
    finally:
        kernel.CloseHandle(process)
    region = gdi.CreateRectRgn(0, 0, 0, 0)
    try:
        kind = user.GetWindowRgn(hwnd, region)
        result = {'kind': kind, 'points': [bool(gdi.PtInRegion(region, round(x), round(y))) for x, y in request['points']]}
    finally:
        gdi.DeleteObject(region)
    return False

user.EnumWindows.argtypes = [callback_type, wintypes.LPARAM]
user.EnumWindows(inspect, 0)
if result is None:
    raise RuntimeError('Workspace capture window not found')
print(json.dumps(result))
