# Cryptix Stratum Bridge Browser Monitor

Modern browser dashboard for the `cryptix-stratum-bridge` Prometheus metrics endpoint.

## Requirements

- Python 3.9+ (tested with Python 3.14)
- Running Cryptix Stratum Bridge with Prometheus metrics enabled
  - Default expected endpoint: `http://127.0.0.1:2114/metrics`

## Quick Start

### Windows

Run:

```bat
start-windows.bat
```

### Linux

Run:

```bash
chmod +x start-linux.sh
./start-linux.sh
```

## Manual Run

```bash
python3 fetch_metrics.py --host 0.0.0.0 --port 8080 --metrics-url http://127.0.0.1:2114/metrics --interval 5
```

## Options

```text
--metrics-url   Bridge Prometheus URL (default: http://127.0.0.1:2114/metrics)
--host          Bind host for monitor server (default: 0.0.0.0)
--port          Bind port for monitor server (default: 8080)
--interval      Poll interval seconds (default: 5)
--timeout       HTTP timeout seconds (default: 4)
--once          Fetch once and print parsed JSON
```

## Endpoints

- `/` dashboard UI
- `/api/snapshot` parsed live metrics JSON
- `/api/health` monitor health (`online` / `offline`)
