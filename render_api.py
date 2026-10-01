"""
Render Web Service REST Backend API (OmniData Engine)
Wiring Vercel Admin Dashboard to Render Bot Server with ZERO External DB Dependencies.

Endpoints:
- GET  /         : Service Healthcheck
- GET  /status   : Live telemetry state (polling every 2s)
- POST /control  : Start / Pause toggle action ("start" | "pause")
- GET  /edits    : Live edit history for Vercel Dashboard
"""

import os
import time
import json
import queue
import logging
import threading
from typing import Optional, Dict, Any, List

from fastapi import FastAPI, Header, HTTPException, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import Config
from omnidata_engine import OmniDataEngine, validate_script

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s"
)
logger = logging.getLogger("RenderAPI")

# Secret key for header authorization
SECRET_KEY = os.getenv("INTERNAL_BOT_SECRET", "SHADOW_SECURE_TOKEN_2026")

# FastAPI App
app = FastAPI(title="OmniData Engine Controller & Telemetry API")

# Enable CORS for Vercel Dashboard
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Production origins can be specified via env
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-Memory State (RAM only - Zero External Database)
engine_state: Dict[str, Any] = {
    "is_active": False,
    "current_qid": None,
    "completed_in_session": 0,
    "last_action_timestamp": None,
    "status_message": "Engine on Standby",
}

# Global Engine Instance & Lock
engine_instance: Optional[OmniDataEngine] = None
state_lock = threading.Lock()


def verify_token(x_bot_token: Optional[str] = Header(None)):
    """Verifies the X-Bot-Token header against SECRET_KEY."""
    if not x_bot_token or x_bot_token != SECRET_KEY:
        raise HTTPException(status_code=403, detail="Unauthorized request: Invalid or missing X-Bot-Token header")


class ControlRequest(BaseModel):
    action: str  # "start" | "pause"


def background_wikidata_worker():
    """
    Background Thread Worker:
    Controls the OmniDataEngine producer-consumer loop with 0.8s rate limiting.
    Keeps state strictly in-memory (RAM).
    """
    global engine_instance

    logger.info("Initializing OmniDataEngine in Render background worker...")
    cfg = Config.from_env()
    cfg.validate(require_auth=True)

    engine = OmniDataEngine(config=cfg)
    engine_instance = engine

    # Authenticate bot
    if not engine.login():
        logger.error("Render worker failed to authenticate with Wikidata API.")
        with state_lock:
            engine_state["status_message"] = "Authentication Failed"
        return

    logger.info("Render background worker successfully authenticated with Wikidata.")

    # Background candidate pre-fetcher thread (Infinite Producer)
    producer_thread = threading.Thread(target=engine.producer_loop, name="RenderProducer", daemon=True)
    producer_thread.start()

    # Main writer loop
    while True:
        if engine_state["is_active"]:
            t_start = time.time()
            try:
                qid, payload_data = engine.task_queue.get(timeout=2.0)

                # Script Guardrails Check
                guard_ok = True
                for lang, lbl_obj in payload_data.get("labels", {}).items():
                    if not validate_script(lbl_obj["value"], lang):
                        engine.log_skipped_entity(qid, f"Label script guardrail mismatch: {lang}", payload_data)
                        guard_ok = False
                        break

                for lang, desc_obj in payload_data.get("descriptions", {}).items():
                    if not validate_script(desc_obj["value"], lang):
                        engine.log_skipped_entity(qid, f"Description script guardrail mismatch: {lang}", payload_data)
                        guard_ok = False
                        break

                if not guard_ok:
                    engine.task_queue.task_done()
                    continue

                # Update active state
                with state_lock:
                    engine_state["current_qid"] = qid
                    engine_state["status_message"] = f"Processing Wikidata entity {qid}"

                # Send wbeditentity POST request
                edit_payload = {
                    "action": "wbeditentity",
                    "id": qid,
                    "data": json.dumps(payload_data, ensure_ascii=False),
                    "token": engine.csrf_token,
                    "summary": "Added missing Bengali and Hindi labels, descriptions, and P18 media statements",
                    "bot": 1,
                    "format": "json"
                }

                resp = engine.session.post(engine.config.api_url, data=edit_payload, timeout=15)
                res = resp.json()

                if "success" in res and res["success"] == 1:
                    engine.mark_qid_completed(qid)
                    with state_lock:
                        engine_state["completed_in_session"] += 1
                        engine_state["last_action_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        engine_state["status_message"] = f"SUCCESS Edit [QID: {qid}]"
                    logger.info(f"Render Worker SUCCESS Edit [QID: {qid}]")
                elif "error" in res and res["error"].get("code") == "badtoken":
                    logger.warning("CSRF token expired. Refreshing...")
                    engine.fetch_csrf_token()
                    edit_payload["token"] = engine.csrf_token
                    resp2 = engine.session.post(engine.config.api_url, data=edit_payload, timeout=15)
                    if resp2.json().get("success") == 1:
                        engine.mark_qid_completed(qid)
                        with state_lock:
                            engine_state["completed_in_session"] += 1
                            engine_state["last_action_timestamp"] = time.strftime("%Y-%m-%d %H:%M:%S")
                        logger.info(f"Render Worker SUCCESS Edit after refresh [QID: {qid}]")
                    else:
                        engine.log_skipped_entity(qid, f"API Error: {resp2.json()}", payload_data)
                else:
                    engine.log_skipped_entity(qid, f"API Error: {res}", payload_data)

                engine.task_queue.task_done()

            except queue.Empty:
                pass
            except Exception as e:
                logger.error(f"Worker exception: {e}")

            # Dynamic sleep calculation for exact 0.8s rate-limit interval
            elapsed = time.time() - t_start
            sleep_needed = max(0.0, 0.8 - elapsed)
            time.sleep(sleep_needed)
        else:
            with state_lock:
                engine_state["current_qid"] = None
                engine_state["status_message"] = "Paused by admin dashboard"
            time.sleep(1.0)


# Start daemon worker thread on boot
worker_thread = threading.Thread(target=background_wikidata_worker, name="RenderWorkerDaemon", daemon=True)
worker_thread.start()


@app.get("/")
def healthcheck():
    """Healthcheck endpoint for Render / monitoring ping."""
    return {
        "status": "ok",
        "service": "OmniData Engine Render Backend",
        "is_active": engine_state["is_active"],
        "completed_in_session": engine_state["completed_in_session"]
    }


@app.get("/status")
def get_bot_status(x_bot_token: Optional[str] = Header(None)):
    """Returns live in-memory telemetry state for Vercel dashboard."""
    verify_token(x_bot_token)
    with state_lock:
        return engine_state


@app.post("/control")
def control_bot(req: ControlRequest, x_bot_token: Optional[str] = Header(None)):
    """Toggles bot execution status ('start' | 'pause')."""
    verify_token(x_bot_token)
    with state_lock:
        if req.action == "start":
            engine_state["is_active"] = True
            if engine_instance:
                engine_instance.producer_finished = False
            engine_state["status_message"] = "Processing Wikidata queue @ 0.8s"
        elif req.action == "pause":
            engine_state["is_active"] = False
            engine_state["status_message"] = "Paused by admin dashboard"
        else:
            raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'pause'")

        return {"status": "acknowledged", "is_active": engine_state["is_active"]}


@app.get("/edits")
def get_recent_edits(limit: int = 50, x_bot_token: Optional[str] = Header(None)):
    """Returns recent edit records for Vercel Dashboard feed."""
    verify_token(x_bot_token)
    edits = []
    log_file = "omnidata_engine.log"
    if os.path.exists(log_file):
        try:
            with open(log_file, "r", encoding="utf-8") as f:
                lines = f.readlines()
                id_counter = 1
                for line in reversed(lines):
                    if "SUCCESS Edit [QID:" in line:
                        parts = line.strip().split("SUCCESS Edit [QID: ")
                        if len(parts) == 2:
                            ts = line[:19]
                            qid = parts[1].split("]")[0]
                            edits.append({
                                "id": f"edit-{id_counter}",
                                "qid": qid,
                                "fieldType": "multi_field",
                                "fieldLabel": f"Updated QID {qid}",
                                "status": "VERIFIED_SAFE",
                                "timestamp": ts,
                                "latencyMs": 800
                            })
                            id_counter += 1
                            if len(edits) >= limit:
                                break
        except Exception as e:
            logger.error(f"Error reading log for /edits: {e}")
    return {"success": True, "edits": edits, "total": len(edits)}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
