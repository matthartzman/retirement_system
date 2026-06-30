Dim WshShell, oShortcut, fso, strFolder, strRoot, strBat, strIcon

' This script lives in launchers/. START_APP.bat is alongside it; the icon and
' working directory are at the project root one level up.
strFolder = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\"))
strRoot   = Left(strFolder, InStrRev(Left(strFolder, Len(strFolder) - 1), "\"))
strBat    = strFolder & "START_APP.bat"
strIcon   = strRoot & "frontend\assets\retirement_planner.ico"

Set WshShell  = CreateObject("WScript.Shell")
Set fso       = CreateObject("Scripting.FileSystemObject")
Set oShortcut = WshShell.CreateShortcut(WshShell.SpecialFolders("Desktop") & "\Retirement Planner.lnk")

oShortcut.TargetPath       = strBat
oShortcut.WorkingDirectory = Left(strRoot, Len(strRoot) - 1)
oShortcut.WindowStyle      = 1

If fso.FileExists(strIcon) Then
    oShortcut.IconLocation = strIcon
End If

oShortcut.Save

MsgBox "Desktop shortcut created: 'Retirement Planner'", 64, "Done"
