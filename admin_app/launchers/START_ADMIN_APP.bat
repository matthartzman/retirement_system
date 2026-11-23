@echo off
cd /d "%~dp0\..\.."
rem Loopback only (127.0.0.1:5056), behind a per-boot local token: this launcher reads the token file and opens the browser
rem with a one-time sign-in link (the token itself is never in a URL). If the Admin app is already running this just opens it.
rem First time: python -m admin_app create-admin --username YOURNAME
python -m admin_app
pause
