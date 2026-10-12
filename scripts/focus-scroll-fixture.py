"""Focus only the temporary synthetic scroll-test window."""
import ctypes
from ctypes import wintypes
user = ctypes.windll.user32
user.SetProcessDPIAware()
pid=wintypes.DWORD()
user.GetWindowThreadProcessId(user.GetForegroundWindow(),ctypes.byref(pid))
kernel=ctypes.WinDLL('kernel32',use_last_error=True)
kernel.OpenProcess.argtypes=[wintypes.DWORD,wintypes.BOOL,wintypes.DWORD];kernel.OpenProcess.restype=wintypes.HANDLE
kernel.QueryFullProcessImageNameW.argtypes=[wintypes.HANDLE,wintypes.DWORD,wintypes.LPWSTR,ctypes.POINTER(wintypes.DWORD)]
kernel.CloseHandle.argtypes=[wintypes.HANDLE]
process=kernel.OpenProcess(0x1000,False,pid.value);path=ctypes.create_unicode_buffer(32768);length=wintypes.DWORD(len(path))
try:
    name=path.value if process and kernel.QueryFullProcessImageNameW(process,0,path,ctypes.byref(length)) else ''
finally:
    if process:kernel.CloseHandle(process)
if name.lower().endswith('lockapp.exe'):
    raise RuntimeError('Windows is locked. Unlock the desktop to verify real scroll capture.')
callback = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
found = []
@callback
def visit(hwnd, _):
    title = ctypes.create_unicode_buffer(256)
    user.GetWindowTextW(hwnd, title, len(title))
    if title.value.startswith('SnapMind scroll fixture') and user.IsWindowVisible(hwnd):
        found.append(hwnd)
    return True
user.EnumWindows(visit, 0)
if not found:
    raise RuntimeError('Synthetic fixture window not found')
hwnd=found[0]
user.ShowWindow(hwnd,9)
positioned=user.SetWindowPos(hwnd, wintypes.HWND(-1), 0, 0, 0, 0, 0x1|0x2|0x40)
focused=user.SetForegroundWindow(hwnd)
import time
time.sleep(.3)
rect=wintypes.RECT();user.GetWindowRect(hwnd,ctypes.byref(rect))
if not focused:
    raise RuntimeError('Windows did not allow the synthetic window to gain focus')
print('Synthetic fixture focused')
