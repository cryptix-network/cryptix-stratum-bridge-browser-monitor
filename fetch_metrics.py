import requests
import time
from threading import Thread
from collections import defaultdict
from http.server import SimpleHTTPRequestHandler, HTTPServer
from socketserver import ThreadingMixIn

METRIC_NAMES = {
    "py_blocpy_mined": "Blocks Mined",
    "py_valid_share_counter": "Valid Share",
    "py_worker_errors": "Worker Errors",
    "py_invalid_share_counter": "Invalid Share",
    "py_valid_share_diff_counter": "Valid Share Difficulty",
    "py_worker_job_counter": "Job Counter"
}

METRIC_ORDER = [
    "Blocks Mined",
    "Valid Share",
    "Invalid Share",
    "Max Valid Share Difficulty",
    "Job Counter"
]


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    pass

def fetch_metrics():
    while True:
        try:
            url = 'http://localhost:2114/metrics'
            response = requests.get(url)
            if response.status_code == 200:
                metrics_by_wallet_device = defaultdict(lambda: defaultdict(dict))
                total_metrics_by_wallet = defaultdict(lambda: defaultdict(int))
                max_difficulty_by_wallet = defaultdict(int)
                blocks_mined_by_wallet = defaultdict(int)
                devices_by_wallet = defaultdict(set)
                network_hashrate = 0.0
                network_difficulty = 0.0

                for line in response.text.split('\n'):
                    if line.startswith('#') or not line.strip():
                        continue
                    parts = line.split(' ')
                    if len(parts) == 2:
                        metric, value = parts
                        metric_base = metric.split('{')[0]
                        if metric_base == "py_estimated_network_hashrate_gauge":
                            network_hashrate = int(float(value))
                        elif metric_base == "py_network_difficulty_gauge":
                            network_difficulty = int(float(value))
                        metric_name = METRIC_NAMES.get(metric_base, None)
                        if not metric_name:
                            continue

                        if '{' in metric:
                            metric_info = metric.split('{')[1].split('}')[0]
                            details = {k: v.strip('"') for k, v in (item.split('=') for item in metric_info.split(','))}
                            wallet = details.get('wallet')
                            device = details.get('worker', 'Unknown')
                            ip = details.get('ip', 'Unknown')

                            if wallet and device != 'tnn-dev' and device != 'Unknown':
                                key = f"{device} ({ip})"
                                metrics_by_wallet_device[wallet][key][metric_name] = int(float(value))
                                if metric_name != "Valid Share Difficulty":
                                    total_metrics_by_wallet[wallet][metric_name] += int(float(value))
                                if metric_name == "Valid Share Difficulty":
                                    max_difficulty_by_wallet[wallet] = max(max_difficulty_by_wallet[wallet], int(float(value)))
                                if metric_name == "Blocks Mined":
                                    blocks_mined_by_wallet[wallet] += int(float(value))
                                devices_by_wallet[wallet].add(key)

                with open('metrics.html', 'w', encoding='utf-8') as f:
                    f.write('<html><head><title>Cryptix Pool</title>')
                    f.write('<style>')
                    f.write('body { font-family: Arial, sans-serif; margin: 20px; }')
                    f.write('h1, h2 { color: #333; }')
                    f.write('table { width: 100%; border-collapse: collapse; margin-bottom: 20px; }')
                    f.write('th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }')
                    f.write('th { background-color: #f2f2f2; }')
                    f.write('tr:nth-child(even) { background-color: #f9f9f9; }')
                    f.write('tr:hover { background-color: #f1f1f1; }')
                    f.write('.tab { cursor: pointer; padding: 10px; background-color: #fff; border: 1px solid #ddd; margin-top: 5px; }')
                    f.write('.tab-content { display: none; padding: 10px; border: 1px solid #ddd; border-top: none; }')
                    f.write('.total_metrics_style { padding: 20px; border: 1px solid #ccc; margin-top: 20px; }')
                    f.write('.network-info { display: flex; gap: 10px; margin-bottom: 20px; }')
                    f.write('.network-info div { padding: 10px 20px; background-color: #007bff; color: white; border-radius: 5px; cursor: pointer; }')
                    f.write('.canvas-container { display: flex; gap: 20px; }')
                    f.write('.online-indicator { color: green; margin-left: 10px; }')  
                    f.write('</style>')
                    f.write('<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>')
                    f.write('<script>')
                    f.write('function toggleTabContent(id) {')
                    f.write('    var content = document.getElementById(id);')
                    f.write('    if (content.style.display === "none" || content.style.display === "") {')
                    f.write('        content.style.display = "block";')
                    f.write('    } else {')
                    f.write('        content.style.display = "none";')
                    f.write('    }')
                    f.write('}')
                    f.write('function renderChart(ctx, labels, data, title) {')
                    f.write('    new Chart(ctx, {')
                    f.write('        type: "bar",')
                    f.write('        data: {')
                    f.write('            labels: labels,')
                    f.write('            datasets: [{')
                    f.write('                label: title,')
                    f.write('                data: data,')
                    f.write('                backgroundColor: "rgba(75, 192, 192, 0.2)",')
                    f.write('                borderColor: "rgba(75, 192, 192, 1)",')
                    f.write('                borderWidth: 1')
                    f.write('            }]')
                    f.write('        },')
                    f.write('        options: {')
                    f.write('            scales: {')
                    f.write('                y: {')
                    f.write('                    beginAtZero: true')
                    f.write('                }')
                    f.write('            }')
                    f.write('        }')
                    f.write('    });')
                    f.write('}')
                    f.write('</script>')
                    f.write('</head><body>')
                    f.write('<h1>Cryptix Bridge Browser Interface <span id="last-updated" style="font-size: 0.6em; margin-left: 20px;"></span></h1>')

                    # Convert network_hashrate and network_difficulty to MH/s and display as integers
                    network_hashrate_mhs = int(network_hashrate / 1e6)
                    network_difficulty_mhs = int(network_difficulty / 1e6)

                    # Write network hashrate and difficulty as styled buttons
                    f.write('<div class="network-info">')
                    f.write(f'<div>Network Hashrate: {network_hashrate_mhs} MH/s</div>')
                    f.write(f'<div>Network Difficulty: {network_difficulty_mhs} M</div>')
                    f.write('</div>')

                    for wallet, totals in total_metrics_by_wallet.items():
                        f.write(f'<div class="total_metrics_style" id="{wallet}"><h3>Total Metrics for Wallet: {wallet}<span class="online-indicator" id="{wallet}-online" style="display:none;">ONLINE</span></h3>')  # Add ONLINE indicator
                        f.write('<div class="canvas-container">')

                        # General metrics except "Blocks Mined", "Valid Share Difficulty", and "Job Counter"
                        general_labels = [metric_name for metric_name in totals.keys() if metric_name not in ["Blocks Mined", "Valid Share Difficulty", "Job Counter"]]
                        general_data = [totals[metric_name] for metric_name in general_labels]
                        f.write(f'<canvas id="{wallet}-chart" width="400" height="200"></canvas>')
                        f.write('<script>')
                        f.write(f'var ctx = document.getElementById("{wallet}-chart").getContext("2d");')
                        f.write(f'var labels = {general_labels};')
                        f.write(f'var data = {general_data};')
                        f.write('renderChart(ctx, labels, data, "Metrics");')
                        f.write('</script>')

                        f.write(f'<canvas id="{wallet}-blocks-chart" width="400" height="200"></canvas>')
                        f.write('<script>')
                        f.write(f'var ctxBlocks = document.getElementById("{wallet}-blocks-chart").getContext("2d");')
                        f.write(f'var blocksLabels = ["Blocks Mined"];')
                        f.write(f'var blocksData = [{blocks_mined_by_wallet[wallet]}];')
                        f.write('renderChart(ctxBlocks, blocksLabels, blocksData, "Blocks Mined");')
                        f.write('</script>')

                        f.write(f'<canvas id="{wallet}-difficulty-chart" width="400" height="200"></canvas>')
                        f.write('<script>')
                        f.write(f'var ctxDifficulty = document.getElementById("{wallet}-difficulty-chart").getContext("2d");')
                        f.write(f'var difficultyLabels = ["Max Valid Share Difficulty"];')
                        f.write(f'var difficultyData = [{max_difficulty_by_wallet[wallet]}];')
                        f.write('renderChart(ctxDifficulty, difficultyLabels, difficultyData, "Max Valid Share Difficulty");')
                        f.write('</script>')

                        f.write('</div>')
                        f.write('<table><thead><tr><th>Metric</th><th>Total Value</th></tr></thead><tbody>')

                        for metric_name in METRIC_ORDER:
                            if metric_name == "Max Valid Share Difficulty":
                                metric_value = max_difficulty_by_wallet[wallet]
                            else:
                                metric_value = totals.get(metric_name, 0)
                            metric_id = f"{wallet}-{metric_name.replace(' ', '-')}"
                            f.write(f'<tr><td>{metric_name}</td><td id="{metric_id}">{metric_value}</td></tr>')

                        f.write('</tbody></table>')

                        f.write('<h2>Device Metrics</h2>')
                        for device_key, device_metrics in metrics_by_wallet_device[wallet].items():
                            f.write(f'<button class="tab" onclick="toggleTabContent(\'{device_key}\')">Show Metrics for {device_key}</button>')
                            f.write(f'<div id="{device_key}" class="tab-content">')
                            f.write('<table><thead><tr><th>Metric</th><th>Value</th></tr></thead><tbody>')
                            for metric_name, value in device_metrics.items():
                                f.write(f'<tr><td>{metric_name}</td><td>{value}</td></tr>')
                            f.write('</tbody></table>')
                            f.write('</div>')

                        f.write('</div>')

                    f.write('<script>document.getElementById("last-updated").textContent = "Last updated: " + new Date().toLocaleString();</script>')
                    f.write('</body></html>')

            else:
                print('Fehler beim Abrufen der Metriken', response.status_code)
        except requests.exceptions.RequestException as e:
            print(f"Fehler beim Abrufen der Metriken: {e}")
        time.sleep(10)

def start_server():
    server_address = ('', 80)
    httpd = ThreadedHTTPServer(server_address, SimpleHTTPRequestHandler)
    print('Starte den Server auf Port 80...')
    httpd.serve_forever()

if __name__ == "__main__":
   
    metrics_thread = Thread(target=fetch_metrics)
    metrics_thread.daemon = True
    metrics_thread.start()

  
    start_server()
