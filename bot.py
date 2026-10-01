import os
import re
import sys
import time
import json
import queue
import random
import logging
import unicodedata
import threading
from pathlib import Path
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any
import requests
from requests.adapters import HTTPAdapter
from dotenv import load_dotenv

load_dotenv()

# Thread Synchronization & Queue Architecture
state_lock = threading.Lock()
auth_lock = threading.RLock()

# Thread-Safe Pipeline Queue (Pre-fetched & pre-validated edit payloads)
edit_queue: queue.Queue = queue.Queue(maxsize=100)

# API & Bot Configuration
API_URL = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
SPARQL_URL = "https://query.wikidata.org/sparql"
BOT_USER = os.getenv("WIKIDATA_BOT_USER", "SHADOWARROW 2026@ShadowBot").strip()
BOT_PASSWORD = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()

USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026) python-requests"
STATE_FILE = "completed_qids.txt"
LOG_FILE = "bot_execution.log"

CONSUMER_WRITE_DELAY = 0.8  # Strict 0.8s throttle for single consumer thread
MAXLAG = 5
MAX_RETRIES = 5
BATCH_FETCH_SIZE = 50

EDIT_SUMMARY = "Added missing Bengali and Hindi labels/descriptions from verified Wikipedia sitelinks"

# Strict Script Regex Validators (Absolute Hard Guardrails)
BENGALI_SCRIPT_REGEX = re.compile(r'[\u0980-\u09FF]')
DEVANAGARI_SCRIPT_REGEX = re.compile(r'[\u0900-\u097F]')
LATIN_ALPHABET_REGEX = re.compile(r'[a-zA-Z]')

# Configure UTF-8 Logging
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

class FlushStreamHandler(logging.StreamHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

class FlushFileHandler(logging.FileHandler):
    def emit(self, record):
        super().emit(record)
        self.flush()

logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        FlushStreamHandler(sys.stdout),
        FlushFileHandler(LOG_FILE, encoding="utf-8")
    ]
)
logger = logging.getLogger("WikidataBot")

# Complete Verified State & UT Mapping Dictionary (34 Entities)
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
    "Telangana": {"hi": "तेलंगाना", "bn": "তেলেঙ্গানা"},
    "Tripura": {"hi": "त्रिपुरा", "bn": "ত্রিপুরা"},
    "Uttar Pradesh": {"hi": "उत्तर प्रदेश", "bn": "উত্তরপ্রদেশ"},
    "Uttarakhand": {"hi": "उत्तराखंड", "bn": "উত্তরাখণ্ড"},
    "West Bengal": {"hi": "पश्चिम बंगाल", "bn": "পশ্চিমবঙ্গ"},
    "Delhi": {"hi": "दिल्ली", "bn": "দিল্লি"},
    "Jammu and Kashmir": {"hi": "जम्मू और कश्मीर", "bn": "জম্মু ও কাশ্মীর"},
    "Ladakh": {"hi": "लद्दाख", "bn": "লাদাখ"},
    "Puducherry": {"hi": "पुदुचेरी", "bn": "পুদুচেরি"},
    "Chandigarh": {"hi": "चंडीगढ़", "bn": "চণ্ডীগড়"}
}

def validate_script(text: str, lang: str) -> bool:
    """
    Absolute Hard Guardrail:
    1. ZERO Latin characters allowed (re.search(r'[a-zA-Z]', text) MUST be False).
    2. Bengali text MUST match Bengali Unicode range [\u0980-\u09FF].
    3. Hindi text MUST match Devanagari Unicode range [\u0900-\u097F].
    """
    if not text or not isinstance(text, str):
        return False

    if LATIN_ALPHABET_REGEX.search(text):
        return False

    has_bn = bool(BENGALI_SCRIPT_REGEX.search(text))
    has_hi = bool(DEVANAGARI_SCRIPT_REGEX.search(text))

    if lang == "bn":
        return has_bn and not has_hi
    elif lang == "hi":
        return has_hi and not has_bn

    return False

def clean_sitelink_title(title: str) -> str:
    """Strips disambiguation parentheses, e.g. 'Ahmedabad (city)' -> 'Ahmedabad'."""
    if not title or not isinstance(title, str):
        return ""
    cleaned = re.sub(r'\s*\([^)]*\)$', '', title).strip()
    return unicodedata.normalize('NFC', cleaned)

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
            "bn": f"ভারতের {state_bn} রাজ্যের একটি नदी"
        }

    return None

class ZeroErrorWikidataEngine:
    def __init__(self):
        self.session = requests.Session()
        # High-Performance Keep-Alive HTTP Connection Pool to eliminate TCP/SSL Handshake Overhead
        adapter = HTTPAdapter(
            pool_connections=20,
            pool_maxsize=20,
            max_retries=3,
            pool_block=False
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self.session.headers.update({"User-Agent": USER_AGENT})

        self.csrf_token: Optional[str] = None
        self.completed_qids = self._load_completed_qids()
        self.is_running = True

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
        with state_lock:
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
                    messages = err.get("messages", [])

                    is_throttled = any("actionthrottledtext" in str(m) for m in messages)
                    if is_throttled:
                        logger.warning(f"[Wikimedia Anti-Abuse Rate Throttle] Pausing for 15.0s before retry...")
                        time.sleep(15.0)
                        continue

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
        """Log in with Action API action=login using Bot Account credentials."""
        with auth_lock:
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
        """Fetches session CSRF token for write operations."""
        with auth_lock:
            logger.debug("[Auth] Fetching session CSRF token...")
            res = self.request_mediawiki("GET", params={"action": "query", "meta": "tokens", "type": "csrf"})
            token = res.get("query", {}).get("tokens", {}).get("csrftoken")

            if not token or token == "+\\":
                raise RuntimeError("Obtained invalid CSRF token.")

            self.csrf_token = token
            logger.debug("[Auth] Session CSRF token stored.")
            return token

    def fetch_sparql_batch(self) -> List[str]:
        """Queries MediaWiki Action API search generator for instant Indian locality QIDs (<150ms)."""
        search_terms = [
            '"city in India"', '"village in India"', '"district in India"', 
            '"river in India"', '"town in India"', '"human settlement in India"',
            '"subdistrict in India"', '"railway station in India"', '"building in India"',
            '"temple in India"', '"mountain in India"', '"village in West Bengal"',
            '"village in Uttar Pradesh"', '"village in Bihar"', '"town in Maharashtra"',
            '"village in Rajasthan"', '"village in Madhya Pradesh"', '"village in Gujarat"',
            '"village in Tamil Nadu"', '"village in Kerala"', '"village in Karnataka"',
            '"village in Assam"', '"village in Odisha"', '"village in Punjab"',
            '"village in Haryana"', '"village in Jharkhand"', '"village in Uttarakhand"'
        ]
        term = random.choice(search_terms)
        off = random.randint(0, 450)

        res = self.request_mediawiki("GET", params={
            "action": "query",
            "list": "search",
            "srsearch": term,
            "srnamespace": "0",
            "srlimit": "500",
            "sroffset": str(off)
        })
        search_items = res.get("query", {}).get("search", [])
        return [item["title"] for item in search_items if item.get("title", "").startswith("Q")]

    def fetch_entities_batch(self, qids_chunk: List[str]) -> Dict[str, Any]:
        """Fetches up to 50 QIDs in a SINGLE HTTP GET query using action=wbgetentities with sitelinks."""
        if not qids_chunk:
            return {}

        params = {
            "action": "wbgetentities",
            "ids": "|".join(qids_chunk[:BATCH_FETCH_SIZE]),
            "props": "labels|descriptions|sitelinks",
            "sitefilter": "bnwiki|hiwiki",
            "languages": "en|bn|hi"
        }
        res = self.request_mediawiki("GET", params=params)
        return res.get("entities", {})

    def prepare_edit_payload(self, qid: str, entity_data: dict) -> Optional[Tuple[str, dict, List[str]]]:
        """
        Producer Task: Pre-fetches, evaluates sitelinks & state descriptions, validates script rules,
        and returns a fully prepared payload tuple: (qid, edit_payload, fields_updated) or None.
        """
        with state_lock:
            if qid.upper() in self.completed_qids:
                return None

        if "missing" in entity_data:
            self._mark_completed(qid)
            return None

        labels = entity_data.get("labels", {})
        descriptions = entity_data.get("descriptions", {})
        sitelinks = entity_data.get("sitelinks", {})

        en_desc = descriptions.get("en", {}).get("value", "").strip() if isinstance(descriptions.get("en"), dict) else ""

        edit_payload = {}
        payload_labels = {}
        payload_descriptions = {}
        fields_updated = []

        # 1. Label Extraction from verified Wikipedia sitelinks (bnwiki, hiwiki)
        if "hi" not in labels:
            hi_sitelink = sitelinks.get("hiwiki", {}).get("title", "").strip()
            if hi_sitelink:
                clean_hi = clean_sitelink_title(hi_sitelink)
                if validate_script(clean_hi, "hi"):
                    payload_labels["hi"] = {"language": "hi", "value": clean_hi}
                    fields_updated.append("hi_label")

        if "bn" not in labels:
            bn_sitelink = sitelinks.get("bnwiki", {}).get("title", "").strip()
            if bn_sitelink:
                clean_bn = clean_sitelink_title(bn_sitelink)
                if validate_script(clean_bn, "bn"):
                    payload_labels["bn"] = {"language": "bn", "value": clean_bn}
                    fields_updated.append("bn_label")

        # 2. Process State-Mapped Descriptions (hi, bn)
        if en_desc:
            parsed = parse_english_description(en_desc)
            if parsed:
                entity_type, state_name = parsed
                localized_descs = generate_localized_descriptions(entity_type, state_name)
                if localized_descs:
                    if "bn" not in descriptions and "bn" in localized_descs:
                        bn_desc_val = localized_descs["bn"]
                        if validate_script(bn_desc_val, "bn"):
                            payload_descriptions["bn"] = {"language": "bn", "value": bn_desc_val}
                            fields_updated.append("bn_desc")
                    if "hi" not in descriptions and "hi" in localized_descs:
                        hi_desc_val = localized_descs["hi"]
                        if validate_script(hi_desc_val, "hi"):
                            payload_descriptions["hi"] = {"language": "hi", "value": hi_desc_val}
                            fields_updated.append("hi_desc")

        if payload_labels:
            edit_payload["labels"] = payload_labels
        if payload_descriptions:
            edit_payload["descriptions"] = payload_descriptions

        if not edit_payload:
            self._mark_completed(qid)
            return None

        return (qid, edit_payload, fields_updated)

    def producer_loop(self):
        """
        Thread 1 (Pre-fetcher Producer):
        Continuously fetches QIDs & entity status, pre-prepares edit payloads,
        and pushes validated edit payloads into edit_queue.
        """
        logger.info("[Producer] Pre-fetcher Producer Thread started.")
        while self.is_running:
            try:
                qids = self.fetch_sparql_batch()
                with state_lock:
                    pending_qids = [q for q in qids if q.upper() not in self.completed_qids]

                if not pending_qids:
                    time.sleep(1)
                    continue

                queued_count = 0
                for i in range(0, len(pending_qids), BATCH_FETCH_SIZE):
                    if not self.is_running:
                        break
                    chunk = pending_qids[i : i + BATCH_FETCH_SIZE]
                    entities_batch = self.fetch_entities_batch(chunk)

                    for qid in chunk:
                        if not self.is_running:
                            break
                        entity_data = entities_batch.get(qid, {})
                        prepared = self.prepare_edit_payload(qid, entity_data)
                        if prepared:
                            edit_queue.put(prepared)
                            queued_count += 1

                if queued_count > 0:
                    logger.info(f"[Producer] Queued {queued_count} prepared edit payloads | Queue Depth: {edit_queue.qsize()}")

            except Exception as e:
                logger.error(f"[Producer Error] {e}")
                time.sleep(2)

    def consumer_loop(self):
        """
        Thread 2 (Fast Submitter Consumer):
        Pops prepared edit payloads from edit_queue, executes action=wbeditentity POST,
        and strictly enforces 0.8s write delay to maximize edit throughput.
        """
        logger.info("[Consumer] Fast Submitter Consumer Thread started.")
        while self.is_running:
            try:
                try:
                    qid, edit_payload, fields_updated = edit_queue.get(timeout=2)
                except queue.Empty:
                    continue

                if not self.csrf_token:
                    self.refresh_csrf_token()

                start_time = time.time()
                post_data = {
                    "action": "wbeditentity",
                    "id": qid,
                    "data": json.dumps(edit_payload, ensure_ascii=False),
                    "summary": EDIT_SUMMARY,
                    "token": self.csrf_token,
                    "bot": "1"
                }

                # Hard Throttle: strictly 0.8s delay between write requests
                time.sleep(CONSUMER_WRITE_DELAY)

                res = self.request_mediawiki("POST", data=post_data, is_write=True)
                latency = time.time() - start_time

                if res.get("success") == 1:
                    fields_str = "+".join(fields_updated)
                    logger.info(f"QID: {qid} | Action: Updated {fields_str} | Latency: {latency:.2f}s | Status: OK")
                    self._mark_completed(qid)
                else:
                    logger.error(f"QID: {qid} | Action: Failed atomic edit | Latency: {latency:.2f}s | Response: {res}")

                edit_queue.task_done()

            except Exception as e:
                logger.error(f"[Consumer Error] {e}")
                time.sleep(1)

def main():
    logger.info("==========================================================")
    logger.info(" Starting Producer-Consumer High-Throughput Engine (bot.py) ")
    logger.info(" Architecture: Thread-safe Queue + Keep-Alive Connection Pool ")
    logger.info(" Throttle: Strict 0.8s Write Delay | Pre-fetcher Active ")
    logger.info("==========================================================")

    bot = ZeroErrorWikidataEngine()

    try:
        bot.login()
    except Exception as e:
        logger.critical(f"[Fatal] Authentication failed: {e}")
        sys.exit(1)

    # Launch Producer and Consumer Threads
    producer_t = threading.Thread(target=bot.producer_loop, name="ProducerThread", daemon=True)
    consumer_t = threading.Thread(target=bot.consumer_loop, name="ConsumerThread", daemon=True)

    producer_t.start()
    consumer_t.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        logger.info("\n[!] Shutdown requested. Exiting cleanly.")
        bot.is_running = False
        sys.exit(0)

if __name__ == "__main__":
    main()
