"""Read only the generated fixture clipboard for the native regression test."""
import json,sys
import win32clipboard,win32con
win32clipboard.OpenClipboard()
try:
    result={'text':win32clipboard.GetClipboardData(win32con.CF_UNICODETEXT),'html':win32clipboard.GetClipboardData(win32clipboard.RegisterClipboardFormat('HTML Format'))}
    if isinstance(result['html'],bytes):result['html']=result['html'].decode('utf-8').rstrip('\0')
finally:win32clipboard.CloseClipboard()
sys.stdout.buffer.write(json.dumps(result,ensure_ascii=False).encode('utf-8'))
