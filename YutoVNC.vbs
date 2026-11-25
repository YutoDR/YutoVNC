Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
strDir = fso.GetParentFolderName(WScript.ScriptFullName)

' Run pythonw silently without popping up a black console window
WshShell.CurrentDirectory = strDir
WshShell.Run "pythonw.exe main.py", 0, False
