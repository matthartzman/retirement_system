@echo off
cd /d "%~dp0\..\.."
rem Loopback only. If the always-on server is already running this just opens the browser.
python financial_trends_reporter\main.py
pause
