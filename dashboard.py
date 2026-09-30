"""
Live Web Dashboard for Wikidata Regional Bot.
Provides a real-time web UI on http://localhost:5000 to monitor bot status, live edit feed,
and submit custom QIDs directly from the browser.
"""

import os
import sys
import json
import time
import threading
import subprocess
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse

HOST = "localhost"
PORT = 5000

# Ensure Windows stdout handles UTF-8 characters
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

# Global shared state
BOT_PROCESS = None
LIVE_QUEUE = []
EDIT_STATS = {
    "total_processed": 0,
    "total_updated": 0,
    "total_skipped": 0,
    "status": "STOPPED"
}

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Wikidata Bot - Live Monitor & Feed</title>
    <link href="https://fonts.googleapis.com/css2?family=Outfit:wght@300;400;600;700&family=JetBrains+Mono:wght@400;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-color: #0b0f19;
            --card-bg: rgba(22, 30, 49, 0.75);
            --card-border: rgba(255, 255, 255, 0.08);
            --primary: #6366f1;
            --primary-glow: rgba(99, 102, 241, 0.35);
            --accent-bn: #ec4899;
            --accent-hi: #10b981;
            --text-main: #f3f4f6;
            --text-muted: #9ca3af;
        }

        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            font-family: 'Outfit', sans-serif;
            background-color: var(--bg-color);
            color: var(--text-main);
            min-height: 100vh;
            padding: 2rem;
            background-image: 
                radial-gradient(circle at 15% 15%, rgba(99, 102, 241, 0.12) 0%, transparent 40%),
                radial-gradient(circle at 85% 85%, rgba(236, 72, 153, 0.12) 0%, transparent 40%);
        }

        .container { max-width: 1200px; margin: 0 auto; }
        
        header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 2rem;
            padding-bottom: 1rem;
            border-bottom: 1px solid var(--card-border);
        }

        .title-box { display: flex; align-items: center; gap: 1rem; }
        .logo {
            width: 44px; height: 44px;
            background: linear-gradient(135deg, var(--primary), var(--accent-bn));
            border-radius: 12px;
            display: grid; place-items: center;
            font-weight: 700; font-size: 1.4rem;
            box-shadow: 0 0 20px var(--primary-glow);
        }

        .status-pill {
            padding: 0.5rem 1.2rem;
            border-radius: 99px;
            font-weight: 600; font-size: 0.9rem;
            display: flex; align-items: center; gap: 0.6rem;
            background: rgba(255, 255, 255, 0.05);
            border: 1px solid var(--card-border);
        }

        .dot { width: 10px; height: 10px; border-radius: 50%; background: #9ca3af; }
        .dot.running { background: #10b981; box-shadow: 0 0 10px #10b981; animation: pulse 2s infinite; }
        .dot.stopped { background: #ef4444; }

        @keyframes pulse { 0%, 100% { opacity: 1; } 50% { opacity: 0.4; } }

        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
            gap: 1.5rem;
            margin-bottom: 2rem;
        }

        .stat-card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
            transition: transform 0.2s;
        }

        .stat-card:hover { transform: translateY(-4px); }
        .stat-label { font-size: 0.85rem; color: var(--text-muted); text-transform: uppercase; tracking: 1px; }
        .stat-value { font-size: 2.2rem; font-weight: 700; margin-top: 0.5rem; }

        .main-layout {
            display: grid;
            grid-template-columns: 1fr 360px;
            gap: 2rem;
        }

        @media (max-width: 900px) { .main-layout { grid-template-columns: 1fr; } }

        .card {
            background: var(--card-bg);
            border: 1px solid var(--card-border);
            border-radius: 16px;
            padding: 1.5rem;
            backdrop-filter: blur(12px);
        }

        .card-header {
            display: flex; justify-content: space-between; align-items: center;
            margin-bottom: 1.2rem;
        }
        .card-title { font-size: 1.2rem; font-weight: 600; }

        .feed-container {
            font-family: 'JetBrains Mono', monospace;
            background: rgba(0, 0, 0, 0.4);
            border: 1px solid rgba(255, 255, 255, 0.05);
            border-radius: 12px;
            height: 480px;
            overflow-y: auto;
            padding: 1rem;
            font-size: 0.88rem;
            display: flex;
            flex-direction: column;
            gap: 0.6rem;
        }

        .log-entry {
            line-height: 1.5;
            padding: 0.4rem 0.6rem;
            border-radius: 6px;
            background: rgba(255, 255, 255, 0.02);
            word-break: break-all;
        }

        .log-time { color: var(--text-muted); font-size: 0.78rem; margin-right: 0.6rem; }
        .log-info { color: #38bdf8; }
        .log-success { color: #4ade80; font-weight: 600; }
        .log-warn { color: #fbbf24; }
        .log-err { color: #f87171; }

        .form-group { margin-bottom: 1rem; }
        .form-group label { display: block; font-size: 0.85rem; margin-bottom: 0.4rem; color: var(--text-muted); }
        .form-control {
            width: 100%;
            padding: 0.75rem 1rem;
            background: rgba(0, 0, 0, 0.3);
            border: 1px solid var(--card-border);
            border-radius: 10px;
            color: var(--text-main);
            font-family: inherit;
            font-size: 0.95rem;
        }
        .form-control:focus { outline: none; border-color: var(--primary); }

        .btn {
            width: 100%;
            padding: 0.8rem 1.2rem;
            border-radius: 10px;
            border: none;
            font-weight: 600;
            font-size: 0.95rem;
            cursor: pointer;
            transition: all 0.2s;
            margin-top: 0.5rem;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--primary), #4f46e5);
            color: #fff;
            box-shadow: 0 4px 14px var(--primary-glow);
        }

        .btn-primary:hover { opacity: 0.9; transform: translateY(-1px); }

        .btn-danger {
            background: linear-gradient(135deg, #ef4444, #dc2626);
            color: #fff;
        }
    </style>
</head>
<body>
    <div class="container">
        <header>
            <div class="title-box">
                <div class="logo">W</div>
                <div>
                    <h2>Wikidata Bot Dashboard</h2>
                    <p style="font-size: 0.85rem; color: var(--text-muted);">Live Monitoring & Real-time Edit Feed (Bengali 'bn' & Hindi 'hi')</p>
                </div>
            </div>
            <div class="status-pill">
                <div class="dot" id="statusDot"></div>
                <span id="statusText">LOADING...</span>
            </div>
        </header>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-label">Total Processed</div>
                <div class="stat-value" id="valProcessed">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Live Updates Submitted</div>
                <div class="stat-value" id="valUpdated" style="color: #4ade80;">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">Skipped (Already Present)</div>
                <div class="stat-value" id="valSkipped" style="color: #60a5fa;">0</div>
            </div>
        </div>

        <div class="main-layout">
            <div class="card">
                <div class="card-header">
                    <div class="card-title">📡 Real-Time Edit Feed</div>
                    <button class="btn btn-primary" style="width: auto; padding: 0.4rem 0.8rem; font-size: 0.8rem;" onclick="clearFeed()">Clear Feed</button>
                </div>
                <div class="feed-container" id="feedBox">
                    <div class="log-entry"><span class="log-time">[System]</span> Initializing live dashboard connection...</div>
                </div>
            </div>

            <div class="card">
                <div class="card-header">
                    <div class="card-title">⚡ Add Item to Live Queue</div>
                </div>
                <form id="addForm" onsubmit="submitItem(event)">
                    <div class="form-group">
                        <label>Wikidata QID</label>
                        <input type="text" id="inputQid" class="form-control" placeholder="e.g. Q42" required>
                    </div>
                    <div class="form-group">
                        <label>Bengali Label ('bn')</label>
                        <input type="text" id="labelBn" class="form-control" placeholder="ডগলাস অ্যাডামস">
                    </div>
                    <div class="form-group">
                        <label>Hindi Label ('hi')</label>
                        <input type="text" id="labelHi" class="form-control" placeholder="डगलस एडम्स">
                    </div>
                    <div class="form-group">
                        <label>Bengali Description ('bn')</label>
                        <input type="text" id="descBn" class="form-control" placeholder="ইংরেজি লেখক এবং কৌতুক অভিনেতা">
                    </div>
                    <div class="form-group">
                        <label>Hindi Description ('hi')</label>
                        <input type="text" id="descHi" class="form-control" placeholder="अंग्रेजी लेखक और हास्य अभिनेता">
                    </div>
                    <button type="submit" class="btn btn-primary">Add Item & Process Live</button>
                </form>
            </div>
        </div>
    </div>

    <script>
        function updateDashboard() {
            fetch('/api/status')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('valProcessed').innerText = data.total_processed;
                    document.getElementById('valUpdated').innerText = data.total_updated;
                    document.getElementById('valSkipped').innerText = data.total_skipped;

                    const dot = document.getElementById('statusDot');
                    const txt = document.getElementById('statusText');
                    
                    if (data.status === 'RUNNING') {
                        dot.className = 'dot running';
                        txt.innerText = 'BOT LIVE & RUNNING';
                        txt.style.color = '#10b981';
                    } else {
                        dot.className = 'dot stopped';
                        txt.innerText = 'BOT IDLE / WAITING';
                        txt.style.color = '#ef4444';
                    }
                });

            fetch('/api/logs')
                .then(r => r.json())
                .then(logs => {
                    const box = document.getElementById('feedBox');
                    box.innerHTML = '';
                    logs.forEach(line => {
                        const div = document.createElement('div');
                        div.className = 'log-entry';
                        if (line.includes('SUCCESS:')) {
                            div.innerHTML = `<span class="log-success">${escapeHtml(line)}</span>`;
                        } else if (line.includes('[WARNING]') || line.includes('Maxlag')) {
                            div.innerHTML = `<span class="log-warn">${escapeHtml(line)}</span>`;
                        } else if (line.includes('[Error]') || line.includes('FAILED')) {
                            div.innerHTML = `<span class="log-err">${escapeHtml(line)}</span>`;
                        } else {
                            div.innerHTML = `<span class="log-info">${escapeHtml(line)}</span>`;
                        }
                        box.appendChild(div);
                    });
                    box.scrollTop = box.scrollHeight;
                });
        }

        function escapeHtml(text) {
            return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
        }

        function clearFeed() {
            document.getElementById('feedBox').innerHTML = '';
        }

        function submitItem(e) {
            e.preventDefault();
            const payload = {
                qid: document.getElementById('inputQid').value,
                labels: {
                    bn: document.getElementById('labelBn').value,
                    hi: document.getElementById('labelHi').value
                },
                descriptions: {
                    bn: document.getElementById('descBn').value,
                    hi: document.getElementById('descHi').value
                }
            };

            fetch('/api/add_item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            }).then(r => r.json()).then(res => {
                alert('Item submitted to bot live queue!');
                document.getElementById('addForm').reset();
                updateDashboard();
            });
        }

        setInterval(updateDashboard, 2000);
        updateDashboard();
    </script>
</body>
</html>
"""

class DashboardRequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/" or parsed.path == "/index.html":
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(HTML_TEMPLATE.encode("utf-8"))

        elif parsed.path == "/api/status":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            # Read state from log/processed files
            log_path = Path("bot_execution.log")
            log_text = log_path.read_text(encoding="utf-8", errors="replace") if log_path.exists() else ""
            
            updated_count = log_text.count("SUCCESS:")
            skipped_count = log_text.count("Skipped") + log_text.count("already exists")
            processed_count = updated_count + skipped_count

            status = "RUNNING" if BOT_PROCESS and BOT_PROCESS.poll() is None else "IDLE"

            data = {
                "status": status,
                "total_processed": processed_count,
                "total_updated": updated_count,
                "total_skipped": skipped_count
            }
            self.wfile.write(json.dumps(data).encode("utf-8"))

        elif parsed.path == "/api/logs":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            
            log_path = Path("bot_execution.log")
            lines = []
            if log_path.exists():
                all_lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
                lines = all_lines[-60:]  # Return recent 60 lines
            
            self.wfile.write(json.dumps(lines).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/add_item":
            content_len = int(self.headers.get("Content-Length", 0))
            post_data = self.rfile.read(content_len).decode("utf-8")
            try:
                item_data = json.loads(post_data)
                temp_file = Path("live_feed_items.json")
                existing = []
                if temp_file.exists():
                    try:
                        existing = json.loads(temp_file.read_text(encoding="utf-8"))
                    except Exception:
                        existing = []
                existing.append(item_data)
                temp_file.write_text(json.dumps(existing, indent=2, ensure_ascii=False), encoding="utf-8")

                # Launch bot on live_feed_items.json
                global BOT_PROCESS
                python_bin = sys.executable
                BOT_PROCESS = subprocess.Popen([python_bin, "bot.py", "live_feed_items.json"], cwd=str(Path.cwd()))

                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps({"status": "success", "message": "Item added"}).encode("utf-8"))
            except Exception as e:
                self.send_response(500)
                self.end_headers()
                self.wfile.write(json.dumps({"error": str(e)}).encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def main():
    server = HTTPServer((HOST, PORT), DashboardRequestHandler)
    print("==========================================================")
    print(f"🚀 Wikidata Bot Dashboard Live at: http://{HOST}:{PORT}")
    print("==========================================================")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down Dashboard...")
        server.server_close()

if __name__ == "__main__":
    main()
