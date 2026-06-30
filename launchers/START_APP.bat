@echo off
REM This launcher lives in launchers/ — run from the project root one level up.
cd /d "%~dp0.."
set SCRIPT=tools\launchers\START_DESKTOP.py

:: Try py launcher and python on PATH first
py "%SCRIPT%" 2>nul && exit /b 0
python "%SCRIPT%" 2>nul && exit /b 0

:: Try known non-standard install location (Python 3.14 via install manager)
if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    "%LOCALAPPDATA%\Python\bin\python.exe" "%SCRIPT%" && exit /b 0
)

:: Use PowerShell to locate any python.exe on the system
for /f "usebackq delims=" %%P in (`powershell -NoProfile -Command "Get-ChildItem -Path $env:LOCALAPPDATA\Programs\Python, C:\Python*, $env:PROGRAMFILES\Python* -Filter python.exe -Recurse -ErrorAction SilentlyContinue | Where-Object { $_.Directory.Name -notlike '*Scripts*' } | Sort-Object -Descending { $_.FullName } | Select-Object -First 1 -ExpandProperty FullName" 2^>nul`) do (
    if exist "%%P" (
        "%%P" "%SCRIPT%" && exit /b 0
    )
)

:: Last resort: search registry for Python installs
for /f "usebackq tokens=2*" %%A in (`reg query "HKCU\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul`) do (
    if exist "%%B" (
        "%%B" "%SCRIPT%" && exit /b 0
    )
)
for /f "usebackq tokens=2*" %%A in (`reg query "HKLM\Software\Python\PythonCore" /s /v ExecutablePath 2^>nul`) do (
    if exist "%%B" (
        "%%B" "%SCRIPT%" && exit /b 0
    )
)

echo.
echo ERROR: Python not found.
echo Please install Python from https://python.org
echo Make sure to check "Add Python to PATH" during installation.
echo.
pause
