#!/usr/bin/env python3
"""Cryptix Stratum Bridge browser monitor server.
"""

from __future__ import annotations

import argparse
import copy
import json
import logging
import os
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


METRIC_LINE_RE = re.compile(r"^([a-zA-Z_:][a-zA-Z0-9_:]*)(\{[^}]*\})?\s+(.+)$")
LABEL_RE = re.compile(r'([a-zA-Z_][a-zA-Z0-9_]*)="((?:[^"\\]|\\.)*)"')


NETWORK_METRICS = {
    "py_estimated_network_hashrate_gauge": ("hashrate_hs", float),
    "py_network_difficulty_gauge": ("difficulty", float),
    "py_network_block_count": ("block_count", int),
}


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def parse_metric_labels(raw_labels: str) -> dict[str, str]:
    labels: dict[str, str] = {}
    for key, raw_value in LABEL_RE.findall(raw_labels):
        labels[key] = bytes(raw_value, "utf-8").decode("unicode_escape")
    return labels


def safe_int(value: float) -> int:
    if value != value:  # NaN guard
        return 0
    return int(value)


def format_worker_key(worker: str, ip: str) -> str:
    clean_worker = worker or "anonymous"
    clean_ip = ip or "unknown"
    return f"{clean_worker}@{clean_ip}"


def build_empty_snapshot(metrics_url: str, status: str, error: str | None = None) -> dict[str, Any]:
    return {
        "status": status,
        "error": error,
        "bridge_metrics_url": metrics_url,
        "updated_at_unix": int(time.time()),
        "updated_at_iso": utc_now_iso(),
        "network": {
            "hashrate_hs": 0.0,
            "difficulty": 0.0,
            "block_count": 0,
        },
        "totals": {
            "blocks_mined": 0,
            "valid_shares": 0,
            "invalid_shares": 0,
            "jobs": 0,
            "disconnects": 0,
            "share_difficulty": 0.0,
        },
        "wallet_count": 0,
        "wallets": [],
    }


def parse_prometheus_snapshot(text: str, metrics_url: str) -> dict[str, Any]:
    snapshot = build_empty_snapshot(metrics_url, status="online")
    wallets: dict[str, dict[str, Any]] = {}

    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue

        metric_match = METRIC_LINE_RE.match(line)
        if not metric_match:
            continue

        metric_name = metric_match.group(1)
        metric_labels_raw = metric_match.group(2) or ""
        raw_value = metric_match.group(3)

        try:
            value = float(raw_value)
        except ValueError:
            continue

        network_mapping = NETWORK_METRICS.get(metric_name)
        if network_mapping is not None:
            target_key, caster = network_mapping
            snapshot["network"][target_key] = caster(value)
            continue

        labels = parse_metric_labels(metric_labels_raw)
        wallet = labels.get("wallet", "").strip()
        if not wallet:
            continue

        worker = labels.get("worker", "").strip() or "anonymous"
        miner = labels.get("miner", "").strip() or "unknown"
        ip = labels.get("ip", "").strip() or "unknown"
        worker_key = format_worker_key(worker, ip)

        wallet_entry = wallets.setdefault(
            wallet,
            {
                "wallet": wallet,
                "totals": {
                    "blocks_mined": 0,
                    "valid_shares": 0,
                    "invalid_shares": 0,
                    "jobs": 0,
                    "disconnects": 0,
                    "share_difficulty": 0.0,
                    "invalid_by_type": {},
                },
                "workers": {},
            },
        )

        worker_entry = wallet_entry["workers"].setdefault(
            worker_key,
            {
                "worker": worker,
                "ip": ip,
                "miner": miner,
                "blocks_mined": 0,
                "valid_shares": 0,
                "invalid_shares": 0,
                "jobs": 0,
                "disconnects": 0,
                "share_difficulty": 0.0,
                "invalid_by_type": {},
            },
        )

        int_value = safe_int(value)
        if metric_name == "py_blocpy_mined":
            worker_entry["blocks_mined"] = int_value
            wallet_entry["totals"]["blocks_mined"] += int_value
        elif metric_name == "py_valid_share_counter":
            worker_entry["valid_shares"] = int_value
            wallet_entry["totals"]["valid_shares"] += int_value
        elif metric_name == "py_worker_job_counter":
            worker_entry["jobs"] = int_value
            wallet_entry["totals"]["jobs"] += int_value
        elif metric_name == "py_worker_disconnect_counter":
            worker_entry["disconnects"] = int_value
            wallet_entry["totals"]["disconnects"] += int_value
        elif metric_name == "py_valid_share_diff_counter":
            worker_entry["share_difficulty"] = float(value)
            wallet_entry["totals"]["share_difficulty"] += float(value)
        elif metric_name == "py_invalid_share_counter":
            invalid_type = labels.get("type", "invalid")
            worker_entry["invalid_by_type"][invalid_type] = int_value
            worker_entry["invalid_shares"] += int_value
            wallet_entry["totals"]["invalid_shares"] += int_value
            current = wallet_entry["totals"]["invalid_by_type"].get(invalid_type, 0)
            wallet_entry["totals"]["invalid_by_type"][invalid_type] = current + int_value

    wallet_list = []
    for wallet_id in sorted(wallets.keys()):
        wallet_entry = wallets[wallet_id]
        workers = sorted(wallet_entry["workers"].values(), key=lambda w: (w["worker"], w["ip"]))
        wallet_entry["workers"] = workers

        wallet_entry["worker_count"] = len(workers)
        valid = wallet_entry["totals"]["valid_shares"]
        invalid = wallet_entry["totals"]["invalid_shares"]
        total = valid + invalid
        wallet_entry["acceptance_rate"] = 0.0 if total == 0 else round((valid / total) * 100.0, 2)

        snapshot["totals"]["blocks_mined"] += wallet_entry["totals"]["blocks_mined"]
        snapshot["totals"]["valid_shares"] += valid
        snapshot["totals"]["invalid_shares"] += invalid
        snapshot["totals"]["jobs"] += wallet_entry["totals"]["jobs"]
        snapshot["totals"]["disconnects"] += wallet_entry["totals"]["disconnects"]
        snapshot["totals"]["share_difficulty"] += wallet_entry["totals"]["share_difficulty"]
        wallet_list.append(wallet_entry)

    snapshot["wallets"] = wallet_list
    snapshot["wallet_count"] = len(wallet_list)
    snapshot["updated_at_unix"] = int(time.time())
    snapshot["updated_at_iso"] = utc_now_iso()
    return snapshot


def fetch_metrics_text(url: str, timeout: float) -> str:
    request = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        if response.status != 200:
            raise RuntimeError(f"bridge returned HTTP {response.status}")
        return response.read().decode("utf-8", errors="replace")


class MonitorState:
    def __init__(self, metrics_url: str) -> None:
        self._lock = threading.Lock()
        self._snapshot = build_empty_snapshot(metrics_url, status="starting")

    def set_snapshot(self, snapshot: dict[str, Any]) -> None:
        with self._lock:
            self._snapshot = snapshot

    def set_error(self, error_message: str) -> None:
        with self._lock:
            snapshot = copy.deepcopy(self._snapshot)
            snapshot["status"] = "offline"
            snapshot["error"] = error_message
            snapshot["updated_at_unix"] = int(time.time())
            snapshot["updated_at_iso"] = utc_now_iso()
            self._snapshot = snapshot

    def get_snapshot(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._snapshot)


def collect_loop(
    state: MonitorState,
    metrics_url: str,
    interval_seconds: float,
    request_timeout: float,
    stop_event: threading.Event,
) -> None:
    while not stop_event.is_set():
        try:
            raw_text = fetch_metrics_text(metrics_url, timeout=request_timeout)
            snapshot = parse_prometheus_snapshot(raw_text, metrics_url=metrics_url)
            state.set_snapshot(snapshot)
        except (urllib.error.URLError, TimeoutError, RuntimeError, OSError) as exc:
            state.set_error(str(exc))
            logging.warning("Failed to fetch bridge metrics: %s", exc)
        except Exception as exc:  # broad catch to keep monitor alive
            state.set_error(str(exc))
            logging.exception("Unexpected monitor error: %s", exc)

        stop_event.wait(interval_seconds)


def build_handler(static_dir: Path, state: MonitorState):
    class MonitorHandler(SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=str(static_dir), **kwargs)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            if parsed.path == "/api/snapshot":
                self._write_json(state.get_snapshot(), status_code=200)
                return
            if parsed.path == "/api/health":
                payload = state.get_snapshot()
                status_code = 200 if payload.get("status") == "online" else 503
                self._write_json({"status": payload.get("status"), "error": payload.get("error")}, status_code)
                return
            super().do_GET()

        def log_message(self, format_: str, *args):
            logging.info("%s - %s", self.address_string(), format_ % args)

        def _write_json(self, payload: dict[str, Any], status_code: int) -> None:
            data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    return MonitorHandler


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Cryptix Stratum Bridge browser monitor")
    parser.add_argument(
        "--metrics-url",
        default=os.getenv("BRIDGE_METRICS_URL", "http://127.0.0.1:2114/metrics"),
        help="Bridge Prometheus metrics URL (default: http://127.0.0.1:2114/metrics)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MONITOR_HOST", "0.0.0.0"),
        help="Bind host for monitor web server (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        default=int(os.getenv("MONITOR_PORT", "8080")),
        type=int,
        help="Bind port for monitor web server (default: 8080)",
    )
    parser.add_argument(
        "--interval",
        default=float(os.getenv("MONITOR_INTERVAL_SECONDS", "5")),
        type=float,
        help="Polling interval in seconds for bridge metrics (default: 5)",
    )
    parser.add_argument(
        "--timeout",
        default=float(os.getenv("MONITOR_REQUEST_TIMEOUT_SECONDS", "4")),
        type=float,
        help="HTTP timeout in seconds when fetching bridge metrics (default: 4)",
    )
    parser.add_argument(
        "--once",
        action="store_true",
        help="Fetch bridge metrics once and print parsed JSON to stdout",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if args.once:
        raw = fetch_metrics_text(args.metrics_url, timeout=args.timeout)
        snapshot = parse_prometheus_snapshot(raw, metrics_url=args.metrics_url)
        print(json.dumps(snapshot, indent=2))
        return

    static_dir = Path(__file__).resolve().parent
    state = MonitorState(metrics_url=args.metrics_url)
    stop_event = threading.Event()

    collector_thread = threading.Thread(
        target=collect_loop,
        kwargs={
            "state": state,
            "metrics_url": args.metrics_url,
            "interval_seconds": max(args.interval, 1.0),
            "request_timeout": max(args.timeout, 0.5),
            "stop_event": stop_event,
        },
        daemon=True,
        name="bridge-metrics-collector",
    )
    collector_thread.start()

    handler = build_handler(static_dir=static_dir, state=state)
    server = ThreadingHTTPServer((args.host, args.port), handler)
    logging.info("Monitor UI:  http://%s:%d", args.host, args.port)
    logging.info("Bridge URL:  %s", args.metrics_url)

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logging.info("Shutting down monitor...")
    finally:
        stop_event.set()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
