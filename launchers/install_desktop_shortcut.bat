@echo off
cd /d "%~dp0.."
python tools\INSTALL_DESKTOP_ICON.py
echo.
echo Press any key to close.
pause >nul
