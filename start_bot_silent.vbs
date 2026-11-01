Set WshShell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")
currentDir = fso.GetParentFolderName(WScript.ScriptFullName)
pythonwExe = currentDir & "\venv\Scripts\pythonw.exe"
runnerPy = currentDir & "\run_forever.py"

WshShell.CurrentDirectory = currentDir
WshShell.Run """" & pythonwExe & """ """ & runnerPy & """", 0, False
