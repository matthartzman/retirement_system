@echo off
cd /d "%~dp0\..\.."
rem --host 0.0.0.0 serves other devices on the network (needs Security/server_api_token).
python financial_trends_reporter\main.py --host 0.0.0.0
pause
