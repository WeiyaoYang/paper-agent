Set files = CreateObject("Scripting.FileSystemObject")
Set shell = CreateObject("WScript.Shell")
root = files.GetParentFolderName(WScript.ScriptFullName)
shell.CurrentDirectory = root
shell.Run Chr(34) & root & "\.venv\Scripts\pythonw.exe" & Chr(34) & " " & Chr(34) & root & "\" & files.GetBaseName(WScript.ScriptFullName) & ".pyw" & Chr(34), 0, False
