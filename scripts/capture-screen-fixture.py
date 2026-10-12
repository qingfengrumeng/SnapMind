"""Synthetic physical-screen fixture; emits pixel classes, never screen images."""
import ctypes
import json
import threading
import time
import tkinter as tk
from PIL import ImageGrab

user32 = ctypes.windll.user32
user32.SetProcessDPIAware()
width, height = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
root = tk.Tk()
root.title("SnapMind screen transition fixture")
root.overrideredirect(True)
root.geometry(f"{width}x{height}+0+0")
canvas = tk.Canvas(root, highlightthickness=0, borderwidth=0)
canvas.pack(fill="both", expand=True)
for x in range(0, width, 3):
    canvas.create_rectangle(x, 0, x + 3, height, fill="#ffffff" if x // 3 % 2 else "#182030", outline="")
root.update()
user32.SetCursorPos(width // 2, height // 2)
points = [(x, y) for x in (2, 5, 11, width - 2, width - 5) for y in (150, height // 3, height * 2 // 3, height - 50)]
stop = threading.Event()

def record():
    time.sleep(0.25)
    while not stop.is_set():
        frame = ImageGrab.grab()
        bits = [sum(frame.getpixel(p)[:3]) > 240 for p in points]
        print(json.dumps({"pixels": bits}), flush=True)
        time.sleep(0.015)

def finish():
    if stop.is_set():
        root.destroy()
    else:
        root.after(50, finish)

def read_input():
    input()
    stop.set()

threading.Thread(target=record, daemon=True).start()
threading.Thread(target=read_input, daemon=True).start()
root.after(50, finish)
root.after(30000, lambda: stop.set())
root.mainloop()
