@echo off
REM Rebuild the standalone exe and back the project up to OneDrive.
REM Equivalent to:  python build.py
cd /d "%~dp0.."
set SCRIPT=build.py

py "%SCRIPT%" %* && goto :done
python "%SCRIPT%" %* && goto :done

if exist "%LOCALAPPDATA%\Python\bin\python.exe" (
    "%LOCALAPPDATA%\Python\bin\python.exe" "%SCRIPT%" %* && goto :done
)

echo.
echo ERROR: Python not found. Install Python from https://python.org
echo and ensure "Add Python to PATH" is checked.
echo.

:done
echo.
echo Press any key to close.
pause >nul
