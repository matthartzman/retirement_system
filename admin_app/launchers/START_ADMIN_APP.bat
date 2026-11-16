@echo off
cd /d "%~dp0\..\.."
rem Loopback only (127.0.0.1:5056). If the Admin app is already running this just opens the browser.
rem First time: python -m admin_app create-admin --username YOURNAME
python -m admin_app
pause
