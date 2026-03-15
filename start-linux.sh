#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

MONITOR_PORT=8080
BRIDGE_METRICS_URL="${BRIDGE_METRICS_URL:-http://127.0.0.1:2114/metrics}"

xdg-open "http://127.0.0.1:${MONITOR_PORT}" >/dev/null 2>&1 || true
python3 fetch_metrics.py --host 0.0.0.0 --port "${MONITOR_PORT}" --metrics-url "${BRIDGE_METRICS_URL}" --interval 5
