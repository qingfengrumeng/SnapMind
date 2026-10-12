"""Resize the actual SnapMind HWND from each edge, then restore its geometry."""
import ctypes
import json
import time
from ctypes import wintypes
u=ctypes.WinDLL('user32',use_last_error=True)
u.SetProcessDPIAware()
u.FindWindowW.restype=wintypes.HWND
w=u.FindWindowW(None,'SnapMind 截图')
assert w,'SnapMind main window is missing'
u.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.SetForegroundWindow.argtypes=[wintypes.HWND]
u.ShowWindow.argtypes=[wintypes.HWND,ctypes.c_int]
u.SetWindowPos.argtypes=[wintypes.HWND,wintypes.HWND,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_int,ctypes.c_uint]
u.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
u.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
u.WindowFromPoint.argtypes=[wintypes.POINT]
u.WindowFromPoint.restype=wintypes.HWND
u.GetAncestor.argtypes=[wintypes.HWND,ctypes.c_uint]
u.GetAncestor.restype=wintypes.HWND
def rect():
    r=wintypes.RECT();assert u.GetWindowRect(w,ctypes.byref(r));return r
original=rect()
assert original.left>-10000
results=[]
try:
    u.ShowWindow(w,9)
    u.SetForegroundWindow(w)
    for edge in ('North','South','East','West'):
        # Test helpers cannot always take foreground focus; temporarily raise only this HWND.
        assert u.SetWindowPos(w,wintypes.HWND(-1),original.left,original.top,original.right-original.left,original.bottom-original.top,0),ctypes.get_last_error()
        time.sleep(.3)
        r=rect()
        client=wintypes.RECT();u.GetClientRect(w,ctypes.byref(client))
        origin=wintypes.POINT(0,0);u.ClientToScreen(w,ctypes.byref(origin))
        x=origin.x+client.right//2;y=origin.y+client.bottom//2
        dx=dy=0
        if edge=='North':y=origin.y+2;dy=36
        if edge=='South':y=origin.y+client.bottom-2;dy=-36
        if edge=='East':x=origin.x+client.right-2;dx=-36
        if edge=='West':x=origin.x+2;dx=36
        hit=u.GetAncestor(u.WindowFromPoint(wintypes.POINT(x,y)),2)
        print(json.dumps({'edge':edge,'point':[x,y],'ownWindowAtPoint':hit==w,'client':[client.right,client.bottom]}),flush=True)
        u.SetCursorPos(x,y);u.mouse_event(2,0,0,0,0);time.sleep(.4)
        for step in range(1,7):
            u.SetCursorPos(x+dx*step//6,y+dy*step//6);time.sleep(.04)
        u.mouse_event(4,0,0,0,0);time.sleep(.3)
        after=rect()
        changed=(after.right-after.left)-(r.right-r.left) if dx else (after.bottom-after.top)-(r.bottom-r.top)
        assert abs(changed)>=20,{'edge':edge,'changed':changed}
        results.append({'edge':edge,'changed':changed})
    print(json.dumps({'result':'PASS','realMouseResize':results}))
finally:
    u.mouse_event(4,0,0,0,0)
    u.SetWindowPos(w,wintypes.HWND(-2),original.left,original.top,original.right-original.left,original.bottom-original.top,0)
