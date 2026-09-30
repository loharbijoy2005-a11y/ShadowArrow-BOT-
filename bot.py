"""
High-Speed Production Wikidata Automation Engine (bot.py)
Designed for local execution and 24/7 Render background worker deployment.

Architectural Rules:
1. NO LABELS: Only edits localized descriptions. Never touches labels.
2. Unicode Script Guardrails: Validates Bengali (\\u0980-\\u09FF) and Devanagari (\\u0900-\\u097F) scripts before write.
3. Accurate State Localization: Parses English description, maps Indian State/UT, generates natural phrasing.
4. One-Time CSRF Session Token & Batch Fetching (50 QIDs).
5. Single Atomic POST Edit (`action=wbeditentity`) throttled at 1.8 seconds.
6. Persistent Resumability (`completed_qids.txt`).
"""

import os
import re
import sys
import time
import json
import random
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import requests
from dotenv import load_dotenv

load_dotenv()

# Environment Credentials & Configuration
API_URL = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
SPARQL_URL = "https://query.wikidata.org/sparql"
BOT_USER = os.getenv("WIKIDATA_BOT_USER", "SHADOWARROW 2026@ShadowBot").strip()
BOT_PASSWORD = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()

USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026) python-requests"
STATE_FILE = "completed_qids.txt"
LOG_FILE = "bot_execution.log"

RATE_LIMIT_DELAY = 1.8  # Strict 1.8s delay between write calls
MAXLAG = 5
MAX_RETRIES = 5
BATCH_FETCH_SIZE = 50

EDIT_SUMMARY = "Added missing Hindi and Bengali descriptions for Indian localities"

# Unicode Script Regex Validators (Hard Guardrails)
BENGALI_SCRIPT_REGEX = re.compile(r'[\u0980-\u09FF]')
DEVANAGARI_SCRIPT_REGEX = re.compile(r'[\u0900-\u097F]')

# Configure UTF-8 Logging
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("WikidataBot")

# Comprehensive Indian State & Union Territory Dictionary
INDIAN_STATES = {
    "Andhra Pradesh": {"hi": "आंध्र प्रदेश", "bn": "অন্ধ্রপ্রদেশ"},
    "Arunachal Pradesh": {"hi": "अरुणाचल प्रदेश", "bn": "অরুণাচল প্রদেশ"},
    "Assam": {"hi": "असम", "bn": "অসম"},
    "Bihar": {"hi": "बिहार", "bn": "বিহার"},
    "Chhattisgarh": {"hi": "छत्तीसगढ़", "bn": "ছত্তিশগড়"},
    "Goa": {"hi": "गोवा", "bn": "গোয়া"},
    "Gujarat": {"hi": "गुजरात", "bn": "গুজরাত"},
    "Haryana": {"hi": "हरियाणा", "bn": "হরিয়ানা"},
    "Himachal Pradesh": {"hi": "हिमाचल प्रदेश", "bn": "হিমাচল প্রদেশ"},
    "Jharkhand": {"hi": "झारखंड", "bn": "ঝাড়খণ্ড"},
    "Karnataka": {"hi": "कर्नाटक", "bn": "কর্ণাটক"},
    "Kerala": {"hi": "केरल", "bn": "কেরালা"},
    "Madhya Pradesh": {"hi": "मध्य प्रदेश", "bn": "মধ্যপ্রদেশ"},
    "Maharashtra": {"hi": "महाराष्ट्र", "bn": "মহারাষ্ট্র"},
    "Manipur": {"hi": "मणिपुर", "bn": "মণিপুর"},
    "Meghalaya": {"hi": "मेघालय", "bn": "মেঘালয়"},
    "Mizoram": {"hi": "मिजोरम", "bn": "মিজোরাম"},
    "Nagaland": {"hi": "नागालैंड", "bn": "নাগাল্যান্ড"},
    "Odisha": {"hi": "ओडिशा", "bn": "ওড়িশা"},
    "Orissa": {"hi": "ओडिशा", "bn": "ওড়িশা"},
    "Punjab": {"hi": "पंजाब", "bn": "পাঞ্জাব"},
    "Rajasthan": {"hi": "राजस्थान", "bn": "রাজস্থান"},
    "Sikkim": {"hi": "सिक्किम", "bn": "সিকিম"},
    "Tamil Nadu": {"hi": "तमिलनाडु", "bn": "তামিলনাড়ু"},
    "Telangana": {"hi": "तेलंगाना", "bn": "तेलेंगाना"},
    "Tripura": {"hi": "त्रिपुरा", "bn": "ত্রিপুরা"},
    "Uttar Pradesh": {"hi": "उत्तर प्रदेश", "bn": "उत्तरप्रदेश"},
    "Uttarakhand": {"hi": "उत्तराखंड", "bn": "উত্তরাখণ্ড"},
    "West Bengal": {"hi": "पश्चिम बंगाल", "bn": "পশ্চিমবঙ্গ"},
    "Delhi": {"hi": "दिल्ली", "bn": "দিল্লি"},
    "Jammu and Kashmir": {"hi": "जम्मू और कश्मीर", "bn": "জম্মু ও কাশ্মীর"},
    "Ladakh": {"hi": "लद्दाख", "bn": "লাদাখ"},
    "Puducherry": {"hi": "पुदुचेरी", "bn": "পুদুচেরি"},
    "Chandigarh": {"hi": "चंडीगढ़", "bn": "চণ্ডীগড়"}
}

def validate_unicode_script(text: str, lang: str) -> bool:
    """Hard guardrail validating that generated text contains correct script characters."""
    if not text or not isinstance(text, str):
        return False
    if lang == "bn":
        return bool(BENGALI_SCRIPT_REGEX.search(text))
    elif lang == "hi":
        return bool(DEVANAGARI_SCRIPT_REGEX.search(text))
    return False

def parse_english_description(en_desc: str) -> Optional[Tuple[str, str]]:
    """
    Parses English description ('en') to extract entity type and state.
    Returns Tuple of (entity_type, state_name) or None.
    """
    if not en_desc or not isinstance(en_desc, str):
        return None

    desc_clean = en_desc.strip()

    patterns = [
        (r'\b(?:city|town|human settlement|municipality)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$', 'city'),
        (r'\b(?:village|gram panchayat)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$', 'village'),
        (r'\b(?:district|administrative district)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$', 'district'),
        (r'\b(?:river|watercourse|tributary)\s+(?:in|of)\s+(?:the\s+Indian\s+state\s+of\s+)?([A-Za-z\s]+?)(?:,\s*India)?$', 'river')
    ]

    for pattern, entity_type in patterns:
        match = re.search(pattern, desc_clean, re.IGNORECASE)
        if match:
            extracted_state = match.group(1).strip()
            extracted_state = re.sub(r'\s+state$', '', extracted_state, flags=re.IGNORECASE).strip()
            
            for state_key in INDIAN_STATES:
                if state_key.lower() == extracted_state.lower():
                    return entity_type, state_key

    return None

def generate_localized_descriptions(entity_type: str, state_name: str) -> Optional[Dict[str, str]]:
    """Generates localized Hindi and Bengali descriptions for state & entity type."""
    state_map = INDIAN_STATES.get(state_name)
    if not state_map:
        return None

    state_hi = state_map["hi"]
    state_bn = state_map["bn"]

    if entity_type in ('city', 'town'):
        return {
            "hi": f"भारत के {state_hi} राज्य का एक शहर",
            "bn": f"ভারতের {state_bn} রাজ্যের একটি শহর"
        }
    elif entity_type == 'village':
        return {
            "hi": f"भारत के {state_hi} राज्य का एक गाँव",
            "bn": f"ভারতের {state_bn} রাজ্যের একটি গ্রাম"
        }
    elif entity_type == 'district':
        return {
            "hi": f"भारत के {state_hi} राज्य का एक ज़िला",
            "bn": f"ভারতের {state_bn} রাজ্যের একটি জেলা"
        }
    elif entity_type == 'river':
        return {
            "hi": f"भारत के {state_hi} राज्य की एक नदी",
            "bn": f"ভারতের {state_bn} রাজ্যের একটি নদী"
        }

    return None

class WikidataAutomationEngine:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.csrf_token: Optional[str] = None
        self.completed_qids = self._load_completed_qids()

    def _load_completed_qids(self) -> set:
        completed = set()
        if os.path.exists(STATE_FILE):
            try:
                with open(STATE_FILE, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#"):
                            completed.add(line.upper())
                logger.info(f"[State] Loaded {len(completed)} completed QIDs from '{STATE_FILE}'.")
            except Exception as e:
                logger.error(f"[State] Error loading state file: {e}")
        return completed

    def _mark_completed(self, qid: str):
        qid_clean = qid.strip().upper()
        if qid_clean in self.completed_qids:
            return
        self.completed_qids.add(qid_clean)
        try:
            with open(STATE_FILE, "a", encoding="utf-8") as f:
                f.write(f"{qid_clean}\n")
                f.flush()
        except Exception as e:
            logger.error(f"[State] Failed recording QID {qid_clean}: {e}")

    def request_mediawiki(self, method: str, params: dict = None, data: dict = None, is_write: bool = False) -> dict:
        params = params or {}
        data = data or {}
        params["format"] = "json"
        params["formatversion"] = "2"
        if is_write:
            params["maxlag"] = MAXLAG

        attempt = 0
        backoff = 2.0

        while attempt <= MAX_RETRIES:
            attempt += 1
            try:
                if method.upper() == "POST":
                    time.sleep(RATE_LIMIT_DELAY)
                    res = self.session.post(API_URL, params=params, data=data, timeout=30)
                else:
                    res = self.session.get(API_URL, params=params, timeout=30)

                if res.status_code in (429, 500, 502, 503, 504):
                    wait_t = float(res.headers.get("Retry-After", backoff))
                    logger.warning(f"[HTTP {res.status_code}] Rate limited. Backing off for {wait_t:.2f}s...")
                    time.sleep(wait_t)
                    backoff *= 2.0
                    continue

                res.raise_for_status()
                res_json = res.json()

                if "error" in res_json:
                    err = res_json["error"]
                    err_code = err.get("code", "")
                    err_info = err.get("info", "")

                    if err_code == "maxlag":
                        wait_t = float(res.headers.get("Retry-After", "5"))
                        logger.warning(f"[MediaWiki Maxlag] Server lag ({err_info}). Pausing for {wait_t}s...")
                        time.sleep(wait_t)
                        continue

                    if err_code in ("badtoken", "notloggedin") and is_write and attempt < MAX_RETRIES:
                        logger.warning(f"[Auth] CSRF token invalid/expired ({err_code}). Re-authenticating...")
                        self.login()
                        if data and self.csrf_token:
                            data["token"] = self.csrf_token
                        continue

                return res_json

            except Exception as e:
                wait_t = backoff + random.uniform(0.5, 1.5)
                logger.warning(f"[Network Error] {e}. Retrying in {wait_t:.2f}s...")
                time.sleep(wait_t)
                backoff *= 2.0

        return {}

    def login(self) -> bool:
        """Performs 2-Stage MediaWiki Authentication and stores CSRF token ONCE for session reuse."""
        logger.info(f"[Auth] Authenticating as bot user: '{BOT_USER}'...")
        res_token = self.request_mediawiki("GET", params={"action": "query", "meta": "tokens", "type": "login"})
        login_token = res_token.get("query", {}).get("tokens", {}).get("logintoken")

        if not login_token:
            raise RuntimeError("Failed to obtain logintoken.")

        login_res = self.request_mediawiki("POST", data={
            "action": "login",
            "lgname": BOT_USER,
            "lgpassword": BOT_PASSWORD,
            "lgtoken": login_token
        })
        if login_res.get("login", {}).get("result") != "Success":
            raise RuntimeError(f"Login failed: {login_res}")

        logger.info("[Auth] Successfully authenticated with MediaWiki Action API.")
        self.refresh_csrf_token()
        return True

    def refresh_csrf_token(self) -> str:
        """Fetches one-time CSRF token for write operations."""
        logger.debug("[Auth] Fetching session CSRF token...")
        res = self.request_mediawiki("GET", params={"action": "query", "meta": "tokens", "type": "csrf"})
        token = res.get("query", {}).get("tokens", {}).get("csrftoken")
        
        if not token or token == "+\\":
            raise RuntimeError("Obtained invalid CSRF token.")

        self.csrf_token = token
        logger.debug("[Auth] Session CSRF token stored.")
        return token

    def fetch_sparql_batch(self) -> List[str]:
        """Queries SPARQL Query Service with automatic MediaWiki API random generator fallback."""
        queries = [
            """
            SELECT ?item WHERE {
              ?item wdt:P31 wd:Q515 . # City
              ?item wdt:P17 wd:Q668 . # India
              FILTER NOT EXISTS { ?item schema:description ?bnDesc . FILTER(LANG(?bnDesc) = "bn") }
            } LIMIT 200
            """,
            """
            SELECT ?item WHERE {
              ?item wdt:P31 wd:Q4022 . # River
              ?item wdt:P17 wd:Q668 .  # India
              FILTER NOT EXISTS { ?item schema:description ?bnDesc . FILTER(LANG(?bnDesc) = "bn") }
            } LIMIT 200
            """
        ]

        selected_query = random.choice(queries)

        try:
            res = requests.get(SPARQL_URL, params={"query": selected_query, "format": "json"}, headers={"User-Agent": USER_AGENT}, timeout=10)
            if res.status_code == 200:
                bindings = res.json().get("results", {}).get("bindings", [])
                qids = []
                for b in bindings:
                    uri = b.get("item", {}).get("value", "")
                    if "/entity/" in uri:
                        qids.append(uri.split("/entity/")[-1])
                if qids:
                    return qids
        except Exception as e:
            logger.warning(f"[SPARQL Lag] {e}. Switching to MediaWiki Action API generator...")

        # Fallback Generator: Query MediaWiki Action API directly for random mainspace QIDs
        res = self.request_mediawiki("GET", params={
            "action": "query",
            "list": "random",
            "rnnamespace": "0",
            "rnlimit": "50"
        })
        random_items = res.get("query", {}).get("random", [])
        return [item["title"] for item in random_items if item.get("title", "").startswith("Q")]

    def fetch_entities_batch(self, qids_chunk: List[str]) -> Dict[str, Any]:
        """Fetches up to 50 QIDs in a SINGLE HTTP GET query using action=wbgetentities."""
        if not qids_chunk:
            return {}

        params = {
            "action": "wbgetentities",
            "ids": "|".join(qids_chunk[:BATCH_FETCH_SIZE]),
            "props": "descriptions",
            "languages": "en|bn|hi"
        }
        res = self.request_mediawiki("GET", params=params)
        return res.get("entities", {})

    def process_item_atomic(self, qid: str, entity_data: dict) -> bool:
        """
        Idempotency Check & Atomic Update (`action=wbeditentity`).
        Strictly edits ONLY localized descriptions. NO LABELS ARE EVER TOUCHED.
        """
        if qid in self.completed_qids:
            return False

        if "missing" in entity_data:
            self._mark_completed(qid)
            return False

        descriptions = entity_data.get("descriptions", {})
        en_desc_obj = descriptions.get("en", {})
        en_desc = en_desc_obj.get("value", "").strip() if isinstance(en_desc_obj, dict) else ""

        if not en_desc:
            self._mark_completed(qid)
            return False

        parsed = parse_english_description(en_desc)
        if not parsed:
            self._mark_completed(qid)
            return False

        entity_type, state_name = parsed
        localized_descs = generate_localized_descriptions(entity_type, state_name)

        if not localized_descs:
            self._mark_completed(qid)
            return False

        # Prepare Descriptions-Only Atomic Data Payload (NO LABELS)
        edit_payload_descriptions = {}
        fields_updated = []

        # 1. Bengali Description Check
        if "bn" not in descriptions and "bn" in localized_descs:
            bn_val = localized_descs["bn"]
            if validate_unicode_script(bn_val, "bn"):
                edit_payload_descriptions["bn"] = {"language": "bn", "value": bn_val}
                fields_updated.append("bn_desc")

        # 2. Hindi Description Check
        if "hi" not in descriptions and "hi" in localized_descs:
            hi_val = localized_descs["hi"]
            if validate_unicode_script(hi_val, "hi"):
                edit_payload_descriptions["hi"] = {"language": "hi", "value": hi_val}
                fields_updated.append("hi_desc")

        if not edit_payload_descriptions:
            self._mark_completed(qid)
            return False

        atomic_payload = {"descriptions": edit_payload_descriptions}

        # Execute Single Atomic POST Edit via action=wbeditentity
        if not self.csrf_token:
            self.refresh_csrf_token()

        start_time = time.time()
        post_data = {
            "action": "wbeditentity",
            "id": qid,
            "data": json.dumps(atomic_payload, ensure_ascii=False),
            "summary": EDIT_SUMMARY,
            "token": self.csrf_token,
            "bot": "1"
        }

        res = self.request_mediawiki("POST", data=post_data, is_write=True)
        latency = time.time() - start_time

        if res.get("success") == 1:
            fields_str = "+".join(fields_updated)
            logger.info(f"QID: {qid} | Action: Updated {fields_str} | Latency: {latency:.2f}s | Status: OK")
            self._mark_completed(qid)
            return True
        else:
            logger.error(f"QID: {qid} | Action: Failed atomic edit | Latency: {latency:.2f}s | Response: {res}")
            return False

def main():
    logger.info("==========================================================")
    logger.info(" Starting Wikidata Production Automation Engine (bot.py) ")
    logger.info(" Mode: Descriptions-Only | Batch: 50 | Delay: 1.8s ")
    logger.info("==========================================================")

    bot = WikidataAutomationEngine()

    try:
        bot.login()
    except Exception as e:
        logger.critical(f"[Fatal] Authentication failed: {e}")
        sys.exit(1)

    # 24/7 Continuous Execution Pipeline
    while True:
        qids = bot.fetch_sparql_batch()
        pending_qids = [q for q in qids if q.upper() not in bot.completed_qids]

        if not pending_qids:
            time.sleep(5)
            continue

        # Process in batch chunks of 50 QIDs
        for i in range(0, len(pending_qids), BATCH_FETCH_SIZE):
            chunk = pending_qids[i : i + BATCH_FETCH_SIZE]
            entities_batch = bot.fetch_entities_batch(chunk)

            for qid in chunk:
                entity_data = entities_batch.get(qid, {})
                try:
                    bot.process_item_atomic(qid, entity_data)
                except KeyboardInterrupt:
                    logger.info("\n[!] Shutdown requested. Exiting cleanly.")
                    sys.exit(0)
                except Exception as e:
                    logger.error(f"QID: {qid} | Error: {e}")

if __name__ == "__main__":
    main()
