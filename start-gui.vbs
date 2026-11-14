' 无窗口启动 TALK 桌面版；供桌面快捷方式和双击使用（不弹命令行窗口）。
Option Explicit
Dim fso, shell, home
Set fso = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
home = fso.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = home
shell.Run """" & home & "\start-gui.bat""", 0, False
