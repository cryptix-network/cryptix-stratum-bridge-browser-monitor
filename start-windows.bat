@echo off
setlocal
cd /d "%~dp0"

set MONITOR_PORT=8080
set BRIDGE_METRICS_URL=http://127.0.0.1:2114/metrics

start "" "http://127.0.0.1:%MONITOR_PORT%"
py fetch_metrics.py --host 0.0.0.0 --port %MONITOR_PORT% --metrics-url %BRIDGE_METRICS_URL% --interval 5

endlocal
