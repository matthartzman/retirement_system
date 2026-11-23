@echo off
cd /d "%~dp0\..\.."
rem Loopback only, behind a per-boot local token: the browser is opened with a one-time sign-in link built from the token file.
rem If the always-on server is already running this just opens it. Prints the link instead: python financial_trends_reporter\main.py --print-open-url
python financial_trends_reporter\main.py
pause
