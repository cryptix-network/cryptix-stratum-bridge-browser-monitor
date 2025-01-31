@echo off
cd /d "%~dp0"
start "" "http://localhost:80"
py fetch_metrics.py
pause