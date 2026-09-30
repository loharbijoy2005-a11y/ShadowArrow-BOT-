"""
Wikidata Automated Regional Edit Bot (Bengali 'bn' & Hindi 'hi')
Full, self-contained production implementation with rate-limiting, 
2-stage MediaWiki authentication, state persistence, and automatic resumption.
"""

import os
import sys
import time
import signal
import random
import logging
import requests
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configuration from .env with fallback defaults
API_URL = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
BOT_USER = os.getenv("WIKIDATA_BOT_USER", "SHADOWARROW 2026@ShadowBot").strip()
BOT_PASSWORD = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()

USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026; contact: wikidata-bot@local) python-requests"
STATE_FILE = "completed_qids.txt"
RATE_LIMIT_DELAY = 2.5  # Seconds between POST edit requests
MAXLAG = 5
MAX_RETRIES = 5

# Setup UTF-8 logging for Windows console compatibility
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler("bot_execution.log", encoding="utf-8")
    ]
)
logger = logging.getLogger("WikidataBot")

class WikidataBot:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.csrf_token = None
        self.completed_qids = self._load_completed_qids()
        self.running = True

        # Signal handler for graceful shutdown (Ctrl + C)
        signal.signal(signal.SIGINT, self._handle_shutdown)
        signal.signal(signal.SIGTERM, self._handle_shutdown)

    def _handle_shutdown(self, signum, frame):
        logger.info("\n[!] Graceful shutdown signal received. Finishing current operation and saving state...")
        self.running = False

    def _load_completed_qids(self) -> set:
        """Loads previously processed QIDs from local state file for resumability."""
        completed = set()
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            completed.add(line.upper())
                logger.info(f"[State] Loaded {len(completed)} previously completed QIDs from '{STATE_FILE}'.")
            except Exception as e:
                logger.error(f"[State] Error loading state file: {e}")
        return completed

    def _mark_completed(self, qid: str):
        """Immediately records completed QID to state file."""
        qid_clean = qid.strip().upper()
        if qid_clean in self.completed_qids:
            return
        self.completed_qids.add(qid_clean)
        try:
            with open(STATE_FILE, "a", encoding="utf-8") as f:
                f.write(f"{qid_clean}\n")
                f.flush()
        except Exception as e:
            logger.error(f"[State] Failed to record QID {qid_clean} to state file: {e}")

    def _request_with_retry(self, method: str, params: dict = None, data: dict = None, is_write: bool = False) -> dict:
        """Executes API HTTP requests with exponential backoff, maxlag checks, and rate-limiting."""
        params = params or {}
        data = data or {}

        params["format"] = "json"
        params["formatversion"] = "2"
        if is_write:
            params["maxlag"] = MAXLAG

        attempt = 0
        backoff = 2.0

        while attempt <= MAX_RETRIES:
            if not self.running:
                raise KeyboardInterrupt("Bot execution stopped by user.")

            attempt += 1
            try:
                start_t = time.time()
                if method.upper() == "POST":
                    # Enforce rate limit delay before write requests
                    time.sleep(RATE_LIMIT_DELAY)
                    response = self.session.post(API_URL, params=params, data=data, timeout=30)
                else:
                    response = self.session.get(API_URL, params=params, timeout=30)

                latency = time.time() - start_t

                # Handle HTTP Status errors (429 Too Many Requests / 5xx Server Errors)
                if response.status_code in (429, 500, 502, 503, 504):
                    retry_after = response.headers.get("Retry-After")
                    wait_time = float(retry_after) if (retry_after and retry_after.isdigit()) else (backoff + random.uniform(0.5, 1.5))
                    logger.warning(f"[HTTP {response.status_code}] Rate limited/Server busy ({latency:.2f}s). Retrying in {wait_time:.2f}s...")
                    time.sleep(wait_time)
                    backoff *= 2.0
                    continue

                response.raise_for_status()
                res_json = response.json()

                # Check MediaWiki API error structures
                if "error" in res_json:
                    err = res_json["error"]
                    err_code = err.get("code", "")
                    err_info = err.get("info", "")

                    if err_code == "maxlag":
                        retry_after = response.headers.get("Retry-After", "5")
                        wait_t = float(retry_after) if retry_after.isdigit() else 5.0
                        logger.warning(f"[MediaWiki Maxlag] Server lag exceeded ({err_info}). Pausing for {wait_t}s...")
                        time.sleep(wait_t)
                        continue

                    if err_code in ("readonly", "ratelimited"):
                        wait_t = backoff + random.uniform(1.0, 2.0)
                        logger.warning(f"[MediaWiki {err_code}] {err_info}. Retrying in {wait_t:.2f}s...")
                        time.sleep(wait_t)
                        backoff *= 2.0
                        continue

                    if err_code in ("badtoken", "notloggedin") and is_write and attempt < MAX_RETRIES:
                        logger.warning(f"[Auth] Token invalid/expired ({err_code}). Re-authenticating...")
                        self.login()
                        if data and self.csrf_token:
                            data["token"] = self.csrf_token
                        continue

                return res_json

            except (requests.RequestException, ValueError) as e:
                wait_t = backoff + random.uniform(0.5, 1.5)
                logger.warning(f"[Network Error] {e}. Retrying in {wait_t:.2f}s (Attempt {attempt}/{MAX_RETRIES})...")
                time.sleep(wait_t)
                backoff *= 2.0

        raise RuntimeError(f"Max retries ({MAX_RETRIES}) exceeded for MediaWiki API request.")

    def login(self) -> bool:
        """
        Performs 2-Stage MediaWiki Action API Authentication.
        Step 1: Request logintoken
        Step 2: POST action=login
        Step 3: Request csrftoken for edit operations
        """
        logger.info(f"[Auth] Authenticating as bot user: '{BOT_USER}'...")

        # Step 1: Request logintoken
        res_token = self._request_with_retry("GET", params={"action": "query", "meta": "tokens", "type": "login"})
        login_token = res_token.get("query", {}).get("tokens", {}).get("logintoken")

        if not login_token:
            raise RuntimeError("Failed to obtain logintoken from MediaWiki API.")

        # Step 2: POST action=login
        login_data = {
            "action": "login",
            "lgname": BOT_USER,
            "lgpassword": BOT_PASSWORD,
            "lgtoken": login_token
        }
        login_res = self._request_with_retry("POST", data=login_data)
        result = login_res.get("login", {}).get("result")

        if result != "Success":
            reason = login_res.get("login", {}).get("reason", "Unknown authentication failure")
            raise RuntimeError(f"Login failed: {result} - {reason}")

        logger.info("[Auth] Successfully logged into Wikidata MediaWiki Action API!")

        # Step 3: Fetch CSRF edit token
        self.refresh_csrf_token()
        return True

    def refresh_csrf_token(self) -> str:
        """Fetches a fresh CSRF token required for wbsetlabel and wbsetdescription edits."""
        logger.debug("[Auth] Fetching CSRF edit token...")
        res = self._request_with_retry("GET", params={"action": "query", "meta": "tokens", "type": "csrf"})
        csrf_token = res.get("query", {}).get("tokens", {}).get("csrftoken")

        if not csrf_token or csrf_token == "+\\":
            raise RuntimeError("Invalid CSRF edit token received. Check bot permissions.")

        self.csrf_token = csrf_token
        logger.debug("[Auth] CSRF edit token acquired.")
        return csrf_token

    def get_entity_data(self, qid: str) -> dict:
        """Fetches existing labels and descriptions for a Wikidata item."""
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels|descriptions",
            "languages": "bn|hi"
        }
        res = self._request_with_retry("GET", params=params)
        entities = res.get("entities", {})
        return entities.get(qid, {})

    def process_item(self, item: dict) -> bool:
        """
        Safety check & Edit execution:
        Checks if Bengali ('bn') or Hindi ('hi') labels/descriptions exist.
        Only edits if currently MISSING (idempotency check).
        """
        qid = item.get("qid", "").strip().upper()
        if not qid:
            return False

        if qid in self.completed_qids:
            logger.info(f"[{qid}] Already processed in prior session. Skipping.")
            return True

        desired_labels = item.get("labels", {})
        desired_descriptions = item.get("descriptions", {})
        summary = item.get("summary", "Adding missing regional label/description via automated bot")

        entity_data = self.get_entity_data(qid)
        if "missing" in entity_data:
            logger.warning(f"[{qid}] Item does not exist on Wikidata. Skipping.")
            self._mark_completed(qid)
            return False

        existing_labels = entity_data.get("labels", {})
        existing_descriptions = entity_data.get("descriptions", {})

        edits_made = 0

        # Process Labels (bn, hi)
        for lang in ("bn", "hi"):
            new_label = desired_labels.get(lang)
            if not new_label:
                continue

            current_label_obj = existing_labels.get(lang)
            if current_label_obj and current_label_obj.get("value", "").strip():
                logger.info(f"[{qid}] Skipped '{lang}' label: already exists ('{current_label_obj.get('value')}')")
                continue

            # Target language label missing! Set label.
            self._set_label(qid, lang, new_label.strip(), summary)
            edits_made += 1

        # Process Descriptions (bn, hi)
        for lang in ("bn", "hi"):
            new_desc = desired_descriptions.get(lang)
            if not new_desc:
                continue

            current_desc_obj = existing_descriptions.get(lang)
            if current_desc_obj and current_desc_obj.get("value", "").strip():
                logger.info(f"[{qid}] Skipped '{lang}' description: already exists ('{current_desc_obj.get('value')}')")
                continue

            # Target language description missing! Set description.
            self._set_description(qid, lang, new_desc.strip(), summary)
            edits_made += 1

        if edits_made == 0:
            logger.info(f"[{qid}] Check complete. No missing Bengali/Hindi fields to add.")

        # Mark QID as completed in state file
        self._mark_completed(qid)
        return True

    def _set_label(self, qid: str, language: str, value: str, summary: str):
        """Executes action=wbsetlabel POST request."""
        if not self.csrf_token:
            self.refresh_csrf_token()

        payload = {
            "action": "wbsetlabel",
            "id": qid,
            "language": language,
            "value": value,
            "summary": summary,
            "token": self.csrf_token,
            "bot": "1"
        }
        logger.info(f"[{qid}] Adding missing '{language}' label -> '{value}'")
        res = self._request_with_retry("POST", data=payload, is_write=True)
        if res.get("success") == 1:
            logger.info(f"[{qid}] SUCCESS: '{language}' label updated!")
        else:
            logger.error(f"[{qid}] FAILED updating '{language}' label: {res}")

    def _set_description(self, qid: str, language: str, value: str, summary: str):
        """Executes action=wbsetdescription POST request."""
        if not self.csrf_token:
            self.refresh_csrf_token()

        payload = {
            "action": "wbsetdescription",
            "id": qid,
            "language": language,
            "value": value,
            "summary": summary,
            "token": self.csrf_token,
            "bot": "1"
        }
        logger.info(f"[{qid}] Adding missing '{language}' description -> '{value}'")
        res = self._request_with_retry("POST", data=payload, is_write=True)
        if res.get("success") == 1:
            logger.info(f"[{qid}] SUCCESS: '{language}' description updated!")
        else:
            logger.error(f"[{qid}] FAILED updating '{language}' description: {res}")

def generate_target_items() -> list:
    """
    Built-in target list generator containing regional entities (cities, monuments, geography, rivers)
    with proposed Bengali ('bn') and Hindi ('hi') labels and descriptions.
    """
    return [
        {
            "qid": "Q42",
            "labels": {"bn": "ডগলাস অ্যাডামস", "hi": "डगलस एडम्स"},
            "descriptions": {"bn": "ইংরেজি লেখক এবং কৌতুক অভিনেতা", "hi": "अंग्रेजी लेखक और हास्य अभिनेता"}
        },
        {
            "qid": "Q180126",
            "labels": {"bn": "কলকাতা", "hi": "कोलकाता"},
            "descriptions": {"bn": "ভারতের পশ্চিমবঙ্গের রাজধানী", "hi": "भारत के पश्चिम बंगाल राज्य की राजधानी"}
        },
        {
            "qid": "Q1353",
            "labels": {"bn": "দিল্লি", "hi": "दिल्ली"},
            "descriptions": {"bn": "ভারতের রাজধানী অঞ্চল", "hi": "भारत की राजधानी"}
        },
        {
            "qid": "Q1156",
            "labels": {"bn": "মুম্বই", "hi": "मुंबई"},
            "descriptions": {"bn": "ভারতের মহারাষ্ট্রের রাজধানী", "hi": "भारत के महाराष्ट्र राज्य की राजधानी"}
        },
        {
            "qid": "Q1355",
            "labels": {"bn": "বেঙ্গালুরু", "hi": "बेंगलुरु"},
            "descriptions": {"bn": "ভারতের কর্ণাটকের রাজধানী", "hi": "भारत के कर्नाटक राज्य की राजधानी"}
        },
        {
            "qid": "Q1538",
            "labels": {"bn": "পুনে", "hi": "पुणे"},
            "descriptions": {"bn": "ভারতের মহারাষ্ট্রের একটি শহর", "hi": "भारत के महाराष्ट्र राज्य का एक शहर"}
        },
        {
            "qid": "Q66616",
            "labels": {"bn": "সুন্দরবন", "hi": "सुंदरवन"},
            "descriptions": {"bn": "বঙ্গোপসাগরের অববাহিকায় অবস্থিত ম্যানগ্রোভ বন", "hi": "बंगाल की खाड़ी के डेल्टा में स्थित मैन्ग्रोव वन क्षेत्र"}
        },
        {
            "qid": "Q5488",
            "labels": {"bn": "গঙ্গা নদী", "hi": "गंगा नदी"},
            "descriptions": {"bn": "ভারত ও বাংলাদেশের একটি আন্তর্জাতিক নদী", "hi": "भारत और बांग्लादेश में बहने वाली एक प्रमुख नदी"}
        }
    ]

def main():
    logger.info("==========================================================")
    logger.info(" Starting Wikidata Regional Label & Description Bot ")
    logger.info(" Target Languages: Bengali ('bn') & Hindi ('hi') ")
    logger.info("==========================================================")

    bot = WikidataBot()

    # Step 1: Login
    try:
        bot.login()
    except Exception as e:
        logger.critical(f"[Fatal] Authentication failed: {e}")
        sys.exit(1)

    # Step 2: Load Target Items Batch
    items = generate_target_items()
    logger.info(f"[Target] Total items in queue: {len(items)}")

    # Step 3: Run Continuous Execution Loop
    processed_count = 0
    for item in items:
        if not bot.running:
            break
        try:
            success = bot.process_item(item)
            if success:
                processed_count += 1
        except KeyboardInterrupt:
            logger.info("\n[!] User interrupted execution.")
            break
        except Exception as e:
            logger.error(f"[Error] Unexpected error processing {item.get('qid')}: {e}")

    logger.info("==========================================================")
    logger.info(f" Run Finished. Total QIDs processed in session: {processed_count}")
    logger.info(f" Saved state: {len(bot.completed_qids)} QIDs logged in '{STATE_FILE}'.")
    logger.info("==========================================================")

if __name__ == "__main__":
    main()
