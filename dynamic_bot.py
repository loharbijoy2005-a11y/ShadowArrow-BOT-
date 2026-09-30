"""
Dynamic State-Aware Wikidata Regional Bot (dynamic_bot.py)
Parses English descriptions ('en') dynamically, extracts Indian State/UT names,
and generates grammatically natural localized Hindi and Bengali descriptions.
Strictly skips items where state pattern cannot be matched with 100% confidence.
"""

import os
import re
import sys
import time
import random
import logging
from pathlib import Path
from typing import Dict, Optional, Tuple, List
import requests
from dotenv import load_dotenv

load_dotenv()

# Configuration
API_URL = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
SPARQL_URL = "https://query.wikidata.org/sparql"
BOT_USER = os.getenv("WIKIDATA_BOT_USER", "SHADOWARROW 2026@ShadowBot").strip()
BOT_PASSWORD = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()

USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026; contact: local-dev) python-requests"
STATE_FILE = "completed_qids.txt"
RATE_LIMIT_DELAY = 3.0  # Strict 3s rate-limit delay
MAXLAG = 5
MAX_RETRIES = 5

# Setup UTF-8 logging for Windows
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
logger = logging.getLogger("DynamicWikidataBot")

# Complete State & Union Territory Mapping Dictionary
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

def parse_english_description(en_desc: str) -> Optional[Tuple[str, str]]:
    """
    Parses an English description string.
    Returns Tuple of (entity_type, state_name) if matched, else None.
    
    Supported types: 'city', 'town', 'village', 'district', 'river'
    """
    if not en_desc or not isinstance(en_desc, str):
        return None

    desc_clean = en_desc.strip()

    # Regex pattern matchers for English descriptions
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
            # Remove trailing words like 'state' if present
            extracted_state = re.sub(r'\s+state$', '', extracted_state, flags=re.IGNORECASE).strip()
            
            # Normalize state name lookup
            for state_key in INDIAN_STATES:
                if state_key.lower() == extracted_state.lower():
                    return entity_type, state_key

    return None

def generate_localized_descriptions(entity_type: str, state_name: str) -> Optional[Dict[str, str]]:
    """
    Generates grammatically natural Hindi and Bengali descriptions for a state & entity type.
    """
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

class DynamicWikidataBot:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.csrf_token = None
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
                logger.error(f"[State] Error reading state file: {e}")
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
            logger.error(f"[State] Error saving QID {qid_clean}: {e}")

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
                        logger.warning(f"[Auth] Refreshing session/token ({err_code})...")
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

        logger.info("[Auth] Logged into MediaWiki Action API.")
        self.refresh_csrf_token()
        return True

    def refresh_csrf_token(self) -> str:
        res = self.request_mediawiki("GET", params={"action": "query", "meta": "tokens", "type": "csrf"})
        token = res.get("query", {}).get("tokens", {}).get("csrftoken")
        self.csrf_token = token
        return token

    def fetch_target_qids_via_sparql(self) -> List[str]:
        """Queries SPARQL Endpoint for Indian entities missing Bengali or Hindi descriptions."""
        sparql_query = """
            SELECT DISTINCT ?item WHERE {
              ?item wdt:P17 wd:Q668 . # Located in India
              { ?item wdt:P31/wdt:279* wd:Q515 } UNION
              { ?item wdt:P31/wdt:279* wd:Q4022 } UNION
              { ?item wdt:P31 wd:Q1149723 }
              FILTER NOT EXISTS { ?item schema:description ?bnDesc . FILTER(LANG(?bnDesc) = "bn") }
            } LIMIT 250
        """
        try:
            res = requests.get(SPARQL_URL, params={"query": sparql_query, "format": "json"}, headers={"User-Agent": USER_AGENT}, timeout=45)
            res.raise_for_status()
            bindings = res.json().get("results", {}).get("bindings", [])
            qids = []
            for b in bindings:
                uri = b.get("item", {}).get("value", "")
                if "/entity/" in uri:
                    qids.append(uri.split("/entity/")[-1])
            return qids
        except Exception as e:
            logger.error(f"[SPARQL Error] Failed querying SPARQL: {e}")
            return []

    def process_qid(self, qid: str):
        if qid in self.completed_qids:
            return

        # Fetch current labels and descriptions (en, bn, hi)
        res = self.request_mediawiki("GET", params={
            "action": "wbgetentities",
            "ids": qid,
            "props": "descriptions|labels",
            "languages": "en|bn|hi"
        })

        entities = res.get("entities", {})
        entity = entities.get(qid, {})

        if "missing" in entity:
            self._mark_completed(qid)
            return

        descriptions = entity.get("descriptions", {})
        en_desc_obj = descriptions.get("en", {})
        en_desc = en_desc_obj.get("value", "").strip() if isinstance(en_desc_obj, dict) else ""

        if not en_desc:
            logger.info(f"[{qid}] Skipped: No English description available to parse state.")
            self._mark_completed(qid)
            return

        # Parse State and Entity Type dynamically from English description
        parsed_result = parse_english_description(en_desc)
        if not parsed_result:
            logger.info(f"[{qid}] Skipped: English description ('{en_desc}') did not match state pattern.")
            self._mark_completed(qid)
            return

        entity_type, state_name = parsed_result
        localized_descs = generate_localized_descriptions(entity_type, state_name)

        if not localized_descs:
            logger.info(f"[{qid}] Skipped: No localized state mapping found for '{state_name}'.")
            self._mark_completed(qid)
            return

        edits_made = 0
        summary = f"Adding missing regional description for {entity_type} in {state_name} via dynamic NLP bot"

        for lang in ("bn", "hi"):
            desired_desc = localized_descs.get(lang)
            if not desired_desc:
                continue

            current_desc_obj = descriptions.get(lang)
            if current_desc_obj and current_desc_obj.get("value", "").strip():
                logger.info(f"[{qid}] | State: {state_name} | Type: {entity_type} | Lang: {lang} | Skipped (Already exists: '{current_desc_obj.get('value')}')")
                continue

            # Target language description is genuinely missing! Apply edit safely.
            self.set_description(qid, lang, desired_desc, summary)
            edits_made += 1
            logger.info(f"[{qid}] | State: {state_name} | Type: {entity_type} | Lang: {lang} | Success (Set -> '{desired_desc}')")

        if edits_made == 0:
            logger.info(f"[{qid}] | State: {state_name} | Type: {entity_type} | Status: Skipped (No missing fields)")

        self._mark_completed(qid)

    def set_description(self, qid: str, lang: str, value: str, summary: str):
        if not self.csrf_token:
            self.refresh_csrf_token()

        payload = {
            "action": "wbsetdescription",
            "id": qid,
            "language": lang,
            "value": value,
            "summary": summary,
            "token": self.csrf_token,
            "bot": "1"
        }
        res = self.request_mediawiki("POST", data=payload, is_write=True)
        if res.get("success") != 1:
            logger.error(f"[{qid}] Failed setting '{lang}' description: {res}")

def main():
    logger.info("==========================================================")
    logger.info(" Starting Dynamic State-Aware Wikidata Bot ")
    logger.info("==========================================================")

    bot = DynamicWikidataBot()

    try:
        bot.login()
    except Exception as e:
        logger.critical(f"[Fatal] Authentication failed: {e}")
        sys.exit(1)

    # Step 1: Fetch target QIDs via SPARQL
    qids = bot.fetch_target_qids_via_sparql()
    logger.info(f"[Target] Retrieved {len(qids)} items from SPARQL query.")

    # Step 2: Process each item dynamically
    pending_qids = [q for q in qids if q.upper() not in bot.completed_qids]
    logger.info(f"[Target] {len(pending_qids)} pending QIDs to process.")

    for qid in pending_qids:
        try:
            bot.process_qid(qid)
        except Exception as e:
            logger.error(f"[{qid}] Error processing item: {e}")

    logger.info("==========================================================")
    logger.info(f" Execution Finished. Total QIDs logged in state file: {len(bot.completed_qids)}")
    logger.info("==========================================================")

if __name__ == "__main__":
    main()
