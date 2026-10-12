"""Check the running SnapMind HWND and real title-bar dragging; restore its position."""
import ctypes
import json
import time
from ctypes import wintypes

user32 = ctypes.WinDLL('user32', use_last_error=True)
user32.SetProcessDPIAware()
user32.FindWindowW.restype = wintypes.HWND
window = user32.FindWindowW(None, 'SnapMind 截图')
assert window, 'SnapMind main window not found'
user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
user32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
user32.SetForegroundWindow.argtypes = [wintypes.HWND]
user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]
assert not user32.GetWindowLongW(window, -20) & 0x8, 'Main window must not be always on top'
before = wintypes.RECT()
assert user32.GetWindowRect(window, ctypes.byref(before))
assert before.left > -10000, 'Show the main window before this test'
user32.SetForegroundWindow(window)
time.sleep(0.3)
x, y = before.left + 200, before.top + 24
try:
    user32.SetCursorPos(x, y)
    user32.mouse_event(2, 0, 0, 0, 0)
    time.sleep(0.15)
    for step in range(1, 9):
        user32.SetCursorPos(x + step * 5, y + step * 6)
        time.sleep(0.03)
    user32.mouse_event(4, 0, 0, 0, 0)
    time.sleep(0.3)
    after = wintypes.RECT()
    assert user32.GetWindowRect(window, ctypes.byref(after))
    movement = {'x': after.left - before.left, 'y': after.top - before.top}
    assert abs(movement['x']) >= 20 and abs(movement['y']) >= 20, movement
    print(json.dumps({'result': 'PASS', 'alwaysOnTop': False, 'realTitleBarDrag': movement}))
finally:
    user32.mouse_event(4, 0, 0, 0, 0)
    user32.SetWindowPos(window, None, before.left, before.top, 0, 0, 0x15)
