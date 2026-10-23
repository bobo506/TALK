"""只检查测试创建进程的控制台；在独立辅助进程中附加，绝不改变被测进程。"""
import ctypes
from ctypes import wintypes as w
import json
import sys

kernel=ctypes.WinDLL("kernel32",use_last_error=True)
user=ctypes.WinDLL("user32",use_last_error=True)
kernel.AttachConsole.argtypes=[w.DWORD];kernel.AttachConsole.restype=w.BOOL
kernel.GetConsoleWindow.restype=w.HWND
user.IsWindowVisible.argtypes=[w.HWND];user.IsWindowVisible.restype=w.BOOL
kernel.FreeConsole()
if kernel.AttachConsole(int(sys.argv[1])):
    try:
        window=kernel.GetConsoleWindow()
        result={"console":bool(window),"visible":bool(window and user.IsWindowVisible(window))}
    finally:
        kernel.FreeConsole()
else:
    error=ctypes.get_last_error()
    if error!=6:  # ERROR_INVALID_HANDLE = 被测进程没有控制台，非权限/进程退出。
        raise ctypes.WinError(error)
    result={"console":False,"visible":False}
print(json.dumps(result))
