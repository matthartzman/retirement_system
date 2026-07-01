Dim WshShell, fso, strFolder, strRoot, strIcon, strPython
Dim oShortcut, strDesktop

' This script lives in launchers/. The project root is one level up.
strFolder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
strRoot   = Left(strFolder, InStrRev(Left(strFolder, Len(strFolder) - 1), "\"))
strIcon   = strRoot & "frontend\assets\retirement_planner.ico"

Set WshShell = CreateObject("WScript.Shell")
Set fso      = CreateObject("Scripting.FileSystemObject")
strDesktop   = WshShell.SpecialFolders("Desktop")

' Locate python.exe via py launcher, then fall back to PATH
strPython = ""
On Error Resume Next
Dim oExec
Set oExec = WshShell.Exec("cmd /c where pythonw.exe 2>nul")
oExec.StdOut.ReadAll
If oExec.ExitCode = 0 Then strPython = "pythonw" Else strPython = "pythonw"
On Error GoTo 0

' --- Shortcut 1: Retirement Planner (desktop app) ---
Dim strScript1
strScript1 = strRoot & "tools\launchers\START_DESKTOP.py"
Set oShortcut = WshShell.CreateShortcut(strDesktop & "\Retirement Planner.lnk")
oShortcut.TargetPath       = strPython
oShortcut.Arguments        = Chr(34) & strScript1 & Chr(34)
oShortcut.WorkingDirectory = Left(strRoot, Len(strRoot) - 1)
oShortcut.WindowStyle      = 1
If fso.FileExists(strIcon) Then oShortcut.IconLocation = strIcon
oShortcut.Save

' --- Shortcut 2: Reset Local Mode ---
Dim strScript2
strScript2 = strRoot & "tools\set_local_mode.py"
Set oShortcut = WshShell.CreateShortcut(strDesktop & "\Retirement Planner - Reset Local Mode.lnk")
oShortcut.TargetPath       = strPython
oShortcut.Arguments        = Chr(34) & strScript2 & Chr(34)
oShortcut.WorkingDirectory = Left(strRoot, Len(strRoot) - 1)
oShortcut.WindowStyle      = 1
If fso.FileExists(strIcon) Then oShortcut.IconLocation = strIcon
oShortcut.Save

MsgBox "Desktop shortcuts created:" & vbCrLf & _
       "  - Retirement Planner" & vbCrLf & _
       "  - Retirement Planner - Reset Local Mode", 64, "Done"
