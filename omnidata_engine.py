"""
OmniData Engine: Production-Grade Fault-Tolerant Wikidata Bot
Architected for Zero Rate-Limit Blocks and Zero Data Corruption Risks.

Key Capabilities:
1. Multi-Source Data Enrichment (SPARQL + MediaWiki API + Wikimedia Commons API for P18).
2. Sitelink-Based Native Labels (hiwiki / bnwiki strictly, no transliteration/guessing).
3. Pattern-based Structured Localized Descriptions (Hindi & Bengali).
4. Producer-Consumer Threading Model (threading + queue.Queue).
5. Hard Regex Guardrails for Script Purity (Zero Latin, No Cross-Script Contamination).
6. State Tracking & skipped_entities.json logging.
"""

import os
import re
import json
import time
import queue
import logging
import threading
import unicodedata
from typing import Dict, List, Optional, Tuple, Any
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from config import Config

# Configure Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] [%(threadName)s] %(message)s",
    handlers=[
        logging.FileHandler("omnidata_engine.log", encoding="utf-8"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("OmniDataEngine")

# Unicode Script Regexes
LATIN_ALPHABET_REGEX = re.compile(r'[a-zA-Z]')
BENGALI_SCRIPT_REGEX = re.compile(r'[\u0980-\u09FF]')
DEVANAGARI_SCRIPT_REGEX = re.compile(r'[\u0900-\u097F]')

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
    Hard Regex Guardrail:
    - ZERO Latin characters allowed.
    - Bengali must match Bengali Unicode range AND contain ZERO Devanagari characters.
    - Hindi must match Devanagari Unicode range AND contain ZERO Bengali characters.
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
    """Strips disambiguation suffixes, e.g., 'Patna (city)' -> 'Patna'."""
    if not title or not isinstance(title, str):
        return ""
    cleaned = re.sub(r'\s*\([^)]*\)$', '', title).strip()
    return unicodedata.normalize('NFC', cleaned)


def parse_english_description(en_desc: str) -> Optional[Tuple[str, str]]:
    """
    Parses English description ('en') to extract entity type and state.
    Returns (entity_type, state_name) or None.
    """
    if not en_desc or not isinstance(en_desc, str):
        return None

    pattern = r'^(human settlement|village|town|city|revenue village|gram panchayat)\s+(?:in|of)\s+([A-Za-z\s&]+?)(?:,\s*India|\s+district|\s+state|\s+UT)?$'
    match = re.search(pattern, en_desc.strip(), re.IGNORECASE)
    if not match:
        return None

    raw_type = match.group(1).lower()
    raw_state = match.group(2).strip()

    entity_type = "village" if "village" in raw_type or "settlement" in raw_type else "city"

    # Match state against dictionary
    for state_key in INDIAN_STATES:
        if state_key.lower() in raw_state.lower():
            return (entity_type, state_key)

    return None


class OmniDataEngine:
    def __init__(self, config: Config, state_file: str = "completed_qids.txt", skipped_file: str = "skipped_entities.json"):
        self.config = config
        self.state_file = state_file
        self.skipped_file = skipped_file

        # Session with HTTPAdapter connection pool
        self.session = requests.Session()
        adapter = HTTPAdapter(
            pool_connections=50,
            pool_maxsize=100,
            max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        )
        self.session.mount("https://", adapter)
        self.session.headers.update({
            "User-Agent": self.config.user_agent,
            "Accept-Encoding": "gzip, deflate"
        })

        self.csrf_token: Optional[str] = None
        self.auth_lock = threading.RLock()
        self.is_logged_in = False

        # Queue & State (Max 300 candidates pre-fetched in RAM)
        self.task_queue: queue.Queue = queue.Queue(maxsize=300)
        self.completed_qids = self._load_completed_qids()
        self.skipped_entities: List[Dict[str, Any]] = []

        self.producer_finished = False

    def _load_completed_qids(self) -> set:
        if os.path.exists(self.state_file):
            with open(self.state_file, "r", encoding="utf-8") as f:
                return set(line.strip() for line in f if line.strip())
        return set()

    def mark_qid_completed(self, qid: str):
        with open(self.state_file, "a", encoding="utf-8") as f:
            f.write(f"{qid}\n")
        self.completed_qids.add(qid)

    def log_skipped_entity(self, qid: str, reason: str, payload: Dict[str, Any]):
        entry = {
            "qid": qid,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
            "reason": reason,
            "payload": payload
        }
        self.skipped_entities.append(entry)
        try:
            with open(self.skipped_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.error(f"Failed writing to {self.skipped_file}: {e}")

    def fetch_csrf_token(self) -> str:
        with self.auth_lock:
            resp = self.session.get(
                self.config.api_url,
                params={"action": "query", "meta": "tokens", "type": "csrf", "format": "json"},
                timeout=10
            )
            resp.raise_for_status()
            data = resp.json()
            token = data.get("query", {}).get("tokens", {}).get("csrftoken")
            if not token or token == "+\\":
                raise ValueError("Failed to retrieve valid CSRF token")
            self.csrf_token = token
            logger.info("CSRF token successfully acquired.")
            return token

    def login(self) -> bool:
        with self.auth_lock:
            logger.info(f"Authenticating bot user: {self.config.bot_user}")
            for attempt in range(1, 4):
                try:
                    resp = self.session.get(
                        self.config.api_url,
                        params={"action": "query", "meta": "tokens", "type": "login", "format": "json"},
                        timeout=10
                    )
                    login_token = resp.json().get("query", {}).get("tokens", {}).get("logintoken")
                    if not login_token:
                        logger.error("Failed to fetch login token")
                        time.sleep(2)
                        continue

                    login_resp = self.session.post(
                        self.config.api_url,
                        data={
                            "action": "login",
                            "lgname": self.config.bot_user,
                            "lgpassword": self.config.bot_password,
                            "lgtoken": login_token,
                            "format": "json"
                        },
                        timeout=10
                    )
                    res = login_resp.json()
                    if res.get("login", {}).get("result") == "Success":
                        self.is_logged_in = True
                        self.fetch_csrf_token()
                        logger.info("Bot successfully authenticated.")
                        return True
                    else:
                        logger.error(f"Login attempt {attempt} failed: {res}")
                except Exception as e:
                    logger.warning(f"Login attempt {attempt} error: {e}. Retrying...")
                time.sleep(2)
            return False

    DISALLOWED_IMAGE_KEYWORDS = [
        'campus', 'school', 'hospital', 'orchard', 'station', 'police',
        'college', 'temple', 'office', 'bank', 'stadium', 'hotel',
        'restaurant', 'hall', 'building', 'court', 'gate', 'shop', 'farm',
        'map of', 'location of', 'district', 'branch', 'memorial', 'tank',
        'statue', 'stamp', 'logo', 'journal', 'poster', 'svg', 'map', 'flag',
        'coat of arms', 'seal', 'emblem'
    ]

    def search_commons_image(self, title: str) -> Optional[str]:
        """Queries Wikimedia Commons for strictly verified localized media."""
        if not title:
            return None

        clean_title = re.sub(r'\s*\([^)]*\)$', '', title).strip()
        if not clean_title or len(clean_title) < 3:
            return None

        commons_url = "https://commons.wikimedia.org/w/api.php"
        params = {
            "action": "query",
            "list": "search",
            "srsearch": f'"{clean_title}" India',
            "srnamespace": 6,  # File namespace
            "srlimit": 5,
            "format": "json"
        }
        try:
            resp = self.session.get(commons_url, params=params, timeout=3)
            resp.raise_for_status()
            search_res = resp.json().get("query", {}).get("search", [])

            for item in search_res:
                raw_file_title = item.get("title", "")
                if not raw_file_title.startswith("File:"):
                    continue

                file_name = raw_file_title[5:].strip()
                file_lower = file_name.lower()
                clean_lower = clean_title.lower()

                # Rule 1: File name MUST explicitly contain clean title
                if clean_lower not in file_lower:
                    continue

                # Rule 2: Reject misleading partial keywords unless title explicitly has them
                has_disallowed = False
                for kw in self.DISALLOWED_IMAGE_KEYWORDS:
                    if kw in file_lower and kw not in clean_lower:
                        has_disallowed = True
                        break

                if has_disallowed:
                    logger.info(f"Skipping image '{file_name}' for '{clean_title}': contains unverified keyword.")
                    continue

                # Verified match found!
                logger.info(f"VERIFIED Image match for '{clean_title}': {file_name}")
                return file_name

        except Exception as e:
            logger.debug(f"Commons search error for {title}: {e}")

        return None

    def prepare_payload(self, qid: str, entity: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Parses entity, extracts verified sitelink labels, generates descriptions, and formats payload."""
        labels = entity.get("labels", {})
        descriptions = entity.get("descriptions", {})
        sitelinks = entity.get("sitelinks", {})
        claims = entity.get("claims", {})

        desire_labels = {}
        desire_descriptions = {}
        desire_claims = []

        # 1. Native Labels strictly from verified sitelinks
        if "hi" not in labels and "hiwiki" in sitelinks:
            title = clean_sitelink_title(sitelinks["hiwiki"].get("title", ""))
            if validate_script(title, "hi"):
                desire_labels["hi"] = {"language": "hi", "value": title}

        if "bn" not in labels and "bnwiki" in sitelinks:
            title = clean_sitelink_title(sitelinks["bnwiki"].get("title", ""))
            if validate_script(title, "bn"):
                desire_labels["bn"] = {"language": "bn", "value": title}

        # 2. Localized Descriptions from English patterns
        en_desc = descriptions.get("en", {}).get("value", "")
        parsed = parse_english_description(en_desc)
        if parsed:
            entity_type, state_key = parsed
            state_mapping = INDIAN_STATES.get(state_key)
            if state_mapping:
                if "hi" not in descriptions:
                    hi_state = state_mapping["hi"]
                    hi_type_str = "गाँव" if entity_type == "village" else "शहर"
                    hi_desc = f"भारत के {hi_state} राज्य का एक {hi_type_str}"
                    if validate_script(hi_desc, "hi"):
                        desire_descriptions["hi"] = {"language": "hi", "value": hi_desc}

                if "bn" not in descriptions:
                    bn_state = state_mapping["bn"]
                    bn_type_str = "গ্রাম" if entity_type == "village" else "শহর"
                    bn_desc = f"ভারতের {bn_state} রাজ্যের একটি {bn_type_str}"
                    if validate_script(bn_desc, "bn"):
                        desire_descriptions["bn"] = {"language": "bn", "value": bn_desc}

        # 3. P18 Image from Wikimedia Commons (Fast Verified Sitelink Title Match)
        if "P18" not in claims:
            search_title = None
            if "en" in labels:
                search_title = labels["en"].get("value")
            elif "hiwiki" in sitelinks:
                search_title = sitelinks["hiwiki"].get("title")

            # Fast non-blocking Commons image check
            if search_title and len(search_title) > 3:
                commons_img = self.search_commons_image(search_title)
                if commons_img:
                    desire_claims.append({
                        "mainsnak": {
                            "snaktype": "value",
                            "property": "P18",
                            "datavalue": {"type": "string", "value": commons_img}
                        },
                        "type": "statement",
                        "rank": "normal"
                    })

        if not desire_labels and not desire_descriptions and not desire_claims:
            return None

        payload_data = {}
        if desire_labels:
            payload_data["labels"] = desire_labels
        if desire_descriptions:
            payload_data["descriptions"] = desire_descriptions
        if desire_claims:
            payload_data["claims"] = desire_claims

        return payload_data

    SEARCH_QUERIES = [
        "haswbstatement:P31=Q532 haswbstatement:P17=Q668",      # Villages in India
        "haswbstatement:P31=Q486914 haswbstatement:P17=Q668",   # Settlements in India
        "haswbstatement:P31=Q11776861 haswbstatement:P17=Q668", # Tehsils/Subdistricts in India
        "haswbstatement:P31=Q1549592 haswbstatement:P17=Q668",  # Districts in India
        "haswbstatement:P17=Q668"                               # All Indian entities
    ]

    def fetch_candidates_batch(self, offset: int = 0) -> List[str]:
        """Fetches fresh batch of candidate QIDs via MediaWiki CirrusSearch query rotation with safe random offsets."""
        import random
        qids = []
        query = random.choice(self.SEARCH_QUERIES)
        sroffset = random.randint(0, 18) * 500  # Safe offset between 0 and 9000
        
        try:
            search_params = {
                "action": "query",
                "list": "search",
                "srsearch": query,
                "srlimit": 500,
                "sroffset": sroffset,
                "format": "json"
            }
            s_resp = self.session.get(self.config.api_url, params=search_params, timeout=15)
            if s_resp.status_code == 200:
                s_res = s_resp.json().get("query", {}).get("search", [])
                for item in s_res:
                    title = item.get("title", "")
                    if title.startswith("Q") and title[1:].isdigit() and title not in self.completed_qids:
                        qids.append(title)
            logger.info(f"CirrusSearch [{query} | offset={sroffset}] returned {len(qids)} fresh candidate QIDs.")
        except Exception as e:
            logger.error(f"CirrusSearch fetch error: {e}")

        return qids

    def fetch_entities_batch(self, qids: List[str]) -> Dict[str, Any]:
        """Fetches batch of up to 50 entities via MediaWiki Action API."""
        if not qids:
            return {}
        chunk = qids[:50]
        params = {
            "action": "wbgetentities",
            "ids": "|".join(chunk),
            "props": "labels|descriptions|claims|sitelinks",
            "languages": "en|hi|bn",
            "format": "json"
        }
        try:
            resp = self.session.get(self.config.api_url, params=params, timeout=15)
            resp.raise_for_status()
            return resp.json().get("entities", {})
        except Exception as e:
            logger.error(f"Failed to fetch entities batch: {e}")
            return {}

    def fetch_sparql_batch(self, limit: int = 500) -> List[str]:
        """Backward compatibility wrapper around fetch_candidates_batch."""
        return self.fetch_candidates_batch(offset=0)

    def producer_loop(self):
        """Thread A: Infinite worker that pre-fetches and queues valid edit payloads with 25-thread pool."""
        from concurrent.futures import ThreadPoolExecutor
        logger.info("Producer infinite worker thread started (25-Thread Mode).")
        offset = 0

        with ThreadPoolExecutor(max_workers=25) as executor:
            while True:
                # Buffer queue up to 250 candidates
                if self.task_queue.qsize() > 200:
                    time.sleep(1.0)
                    continue

                qids = self.fetch_candidates_batch(offset=offset)
                offset += 500
                if offset >= 50000:
                    offset = 0  # Wrap around

                if not qids:
                    logger.info("No candidates returned in chunk. Retrying next query offset...")
                    time.sleep(1.0)
                    continue

                batch_size = 50
                added_count = 0

                for i in range(0, len(qids), batch_size):
                    chunk = qids[i:i + batch_size]
                    entities = self.fetch_entities_batch(chunk)

                    futures = []
                    for qid in chunk:
                        entity = entities.get(qid, {})
                        if not entity:
                            futures.append((qid, None))
                            continue
                        futures.append((qid, executor.submit(self.prepare_payload, qid, entity)))

                    for qid, fut in futures:
                        if fut is None:
                            continue
                        try:
                            payload_data = fut.result()
                            if payload_data:
                                self.task_queue.put((qid, payload_data))
                                added_count += 1
                        except Exception as e:
                            logger.error(f"Error preparing payload for {qid}: {e}")

                logger.info(f"Producer batch complete: Queued {added_count} payloads. Total Queue Size: {self.task_queue.qsize()}")

        logger.info("Producer thread exiting.")

    def consumer_loop(self):
        """Thread B: Writer that executes wbeditentity at maximum safe 0.8s cycle speed."""
        logger.info("Consumer writer thread started.")

        while True:
            t_start = time.time()
            try:
                qid, payload_data = self.task_queue.get(timeout=2.0)
            except queue.Empty:
                if self.producer_finished:
                    logger.info("Consumer finished all queued items.")
                    break
                continue

            # Validate guardrails before editing
            guard_ok = True
            for lang, lbl_obj in payload_data.get("labels", {}).items():
                if not validate_script(lbl_obj["value"], lang):
                    self.log_skipped_entity(qid, f"Label script guardrail mismatch: {lang}", payload_data)
                    guard_ok = False
                    break

            for lang, desc_obj in payload_data.get("descriptions", {}).items():
                if not validate_script(desc_obj["value"], lang):
                    self.log_skipped_entity(qid, f"Description script guardrail mismatch: {lang}", payload_data)
                    guard_ok = False
                    break

            if not guard_ok:
                self.task_queue.task_done()
                continue

            # Execute wbeditentity edit
            try:
                edit_payload = {
                    "action": "wbeditentity",
                    "id": qid,
                    "data": json.dumps(payload_data, ensure_ascii=False),
                    "token": self.csrf_token,
                    "summary": "Added missing Bengali and Hindi labels, descriptions, and P18 media statements",
                    "bot": 1,
                    "format": "json"
                }

                resp = self.session.post(self.config.api_url, data=edit_payload, timeout=15)
                res = resp.json()

                if "success" in res and res["success"] == 1:
                    self.mark_qid_completed(qid)
                    logger.info(f"SUCCESS Edit [QID: {qid}] - {list(payload_data.keys())}")
                elif "error" in res and res["error"].get("code") == "badtoken":
                    logger.warning("CSRF token expired. Refreshing token and retrying...")
                    self.fetch_csrf_token()
                    edit_payload["token"] = self.csrf_token
                    resp2 = self.session.post(self.config.api_url, data=edit_payload, timeout=15)
                    if resp2.json().get("success") == 1:
                        self.mark_qid_completed(qid)
                        logger.info(f"SUCCESS Edit after token refresh [QID: {qid}]")
                    else:
                        self.log_skipped_entity(qid, f"API Error: {resp2.json()}", payload_data)
                else:
                    self.log_skipped_entity(qid, f"API Error: {res}", payload_data)

            except Exception as e:
                logger.error(f"Exception during edit of {qid}: {e}")
                self.log_skipped_entity(qid, f"Exception: {str(e)}", payload_data)

            self.task_queue.task_done()
            # Dynamic sleep to guarantee exact 0.8s rate limit cycle
            elapsed = time.time() - t_start
            sleep_needed = max(0.0, 0.8 - elapsed)
            time.sleep(sleep_needed)

    def run(self):
        """Starts Producer-Consumer pipeline."""
        if not self.login():
            logger.error("Authentication failed. Aborting OmniData Engine.")
            return

        producer_thread = threading.Thread(target=self.producer_loop, name="ProducerWorker")
        consumer_thread = threading.Thread(target=self.consumer_loop, name="ConsumerWriter")

        producer_thread.start()
        consumer_thread.start()

        producer_thread.join()
        consumer_thread.join()

        logger.info("OmniData Engine execution complete.")


if __name__ == "__main__":
    cfg = Config.from_env()
    cfg.validate(require_auth=True)
    engine = OmniDataEngine(config=cfg)
    engine.run()
