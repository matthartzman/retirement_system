@echo off
cd /d "%~dp0.."
set SCRIPT=tools\INSTALL_DESKTOP_ICON.py

py "%SCRIPT%" && goto :done
python "%SCRIPT%" && goto :done

if exist "%LOCALAPPDATA%\Python\bin\pythonw.exe" (
    "%LOCALAPPDATA%\Python\bin\pythonw.exe" "%SCRIPT%" && goto :done
)

for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-ChildItem -Path $env:LOCALAPPDATA\Programs\Python, C:\Python*, $env:PROGRAMFILES\Python* -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Directory.Name -notlike '*Scripts*' } | Sort-Object -Descending { $_.FullName } | Select-Object -First 1 -ExpandProperty FullName" 2^>nul`) do (
    if exist "%%P" (
        "%%P" "%SCRIPT%" && goto :done
    )
)

for /f "usebackq tokens=2*" %%A in (`reg query "HKCU\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul`) do (
    if exist "%%B" ( "%%B" "%SCRIPT%" && goto :done )
)
for /f "usebackq tokens=2*" %%A in (`reg query "HKLM\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul`) do (
    if exist "%%B" ( "%%B" "%SCRIPT%" && goto :done )
)

echo.
echo ERROR: Python not found.
echo Please install Python from https://python.org
echo Make sure to check "Add Python to PATH" during installation.
echo.

:done
echo.
echo Press any key to close.
pause >nul
