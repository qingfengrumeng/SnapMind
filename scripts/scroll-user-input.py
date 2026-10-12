"""Test-only hardware-style mouse input; production capture never injects input."""
import ctypes, sys, json, time
from ctypes import wintypes as w
u = ctypes.WinDLL('user32', use_last_error=True)
class Mouse(ctypes.Structure):
    _fields_ = [('dx',w.LONG),('dy',w.LONG),('data',w.DWORD),('flags',w.DWORD),('time',w.DWORD),('extra',ctypes.c_size_t)]
class Union(ctypes.Union):
    _fields_ = [('mouse',Mouse),('pad',ctypes.c_byte*32)]
class Input(ctypes.Structure):
    _fields_ = [('type',w.DWORD),('union',Union)]
u.GetForegroundWindow.restype = w.HWND
u.SetProcessDPIAware()
mode,x,y = sys.argv[1],int(sys.argv[2]),int(sys.argv[3])
if mode != "inspect":
    u.SetCursorPos(x,y)
events = [Input(0,Union(mouse=Mouse(0,0,int(sys.argv[4]) & 0xffffffff,0x800,0,0)))] if mode in ('wheel','burst') else [Input(0,Union(mouse=Mouse(0,0,0,f,0,0))) for f in (2,4)]
array=(Input*len(events))(*events)
if mode != "inspect":
    for _ in range(8 if mode == "burst" else 1):
        assert u.SendInput(len(events),array,ctypes.sizeof(Input))==len(events),ctypes.get_last_error()
        if mode == "burst": time.sleep(.03)
p=w.POINT();u.GetCursorPos(ctypes.byref(p))
print(json.dumps({'foreground':u.GetForegroundWindow(),'x':p.x,'y':p.y}))
