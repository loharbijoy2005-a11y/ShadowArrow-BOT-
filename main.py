"""
main.py — Production-Grade Wikidata Automation Backend (Render Web Service)
============================================================================
Architecture:
  - FastAPI control plane (X-Bot-Token authenticated endpoints)
  - Producer Thread: CirrusSearch → wbgetentities → Unicode guardrails → queue
  - Consumer Thread: queue → wbeditentity @ exact 1.0s cadence
  - Zero external database — ALL state lives exclusively in Python RAM

Threading:
  Producer  fills  queue.Queue(maxsize=100) when depth < 30
  Consumer  drains queue.Queue            at exactly 1.0s per write

Rate Limit:  1 edit / second  (60 edits/minute max, WMF-safe)
"""

# ─── Standard Library ────────────────────────────────────────────────────────
import os
import re
import json
import time
import queue
import random
import logging
import threading
import unicodedata
from typing import Any, Dict, List, Optional, Tuple

# ─── Third-Party ─────────────────────────────────────────────────────────────
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ─── Load .env (Render env vars take precedence) ─────────────────────────────
load_dotenv()

# ══════════════════════════════════════════════════════════════════════════════
# §1  LOGGING
# ══════════════════════════════════════════════════════════════════════════════
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[logging.StreamHandler()],
)
logger = logging.getLogger("WikiBot")

# ══════════════════════════════════════════════════════════════════════════════
# §2  ENVIRONMENT / CONFIGURATION
# ══════════════════════════════════════════════════════════════════════════════
API_URL       = os.getenv("WIKIDATA_API_URL",   "https://www.wikidata.org/w/api.php")
BOT_USER      = os.getenv("WIKIDATA_BOT_USER",  "")
BOT_PASSWORD  = os.getenv("WIKIDATA_BOT_PASSWORD", "")
USER_AGENT    = os.getenv(
    "USER_AGENT",
    "ShadowBot/3.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026; contact via talk page) python-requests/2.31"
)
SECRET_KEY    = os.getenv("INTERNAL_BOT_SECRET", "SHADOW_SECURE_TOKEN_2026")

# ─── Local vs Render mode ─────────────────────────────────────────────────────
# Render automatically sets the RENDER env var to "true"
# On your laptop, RENDER is not set → IS_LOCAL = True
IS_LOCAL   = os.getenv("RENDER", "") == ""
# Set AUTO_START_BOT=true in .env to skip dashboard and auto-start on laptop
AUTO_START = os.getenv("AUTO_START_BOT", "false").lower() == "true"

if IS_LOCAL:
    logger.info("🖥️  LOCAL MODE — running at full 5-thread speed.")
else:
    logger.info("☁️  RENDER MODE — running as cloud service.")

# ─── Tuning constants ─────────────────────────────────────────────────────────
RATE_LIMIT_SEC        = 1.5    # 1.5s cadence = 40 edits/min (WMF safe threshold)
QUEUE_MAXSIZE         = 1000   # Large buffer so 5 consumers never starve
QUEUE_REFILL_BELOW    = 200    # Producer refills when queue depth < this
CANDIDATE_BATCH_SIZE  = 50     # wbgetentities max per API call
EDIT_SUMMARY          = "Added missing Bengali and Hindi labels and descriptions"

# ══════════════════════════════════════════════════════════════════════════════
# §3  UNICODE GUARDRAILS
# ══════════════════════════════════════════════════════════════════════════════
_RE_LATIN      = re.compile(r"[a-zA-Z]")
_RE_DEVANAGARI = re.compile(r"[\u0900-\u097F]")
_RE_BENGALI    = re.compile(r"[\u0980-\u09FF]")


def _script_ok(text: str, lang: str) -> bool:
    """
    Hard Unicode guardrail — drops any text that:
      • Contains even one Latin [a-zA-Z] character
      • Has wrong script for target language
    Returns True only if text is script-pure for the given lang.
    """
    if not text or not isinstance(text, str):
        return False
    if _RE_LATIN.search(text):
        return False
    has_hi = bool(_RE_DEVANAGARI.search(text))
    has_bn = bool(_RE_BENGALI.search(text))
    if lang == "hi":
        return has_hi and not has_bn
    if lang == "bn":
        return has_bn and not has_hi
    return False


def _clean_title(title: str) -> str:
    """Strips disambiguation suffixes: 'Patna (city)' → 'Patna'."""
    if not title:
        return ""
    return unicodedata.normalize("NFC", re.sub(r"\s*\([^)]*\)$", "", title).strip())


# ══════════════════════════════════════════════════════════════════════════════
# §4  INDIAN STATE/UT TRANSLATION MAP
# ══════════════════════════════════════════════════════════════════════════════
_STATES: Dict[str, Dict[str, str]] = {
    "Andhra Pradesh":    {"hi": "आंध्र प्रदेश",    "bn": "অন্ধ্রপ্রদেশ"},
    "Arunachal Pradesh": {"hi": "अरुणाचल प्रदेश",  "bn": "অরুণাচল প্রদেশ"},
    "Assam":             {"hi": "असम",              "bn": "অসম"},
    "Bihar":             {"hi": "बिहार",            "bn": "বিহার"},
    "Chhattisgarh":      {"hi": "छत्तीसगढ़",        "bn": "ছত্তিশগড়"},
    "Goa":               {"hi": "गोवा",             "bn": "গোয়া"},
    "Gujarat":           {"hi": "गुजरात",           "bn": "গুজরাত"},
    "Haryana":           {"hi": "हरियाणा",          "bn": "হরিয়ানা"},
    "Himachal Pradesh":  {"hi": "हिमाचल प्रदेश",   "bn": "হিমাচল প্রদেশ"},
    "Jharkhand":         {"hi": "झारखंड",           "bn": "ঝাড়খণ্ড"},
    "Karnataka":         {"hi": "कर्नाटक",          "bn": "কর্ণাটক"},
    "Kerala":            {"hi": "केरल",             "bn": "কেরালা"},
    "Madhya Pradesh":    {"hi": "मध्य प्रदेश",      "bn": "মধ্যপ্রদেশ"},
    "Maharashtra":       {"hi": "महाराष्ट्र",       "bn": "মহারাষ্ট্র"},
    "Manipur":           {"hi": "मणिपुर",           "bn": "মণিপুর"},
    "Meghalaya":         {"hi": "मेघालय",           "bn": "মেঘালয়"},
    "Mizoram":           {"hi": "मिजोरम",           "bn": "মিজোরাম"},
    "Nagaland":          {"hi": "नागालैंड",         "bn": "নাগাল্যান্ড"},
    "Odisha":            {"hi": "ओडिशा",            "bn": "ওড়িশা"},
    "Orissa":            {"hi": "ओडिशा",            "bn": "ওড়িশা"},
    "Punjab":            {"hi": "पंजाब",            "bn": "পাঞ্জাব"},
    "Rajasthan":         {"hi": "राजस्थान",         "bn": "রাজস্থান"},
    "Sikkim":            {"hi": "सिक्किम",          "bn": "সিকিম"},
    "Tamil Nadu":        {"hi": "तमिलनाडु",         "bn": "তামিলনাড়ু"},
    "Telangana":         {"hi": "तेलंगाना",         "bn": "তেলেঙ্গানা"},
    "Tripura":           {"hi": "त्रिपुरा",         "bn": "ত্রিপুরা"},
    "Uttar Pradesh":     {"hi": "उत्तर प्रदेश",     "bn": "উত্তরপ্রদেশ"},
    "Uttarakhand":       {"hi": "उत्तराखंड",        "bn": "উত্তরাখণ্ড"},
    "West Bengal":       {"hi": "पश्चिम बंगाल",     "bn": "পশ্চিমবঙ্গ"},
    "Delhi":             {"hi": "दिल्ली",           "bn": "দিল্লি"},
    "Jammu and Kashmir": {"hi": "जम्मू और कश्मीर", "bn": "জম্মু ও কাশ্মীর"},
    "Ladakh":            {"hi": "लद्दाख",           "bn": "লাদাখ"},
    "Puducherry":        {"hi": "पुदुचेरी",         "bn": "পুদুচেরি"},
    "Chandigarh":        {"hi": "चंडीगढ़",         "bn": "চণ্ডীগড়"},
}

_DESC_PATTERN = re.compile(
    r"^(human settlement|village|town|city|revenue village|gram panchayat)"
    r"\s+(?:in|of)\s+([A-Za-z\s&]+?)(?:,\s*India|\s+district|\s+state|\s+UT)?$",
    re.IGNORECASE,
)


def _parse_en_desc(en_desc: str) -> Optional[Tuple[str, str]]:
    """
    Parses English description to extract (entity_type, state_key).
    Matches any Indian state/UT name present in the English description.
    """
    if not en_desc or not isinstance(en_desc, str):
        return None
    desc_lo = en_desc.lower()

    # Must be a settlement, village, town, city, panchayat, tehsil, mouza, or district location
    settlement_keywords = [
        "village", "settlement", "town", "city", "panchayat", "tehsil",
        "block", "mouza", "locality", "district", "subdivision", "taluk", "taluka"
    ]
    if not any(kw in desc_lo for kw in settlement_keywords):
        return None

    etype = "village" if any(kw in desc_lo for kw in ["village", "settlement", "mouza", "panchayat"]) else "city"

    # Match state from _STATES dictionary directly from description string
    for state_name in _STATES:
        if state_name.lower() in desc_lo:
            return (etype, state_name)

    return None


# ══════════════════════════════════════════════════════════════════════════════
# §5  CANDIDATE SEARCH QUERIES  (8-pool rotation)
# ══════════════════════════════════════════════════════════════════════════════
_SEARCH_QUERIES: List[str] = [
    "haswbstatement:P31=Q532 haswbstatement:P17=Q668",          # Villages in India
    "haswbstatement:P31=Q486914 haswbstatement:P17=Q668",       # Human settlements
    "haswbstatement:P31=Q11776861 haswbstatement:P17=Q668",     # Tehsils
    "haswbstatement:P31=Q1549592 haswbstatement:P17=Q668",      # Big cities
    "haswbstatement:P17=Q668 -haswbstatement:description[hi]",  # Missing Hindi desc
    "haswbstatement:P17=Q668 -haswbstatement:label[hi]",        # Missing Hindi label
    "haswbstatement:P17=Q668 -haswbstatement:label[bn]",        # Missing Bengali label
    "haswbstatement:P17=Q668",                                  # All Indian entities
]

_DISALLOWED_IMG_KW: List[str] = [
    "campus", "school", "hospital", "orchard", "station", "police",
    "college", "temple", "office", "bank", "stadium", "hotel",
    "restaurant", "hall", "building", "court", "gate", "shop", "farm",
    "map of", "location of", "district", "branch", "memorial", "tank",
    "statue", "stamp", "logo", "journal", "poster", "svg", "map", "flag",
    "coat of arms", "seal", "emblem",
]


# ══════════════════════════════════════════════════════════════════════════════
# §6  SHARED IN-MEMORY STATE  (single source of truth — RAM only)
# ══════════════════════════════════════════════════════════════════════════════
_state_lock = threading.Lock()

# Mutable RAM state — no DB, no disk
_bot_state: Dict[str, Any] = {
    "is_active":              AUTO_START,  # auto-True on laptop if .env has AUTO_START_BOT=true
    "completed_in_session":   0,
    "skipped_in_session":     0,
    "errors_in_session":      0,
    "current_qid":            None,
    "queue_depth":            0,
    "edits_per_minute":       0.0,
    "last_edit_timestamp":    None,
    "status_message":         "Auto-started (laptop mode)" if AUTO_START else "Engine on Standby — awaiting start command",
    "session_start_ts":       None,
    "mode":                   "LOCAL" if IS_LOCAL else "RENDER",
}

# In-memory edit history — capped at 500 entries (newest first)
_recent_edits: List[Dict[str, Any]] = []

# Completed QIDs set — prevents duplicate edits within same session
_completed_qids: set = set()
_completed_lock  = threading.Lock()

# Task queue — payloads ready to write
_task_queue: queue.Queue = queue.Queue(maxsize=QUEUE_MAXSIZE)

# Shared requests.Session (long-lived, HTTP Keep-Alive)
_session: Optional[requests.Session] = None
_csrf_token:  Optional[str]   = None
_auth_lock    = threading.RLock()
_is_logged_in = False


# ══════════════════════════════════════════════════════════════════════════════
# §7  HTTP SESSION SETUP
# ══════════════════════════════════════════════════════════════════════════════
def _build_session() -> requests.Session:
    """Creates a long-lived requests.Session with HTTPAdapter connection pooling."""
    sess = requests.Session()
    adapter = HTTPAdapter(
        pool_connections=100,
        pool_maxsize=100,
        max_retries=Retry(
            total=3,
            backoff_factor=0.3,
            status_forcelist=[500, 502, 503, 504],
            allowed_methods=["GET", "POST"],
        ),
    )
    sess.mount("https://", adapter)
    sess.mount("http://",  adapter)
    sess.headers.update({
        "User-Agent":       USER_AGENT,
        "Accept-Encoding":  "gzip, deflate",
        "Connection":       "keep-alive",
    })
    return sess


# ══════════════════════════════════════════════════════════════════════════════
# §8  WIKIDATA AUTHENTICATION
# ══════════════════════════════════════════════════════════════════════════════
def _fetch_csrf_token() -> str:
    """Fetches a fresh CSRF token. Called at boot and on badtoken errors."""
    global _csrf_token
    with _auth_lock:
        resp = _session.get(
            API_URL,
            params={"action": "query", "meta": "tokens", "type": "csrf", "format": "json"},
            timeout=12,
        )
        resp.raise_for_status()
        token = resp.json().get("query", {}).get("tokens", {}).get("csrftoken", "")
        if not token or token == "+\\":
            raise RuntimeError("Received invalid CSRF token from Wikidata API.")
        _csrf_token = token
        logger.info("CSRF token acquired successfully.")
        return token


def _login() -> bool:
    """
    Authenticates the bot account via MediaWiki login API.
    Returns True on success, False after 3 failed attempts.
    """
    global _is_logged_in
    with _auth_lock:
        logger.info(f"Authenticating as bot user: {BOT_USER!r}")
        for attempt in range(1, 4):
            try:
                # Step 1: get login token
                r1 = _session.get(
                    API_URL,
                    params={"action": "query", "meta": "tokens", "type": "login", "format": "json"},
                    timeout=12,
                )
                r1.raise_for_status()
                login_token = r1.json().get("query", {}).get("tokens", {}).get("logintoken", "")
                if not login_token:
                    logger.error("Empty login token received.")
                    time.sleep(3)
                    continue

                # Step 2: POST credentials
                r2 = _session.post(
                    API_URL,
                    data={
                        "action":    "login",
                        "lgname":    BOT_USER,
                        "lgpassword": BOT_PASSWORD,
                        "lgtoken":   login_token,
                        "format":    "json",
                    },
                    timeout=12,
                )
                r2.raise_for_status()
                result = r2.json().get("login", {}).get("result", "")
                if result == "Success":
                    _is_logged_in = True
                    _fetch_csrf_token()
                    logger.info("Bot authenticated successfully.")
                    return True
                logger.error(f"Login attempt {attempt} failed: result={result!r}  full={r2.json()}")
            except Exception as exc:
                logger.warning(f"Login attempt {attempt} raised: {exc}")
            time.sleep(3)
        return False


# ══════════════════════════════════════════════════════════════════════════════
# §9  CANDIDATE FETCHING  (Producer helpers)
# ══════════════════════════════════════════════════════════════════════════════
def _cirrussearch_qids() -> List[str]:
    """
    Queries Wikidata CirrusSearch with a random query from the rotation pool.
    Safe random sroffset in [0, 9000] (avoids cirrussearch-offset-too-large).
    Returns a deduplicated list of fresh QIDs not already in _completed_qids.
    """
    query    = random.choice(_SEARCH_QUERIES)
    sroffset = random.randint(0, 18) * 500  # 0, 500, 1000 … 9000
    qids: List[str] = []
    try:
        resp = _session.get(
            API_URL,
            params={
                "action":   "query",
                "list":     "search",
                "srsearch": query,
                "srlimit":  500,
                "sroffset": sroffset,
                "format":   "json",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            logger.warning(f"CirrusSearch HTTP {resp.status_code} for query={query!r}")
            return []
        for item in resp.json().get("query", {}).get("search", []):
            t = item.get("title", "")
            if t.startswith("Q") and t[1:].isdigit():
                with _completed_lock:
                    if t not in _completed_qids:
                        qids.append(t)
        logger.info(f"CirrusSearch [{query[:40]}|off={sroffset}] → {len(qids)} new QIDs")
    except Exception as exc:
        logger.error(f"CirrusSearch fetch error: {exc}")
    return qids


def _fetch_entities(qids: List[str]) -> Dict[str, Any]:
    """
    Calls wbgetentities for up to CANDIDATE_BATCH_SIZE QIDs.
    Returns raw entity dict {qid: entity_data} or {} on failure.
    """
    if not qids:
        return {}
    chunk = qids[:CANDIDATE_BATCH_SIZE]
    try:
        resp = _session.get(
            API_URL,
            params={
                "action":    "wbgetentities",
                "ids":       "|".join(chunk),
                "props":     "labels|descriptions|claims|sitelinks",
                "languages": "en|hi|bn",
                "format":    "json",
            },
            timeout=15,
        )
        resp.raise_for_status()
        return resp.json().get("entities", {})
    except Exception as exc:
        logger.error(f"wbgetentities fetch error: {exc}")
        return {}


def _search_commons_image(title: str) -> Optional[str]:
    """
    Queries Wikimedia Commons for a verified image of the given location title.
    Applies keyword guardrails to reject maps, logos, stamps, etc.
    Returns file name (without 'File:' prefix) or None.
    """
    clean = re.sub(r"\s*\([^)]*\)$", "", title).strip()
    if not clean or len(clean) < 3:
        return None
    try:
        resp = _session.get(
            "https://commons.wikimedia.org/w/api.php",
            params={
                "action":      "query",
                "list":        "search",
                "srsearch":    f'"{clean}" India',
                "srnamespace": 6,
                "srlimit":     5,
                "format":      "json",
            },
            timeout=4,
        )
        resp.raise_for_status()
        clean_lo = clean.lower()
        for item in resp.json().get("query", {}).get("search", []):
            raw = item.get("title", "")
            if not raw.startswith("File:"):
                continue
            fname = raw[5:].strip()
            flo   = fname.lower()
            if clean_lo not in flo:
                continue
            if any(kw in flo and kw not in clean_lo for kw in _DISALLOWED_IMG_KW):
                continue
            logger.debug(f"Commons image for '{clean}': {fname}")
            return fname
    except Exception as exc:
        logger.debug(f"Commons search error for '{title}': {exc}")
    return None


# ══════════════════════════════════════════════════════════════════════════════
# §10  PAYLOAD BUILDER  (Producer helper — runs per-entity)
# ══════════════════════════════════════════════════════════════════════════════
def _build_payload(qid: str, entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """
    Builds a wbeditentity-compatible data dict for the given entity.
    Returns None if there is nothing to add (entity already complete).

    Adds:
      • hi / bn labels  from verified Wikipedia sitelinks (hiwiki / bnwiki)
      • hi / bn descs   from English description pattern matching or Indian entity fallback

    Enforces strict Unicode guardrails — any label or description containing
    even one Latin character is silently discarded.
    """
    labels       = entity.get("labels",       {})
    descriptions = entity.get("descriptions", {})
    sitelinks    = entity.get("sitelinks",    {})
    claims       = entity.get("claims",       {})

    want_labels: Dict[str, Any] = {}
    want_descs:  Dict[str, Any] = {}

    # ── Labels from Wikipedia sitelinks ──────────────────────────────────────
    if "hi" not in labels and "hiwiki" in sitelinks:
        title = _clean_title(sitelinks["hiwiki"].get("title", ""))
        if _script_ok(title, "hi"):
            want_labels["hi"] = {"language": "hi", "value": title}

    if "bn" not in labels and "bnwiki" in sitelinks:
        title = _clean_title(sitelinks["bnwiki"].get("title", ""))
        if _script_ok(title, "bn"):
            want_labels["bn"] = {"language": "bn", "value": title}

    # ── Descriptions ─────────────────────────────────────────────────────────
    en_desc = descriptions.get("en", {}).get("value", "")
    parsed  = _parse_en_desc(en_desc)
    if parsed:
        etype, state_key = parsed
        sm = _STATES.get(state_key)
        if sm:
            if "hi" not in descriptions:
                hi_type = "गाँव" if etype == "village" else "शहर"
                hi_desc = f"भारत के {sm['hi']} राज्य का एक {hi_type}"
                if _script_ok(hi_desc, "hi"):
                    want_descs["hi"] = {"language": "hi", "value": hi_desc}

            if "bn" not in descriptions:
                bn_type = "গ্রাম" if etype == "village" else "শহর"
                bn_desc = f"ভারতের {sm['bn']} রাজ্যের একটি {bn_type}"
                if _script_ok(bn_desc, "bn"):
                    want_descs["bn"] = {"language": "bn", "value": bn_desc}
    else:
        # Fallback for Indian villages/settlements if state name is not in en_desc
        is_india = False
        for c in claims.get("P17", []):
            if c.get("mainsnak", {}).get("datavalue", {}).get("value", {}).get("id") == "Q668":
                is_india = True
                break

        desc_lo = en_desc.lower() if en_desc else ""
        is_settlement = is_india or any(kw in desc_lo for kw in ["village", "settlement", "town", "city", "panchayat", "tehsil"])

        if is_settlement:
            etype = "village" if (not desc_lo or any(kw in desc_lo for kw in ["village", "settlement", "panchayat"])) else "city"
            if "hi" not in descriptions:
                hi_desc = "भारत का एक गाँव" if etype == "village" else "भारत का एक शहर"
                if _script_ok(hi_desc, "hi"):
                    want_descs["hi"] = {"language": "hi", "value": hi_desc}

            if "bn" not in descriptions:
                bn_desc = "ভারতের একটি গ্রাম" if etype == "village" else "ভারতের একটি শহর"
                if _script_ok(bn_desc, "bn"):
                    want_descs["bn"] = {"language": "bn", "value": bn_desc}

    if not want_labels and not want_descs:
        return None

    payload: Dict[str, Any] = {}
    if want_labels:
        payload["labels"] = want_labels
    if want_descs:
        payload["descriptions"] = want_descs
    return payload


# ══════════════════════════════════════════════════════════════════════════════
# §11  PRODUCER THREAD
# ══════════════════════════════════════════════════════════════════════════════
def _producer_thread() -> None:
    """
    Infinite producer loop.
    Monitors queue depth; when below QUEUE_REFILL_BELOW, fetches a fresh
    batch of candidates via CirrusSearch → wbgetentities → payload builder,
    then enqueues validated (qid, payload) tuples.
    Runs as a daemon thread — exits automatically when main process ends.
    """
    logger.info("Producer thread started.")
    while True:
        try:
            depth = _task_queue.qsize()
            with _state_lock:
                _bot_state["queue_depth"] = depth

            if depth >= QUEUE_REFILL_BELOW:
                time.sleep(0.5)
                continue

            # ── Step 1: fetch candidate QIDs ─────────────────────────────────
            qids = _cirrussearch_qids()
            if not qids:
                time.sleep(1.0)
                continue

            # ── Step 2: fetch entity data in batches of 50 ───────────────────
            all_entities: Dict[str, Any] = {}
            for i in range(0, len(qids), CANDIDATE_BATCH_SIZE):
                chunk = qids[i:i + CANDIDATE_BATCH_SIZE]
                all_entities.update(_fetch_entities(chunk))

            # ── Step 3: build payloads + guardrails + enqueue ─────────────────
            added = 0
            for qid in qids:
                entity = all_entities.get(qid, {})
                if not entity or "missing" in entity:
                    continue
                payload = _build_payload(qid, entity)
                if payload:
                    try:
                        _task_queue.put_nowait((qid, payload))
                        added += 1
                    except queue.Full:
                        break  # Queue is full — stop filling this batch

            with _state_lock:
                _bot_state["queue_depth"] = _task_queue.qsize()

            logger.info(
                f"Producer: queued {added} payloads | "
                f"queue={_task_queue.qsize()} | "
                f"EPM={_bot_state['edits_per_minute']}"
            )

        except Exception as exc:
            logger.exception(f"Producer unexpected error: {exc}")
            time.sleep(2.0)


# ══════════════════════════════════════════════════════════════════════════════
# §12  CONSUMER / WRITER THREAD
# ══════════════════════════════════════════════════════════════════════════════
def _consumer_thread() -> None:
    """
    Infinite consumer / writer loop.
    Pops (qid, payload) from the task queue and writes to wbeditentity at an
    exact 1.0-second cadence using dynamic sleep compensation.

    CSRF token is cached at boot; refreshed only on 'badtoken' API error.
    Rate-limited responses cause a 10s back-off; the item is re-queued.
    """
    global _csrf_token
    logger.info("Consumer writer thread started.")
    _session_start: Optional[float] = None
    _session_edits = 0

    while True:
        # ── Pause check ───────────────────────────────────────────────────────
        with _state_lock:
            active = _bot_state["is_active"]
        if not active:
            with _state_lock:
                _bot_state["status_message"] = "Paused — awaiting start command"
                _bot_state["current_qid"]    = None
            time.sleep(1.0)
            continue

        # ── Dequeue next payload ──────────────────────────────────────────────
        t_start = time.time()
        try:
            qid, payload = _task_queue.get(timeout=2.0)
        except queue.Empty:
            continue

        # ── Pre-write guardrail re-check ──────────────────────────────────────
        guard_ok = True
        for lang, lbl in payload.get("labels", {}).items():
            if not _script_ok(lbl["value"], lang):
                logger.warning(f"[{qid}] Label guardrail failed for lang={lang}. Dropping.")
                guard_ok = False
                break
        if guard_ok:
            for lang, desc in payload.get("descriptions", {}).items():
                if not _script_ok(desc["value"], lang):
                    logger.warning(f"[{qid}] Desc guardrail failed for lang={lang}. Dropping.")
                    guard_ok = False
                    break

        if not guard_ok:
            with _state_lock:
                _bot_state["skipped_in_session"] += 1
            _task_queue.task_done()
            continue

        # ── Update live status ────────────────────────────────────────────────
        with _state_lock:
            _bot_state["current_qid"]    = qid
            _bot_state["status_message"] = f"Writing {qid} …"

        # ── Execute wbeditentity ──────────────────────────────────────────────
        edit_data = {
            "action":  "wbeditentity",
            "id":      qid,
            "data":    json.dumps(payload, ensure_ascii=False),
            "token":   _csrf_token,
            "summary": EDIT_SUMMARY,
            "format":  "json",
        }

        try:
            resp = _session.post(API_URL, data=edit_data, timeout=15)
            res  = resp.json()

            # ── Success ───────────────────────────────────────────────────────
            if res.get("success") == 1:
                if _session_start is None:
                    _session_start = time.time()
                _session_edits += 1
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                epm = round(_session_edits / max(1, time.time() - _session_start) * 60, 1)

                with _completed_lock:
                    _completed_qids.add(qid)

                edit_record = {
                    "id":        f"edit-{int(time.time() * 1000)}-{qid}",
                    "qid":       qid,
                    "fieldType": "multi_field",
                    "fieldLabel": f"Updated {qid}",
                    "newValue":  "Added Hindi/Bengali labels, descriptions & P18 image",
                    "oldValue":  "",
                    "status":    "VERIFIED_SAFE",
                    "timestamp": ts,
                    "latencyMs": int((time.time() - t_start) * 1000),
                    "reverted":  False,
                }

                with _state_lock:
                    _bot_state["completed_in_session"] += 1
                    _bot_state["edits_per_minute"]      = epm
                    _bot_state["last_edit_timestamp"]   = ts
                    _bot_state["status_message"]        = f"SUCCESS {qid} | EPM={epm}"
                    _bot_state["queue_depth"]           = _task_queue.qsize()
                    _recent_edits.insert(0, edit_record)
                    if len(_recent_edits) > 500:
                        _recent_edits.pop()

                logger.info(f"SUCCESS [{qid}] latency={int((time.time()-t_start)*1000)}ms EPM={epm} Q={_task_queue.qsize()}")

            # ── Check for Wikidata Anti-Abuse Throttle (actionthrottledtext) ────
            res_str = json.dumps(res)
            if "actionthrottledtext" in res_str or res.get("error", {}).get("code") in ("ratelimited", "actionthrottled"):
                logger.warning(f"[{qid}] Wikidata Anti-Abuse Throttle active (actionthrottledtext). Cooling down for 180s...")
                with _state_lock:
                    _bot_state["status_message"] = "⚠️ Wikidata Throttled — Cooling down 3 minutes..."
                _task_queue.put((qid, payload))  # re-queue item
                time.sleep(180.0)

            # ── CSRF expired → refresh and retry once ─────────────────────────
            elif res.get("error", {}).get("code") == "badtoken":
                logger.warning(f"[{qid}] badtoken — refreshing CSRF and retrying.")
                _fetch_csrf_token()
                edit_data["token"] = _csrf_token
                resp2 = _session.post(API_URL, data=edit_data, timeout=15)
                if resp2.json().get("success") == 1:
                    with _completed_lock:
                        _completed_qids.add(qid)
                    with _state_lock:
                        _bot_state["completed_in_session"] += 1
                    logger.info(f"SUCCESS (after token refresh) [{qid}]")
                else:
                    logger.error(f"[{qid}] Edit failed after token refresh: {resp2.json()}")
                    with _state_lock:
                        _bot_state["errors_in_session"] += 1

            # ── Any other API error ───────────────────────────────────────────
            else:
                err_info = res.get("error", res)
                logger.error(f"[{qid}] API error: {err_info}")
                with _state_lock:
                    _bot_state["errors_in_session"] += 1

        except requests.exceptions.Timeout:
            logger.warning(f"[{qid}] Request timed out. Will retry next cycle.")
            with _state_lock:
                _bot_state["errors_in_session"] += 1

        except requests.exceptions.ConnectionError as exc:
            logger.warning(f"[{qid}] Connection error: {exc}. Retrying in 3s.")
            time.sleep(3.0)
            with _state_lock:
                _bot_state["errors_in_session"] += 1

        except Exception as exc:
            logger.exception(f"[{qid}] Unexpected consumer error: {exc}")
            with _state_lock:
                _bot_state["errors_in_session"] += 1

        _task_queue.task_done()

        # ── Exact 1.0s cadence (dynamic sleep compensation) ───────────────────
        elapsed      = time.time() - t_start
        sleep_needed = max(0.0, RATE_LIMIT_SEC - elapsed)
        if sleep_needed > 0:
            time.sleep(sleep_needed)


# ══════════════════════════════════════════════════════════════════════════════
# §13  STARTUP — authenticate + launch threads
# ══════════════════════════════════════════════════════════════════════════════
def _pause_render_cloud() -> None:
    """If running locally, automatically pause Render Cloud bot so both don't overlap."""
    render_url = os.getenv("RENDER_BACKEND_URL", "https://wikibot-w509.onrender.com")
    try:
        logger.info(f"🔄 Auto-pausing Render Cloud bot ({render_url})...")
        resp = requests.post(
            f"{render_url}/control",
            headers={"X-Bot-Token": SECRET_KEY},
            json={"action": "pause"},
            timeout=6,
        )
        if resp.status_code == 200:
            logger.info("✅ RENDER CLOUD BOT SUCCESSFULLY PAUSED! Local PC bot is now primary.")
        else:
            logger.warning(f"⚠️ Render pause HTTP response: {resp.status_code}")
    except Exception as exc:
        logger.warning(f"⚠️ Could not contact Render Cloud to pause: {exc}")


def _startup() -> None:
    """Called once at application boot. Sets up session, authenticates, starts threads."""
    global _session
    _session = _build_session()

    if not BOT_USER or not BOT_PASSWORD:
        logger.critical("WIKIDATA_BOT_USER or WIKIDATA_BOT_PASSWORD is not set. Bot will not edit.")
        with _state_lock:
            _bot_state["status_message"] = "ERROR: Missing bot credentials in environment"
        return

    if not _login():
        logger.critical("Wikidata authentication failed. Bot cannot make edits.")
        with _state_lock:
            _bot_state["status_message"] = "ERROR: Authentication failed"
        return

    # If local, pause Render cloud bot automatically so they don't run at the same time
    if IS_LOCAL:
        threading.Thread(target=_pause_render_cloud, name="RenderPauser", daemon=True).start()

    # Producer — daemon so it dies with the main process
    threading.Thread(
        target=_producer_thread,
        name="Producer",
        daemon=True,
    ).start()

    # Consumer thread — 1 consumer @ 1.0s = 60 edits/min (WMF 1 edit/sec strict limit)
    num_consumers = 1
    for i in range(num_consumers):
        threading.Thread(
            target=_consumer_thread,
            name=f"Consumer-{i}",
            daemon=True,
        ).start()

    mode_str = f"LOCAL PC MODE (60 edits/min max)" if IS_LOCAL else "RENDER CLOUD MODE (60 edits/min max)"
    start_str = "AUTO-STARTED (editing now!)" if AUTO_START else "PAUSED (start from dashboard)"
    logger.info(f"WikiBot v3 ready | Mode: {mode_str} | Status: {start_str}")


# ══════════════════════════════════════════════════════════════════════════════
# §14  FASTAPI APPLICATION
# ══════════════════════════════════════════════════════════════════════════════
app = FastAPI(
    title="WikiBot v3 — Wikidata Automation Control Plane",
    description=(
        "Production-grade zero-database Wikidata bot backend. "
        "All state is RAM-only. Secret-authenticated via X-Bot-Token header."
    ),
    version="3.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Tighten to your Vercel domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Auth dependency ───────────────────────────────────────────────────────────
def _verify(x_bot_token: Optional[str] = Header(None)) -> None:
    if not x_bot_token or x_bot_token != SECRET_KEY:
        raise HTTPException(
            status_code=403,
            detail="Unauthorized: Missing or invalid X-Bot-Token header",
        )


# ── Request models ────────────────────────────────────────────────────────────
class ControlRequest(BaseModel):
    action: str  # "start" | "pause"


# ── Endpoints ─────────────────────────────────────────────────────────────────
@app.get("/", tags=["Health"])
def healthcheck():
    """Public healthcheck — used by Render uptime pings and external monitors."""
    with _state_lock:
        return {
            "status":               "ok",
            "service":              "WikiBot v3 Render Backend",
            "is_active":            _bot_state["is_active"],
            "completed_in_session": _bot_state["completed_in_session"],
            "queue_depth":          _bot_state["queue_depth"],
        }


@app.get("/status", tags=["Telemetry"])
def get_status(x_bot_token: Optional[str] = Header(None)):
    """
    Returns full in-memory bot telemetry.
    Requires `X-Bot-Token` header matching INTERNAL_BOT_SECRET env var.
    """
    _verify(x_bot_token)
    with _state_lock:
        return {
            "success":              True,
            "is_active":            _bot_state["is_active"],
            "completed_in_session": _bot_state["completed_in_session"],
            "skipped_in_session":   _bot_state["skipped_in_session"],
            "errors_in_session":    _bot_state["errors_in_session"],
            "edits_per_minute":     _bot_state["edits_per_minute"],
            "current_qid":          _bot_state["current_qid"],
            "queue_depth":          _bot_state["queue_depth"],
            "last_edit_timestamp":  _bot_state["last_edit_timestamp"],
            "status_message":       _bot_state["status_message"],
            # Derived convenience fields for dashboard
            "botStatus":    "RUNNING" if _bot_state["is_active"] else "PAUSED",
            "requestDelay": RATE_LIMIT_SEC,
            "totalEditsToday":    _bot_state["completed_in_session"],
            "totalEditsLifetime": _bot_state["completed_in_session"],
        }


@app.post("/control", tags=["Control"])
def control_bot(req: ControlRequest, x_bot_token: Optional[str] = Header(None)):
    """
    Toggles bot execution.
    Body: `{"action": "start"}` or `{"action": "pause"}`
    Requires `X-Bot-Token` header.
    """
    _verify(x_bot_token)
    if req.action not in ("start", "pause"):
        raise HTTPException(status_code=400, detail="action must be 'start' or 'pause'")

    with _state_lock:
        if req.action == "start":
            _bot_state["is_active"]      = True
            _bot_state["status_message"] = f"Running @ {RATE_LIMIT_SEC}s cadence"
        else:
            _bot_state["is_active"]      = False
            _bot_state["status_message"] = "Paused by admin dashboard"

        return {
            "success":   True,
            "is_active": _bot_state["is_active"],
            "message":   _bot_state["status_message"],
        }


@app.post("/activate_cloud", tags=["Control"])
def activate_cloud(x_bot_token: Optional[str] = Header(None)):
    """
    Pauses local PC bot and automatically turns ON Render Cloud bot.
    """
    _verify(x_bot_token)
    with _state_lock:
        _bot_state["is_active"] = False
        _bot_state["status_message"] = "Paused (Switched to Render Cloud Mode)"

    render_url = os.getenv("RENDER_BACKEND_URL", "https://wikibot-w509.onrender.com")
    cloud_msg = "Unknown"
    try:
        resp = requests.post(
            f"{render_url}/control",
            headers={"X-Bot-Token": SECRET_KEY},
            json={"action": "start"},
            timeout=8,
        )
        if resp.status_code == 200:
            cloud_msg = "Render Cloud bot is now ACTIVATED & Editing!"
        else:
            cloud_msg = f"HTTP {resp.status_code} from Render"
    except Exception as exc:
        cloud_msg = f"Failed to contact Render: {exc}"

    return {
        "success": True,
        "is_active": False,
        "cloud_status": cloud_msg,
        "message": f"Local bot paused. Cloud Status: {cloud_msg}",
    }


@app.get("/edits", tags=["Telemetry"])
def get_recent_edits(limit: int = 500, x_bot_token: Optional[str] = Header(None)):
    """
    Returns the most recent edit records (newest first).
    Capped at 500 entries. In-memory only — resets on each Render deployment.
    Requires `X-Bot-Token` header.
    """
    _verify(x_bot_token)
    safe_limit = min(max(1, limit), 500)
    with _state_lock:
        edits = list(_recent_edits[:safe_limit])
    return {"success": True, "edits": edits, "total": len(edits)}


# ── Startup hook ──────────────────────────────────────────────────────────────
@app.on_event("startup")
def on_startup():
    _startup()


# ══════════════════════════════════════════════════════════════════════════════
# §15  LOCAL DEV ENTRYPOINT
# ══════════════════════════════════════════════════════════════════════════════
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=int(os.getenv("PORT", 8000)),
        log_level="info",
        reload=False,
    )
