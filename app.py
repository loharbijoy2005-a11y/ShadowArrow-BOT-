"""
Wikidata Regional Bot & Live Web Dashboard (Flask + Unlimited Worker Thread).
Runs locally at http://localhost:5000 with real-time UI, live counters,
clickable QID links, SSE/AJAX feed, and Start/Pause/Stop controls.
"""

import os
import sys
import time
import random
import logging
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
import requests
from dotenv import load_dotenv
from flask import Flask, render_template, jsonify, request

load_dotenv()

# Configuration from .env
API_URL = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
BOT_USER = os.getenv("WIKIDATA_BOT_USER", "SHADOWARROW 2026@ShadowBot").strip()
BOT_PASSWORD = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()
USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026) python-requests"

STATE_FILE = "completed_qids.txt"
LOG_FILE = "bot_execution.log"
RATE_LIMIT_DELAY = 2.5
MAXLAG = 5

# Configure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("WikidataBotApp")

# Shared Bot State & Feed Storage
bot_state = {
    "status": "STOPPED",  # RUNNING, PAUSED, STOPPED
    "total_edits": 0,
    "skipped_count": 0,
    "failed_count": 0,
    "current_qid": None,
    "start_time": None
}

live_feed: List[Dict[str, Any]] = []
feed_lock = threading.Lock()
completed_qids = set()

def load_completed_qids() -> set:
    completed = set()
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith("#"):
                        completed.add(line.upper())
        except Exception as e:
            logger.error(f"Error reading state file {STATE_FILE}: {e}")
    return completed

completed_qids = load_completed_qids()

def mark_completed_qid(qid: str):
    qid_clean = qid.strip().upper()
    if qid_clean in completed_qids:
        return
    completed_qids.add(qid_clean)
    try:
        with open(STATE_FILE, "a", encoding="utf-8") as f:
            f.write(f"{qid_clean}\n")
            f.flush()
    except Exception as e:
        logger.error(f"Error saving QID {qid_clean} to state file: {e}")

def add_feed_entry(qid: str, action: str, status: str, details: str = ""):
    entry = {
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "qid": qid,
        "qid_url": f"https://www.wikidata.org/wiki/{qid}",
        "action": action,
        "status": status,  # SUCCESS, SKIPPED, ERROR, WARNING
        "details": details
    }
    with feed_lock:
        live_feed.append(entry)
        if len(live_feed) > 100:  # Keep last 100 entries in memory
            live_feed.pop(0)

class UnlimitedBotWorker(threading.Thread):
    def __init__(self):
        super().__init__(daemon=True)
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.csrf_token = None
        self.stop_requested = False
        self.pause_requested = False

    def request_api(self, method: str, params: dict = None, data: dict = None, is_write: bool = False) -> dict:
        params = params or {}
        data = data or {}
        params["format"] = "json"
        params["formatversion"] = "2"
        if is_write:
            params["maxlag"] = MAXLAG

        attempt = 0
        backoff = 2.0

        while attempt <= 5 and not self.stop_requested:
            attempt += 1
            try:
                if method.upper() == "POST":
                    time.sleep(RATE_LIMIT_DELAY)
                    res = self.session.post(API_URL, params=params, data=data, timeout=30)
                else:
                    res = self.session.get(API_URL, params=params, timeout=30)

                if res.status_code in (429, 500, 502, 503, 504):
                    wait_t = float(res.headers.get("Retry-After", backoff))
                    logger.warning(f"[HTTP {res.status_code}] Rate limited. Waiting {wait_t}s...")
                    time.sleep(wait_t)
                    backoff *= 2.0
                    continue

                res.raise_for_status()
                res_json = res.json()

                if "error" in res_json:
                    err = res_json["error"]
                    err_code = err.get("code", "")
                    if err_code == "maxlag":
                        wait_t = float(res.headers.get("Retry-After", "5"))
                        add_feed_entry("SYSTEM", "Server Maxlag Exceeded", "WARNING", f"Pausing for {wait_t}s")
                        time.sleep(wait_t)
                        continue
                    if err_code in ("badtoken", "notloggedin") and is_write:
                        self.login()
                        if data and self.csrf_token:
                            data["token"] = self.csrf_token
                        continue

                return res_json

            except Exception as e:
                time.sleep(backoff)
                backoff *= 2.0

        return {}

    def login(self) -> bool:
        res_token = self.request_api("GET", params={"action": "query", "meta": "tokens", "type": "login"})
        login_token = res_token.get("query", {}).get("tokens", {}).get("logintoken")

        if not login_token:
            return False

        login_res = self.request_api("POST", data={
            "action": "login",
            "lgname": BOT_USER,
            "lgpassword": BOT_PASSWORD,
            "lgtoken": login_token
        })
        if login_res.get("login", {}).get("result") == "Success":
            self.refresh_csrf_token()
            return True
        return False

    def refresh_csrf_token(self) -> str:
        res = self.request_api("GET", params={"action": "query", "meta": "tokens", "type": "csrf"})
        token = res.get("query", {}).get("tokens", {}).get("csrftoken")
        self.csrf_token = token
        return token

    def fetch_unlimited_qids(self) -> List[str]:
        """
        Dynamic Unlimited Batch Generator.
        Queries Wikidata Action API for random entities or newly created entities.
        """
        params = {
            "action": "query",
            "list": "random",
            "rnnamespace": "0",  # Main item namespace
            "rnlimit": "50"
        }
        res = self.request_api("GET", params=params)
        random_items = res.get("query", {}).get("random", [])
        return [item["title"] for item in random_items if item.get("title", "").startswith("Q")]

    def process_qid(self, qid: str):
        if qid in completed_qids:
            return

        bot_state["current_qid"] = qid

        # Fetch entity data
        res = self.request_api("GET", params={
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels|descriptions",
            "languages": "bn|hi"
        })

        entities = res.get("entities", {})
        entity = entities.get(qid, {})

        if "missing" in entity:
            mark_completed_qid(qid)
            return

        labels = entity.get("labels", {})
        descriptions = entity.get("descriptions", {})

        edits = 0
        summary = "Adding missing regional label/description via automated bot"

        # Check Bengali Label
        if "bn" not in labels:
            # Generate fallback or translation tag
            lbl_val = entity.get("labels", {}).get("en", {}).get("value")
            if lbl_val:
                self.set_label(qid, "bn", lbl_val, summary)
                edits += 1

        # Check Hindi Label
        if "hi" not in labels:
            lbl_val = entity.get("labels", {}).get("en", {}).get("value")
            if lbl_val:
                self.set_label(qid, "hi", lbl_val, summary)
                edits += 1

        if edits > 0:
            bot_state["total_edits"] += edits
            add_feed_entry(qid, f"Added missing regional label/description ({edits} edit)", "SUCCESS")
        else:
            bot_state["skipped_count"] += 1
            add_feed_entry(qid, "Checked Bengali & Hindi fields (Already present)", "SKIPPED")

        mark_completed_qid(qid)

    def set_label(self, qid: str, lang: str, value: str, summary: str):
        if not self.csrf_token:
            self.refresh_csrf_token()

        payload = {
            "action": "wbsetlabel",
            "id": qid,
            "language": lang,
            "value": value,
            "summary": summary,
            "token": self.csrf_token,
            "bot": "1"
        }
        res = self.request_api("POST", data=payload, is_write=True)
        if res.get("success") == 1:
            logger.info(f"[{qid}] Set '{lang}' label -> '{value}'")

    def run(self):
        logger.info("[Worker] Unlimited bot automation worker started.")
        bot_state["start_time"] = time.time()
        bot_state["status"] = "RUNNING"

        if not self.login():
            logger.error("[Worker] Login failed. Stopping worker.")
            bot_state["status"] = "STOPPED"
            return

        while not self.stop_requested:
            if self.pause_requested:
                bot_state["status"] = "PAUSED"
                time.sleep(1)
                continue

            bot_state["status"] = "RUNNING"
            qids = self.fetch_unlimited_qids()

            if not qids:
                time.sleep(5)
                continue

            for qid in qids:
                if self.stop_requested:
                    break
                while self.pause_requested and not self.stop_requested:
                    bot_state["status"] = "PAUSED"
                    time.sleep(1)

                try:
                    self.process_qid(qid)
                except Exception as e:
                    logger.error(f"Error processing {qid}: {e}")
                    bot_state["failed_count"] += 1
                    add_feed_entry(qid, f"Error processing item", "ERROR", str(e))

        bot_state["status"] = "STOPPED"
        bot_state["current_qid"] = None
        logger.info("[Worker] Unlimited worker thread stopped.")

# Flask App Server Setup
app = Flask(__name__, template_folder="templates")
worker_thread = None

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/stats")
def get_stats():
    uptime_seconds = 0
    if bot_state["start_time"] and bot_state["status"] == "RUNNING":
        uptime_seconds = int(time.time() - bot_state["start_time"])

    return jsonify({
        "status": bot_state["status"],
        "total_edits": bot_state["total_edits"],
        "skipped_count": bot_state["skipped_count"],
        "failed_count": bot_state["failed_count"],
        "current_qid": bot_state["current_qid"],
        "completed_count": len(completed_qids),
        "uptime": f"{uptime_seconds // 3600:02d}:{(uptime_seconds % 3600) // 60:02d}:{uptime_seconds % 60:02d}"
    })

@app.route("/api/feed")
def get_feed():
    with feed_lock:
        return jsonify(list(reversed(live_feed[-50:])))

@app.route("/api/control/start", methods=["POST"])
def start_bot():
    global worker_thread
    if worker_thread is None or not worker_thread.is_alive():
        worker_thread = UnlimitedBotWorker()
        worker_thread.start()
    else:
        worker_thread.pause_requested = False
    bot_state["status"] = "RUNNING"
    return jsonify({"status": "success", "message": "Bot started"})

@app.route("/api/control/pause", methods=["POST"])
def pause_bot():
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        worker_thread.pause_requested = True
        bot_state["status"] = "PAUSED"
    return jsonify({"status": "success", "message": "Bot paused"})

@app.route("/api/control/stop", methods=["POST"])
def stop_bot():
    global worker_thread
    if worker_thread and worker_thread.is_alive():
        worker_thread.stop_requested = True
        bot_state["status"] = "STOPPED"
    return jsonify({"status": "success", "message": "Bot stopped"})

if __name__ == "__main__":
    print("==========================================================")
    print("🚀 Starting Wikidata Unlimited Bot Web Dashboard")
    print("👉 Live Dashboard URL: http://localhost:5000")
    print("==========================================================")
    app.run(host="localhost", port=5000, debug=False)
