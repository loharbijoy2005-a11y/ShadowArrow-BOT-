import os
import re
import sys
import time
import json
import logging
import unicodedata
from typing import Dict, List, Optional, Tuple, Any, Set
import requests
from dotenv import load_dotenv
from indic_transliteration import sanscript

load_dotenv()

# API & Credentials Configuration
API_URL = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
BOT_USER = os.getenv("WIKIDATA_BOT_USER", "SHADOWARROW 2026@ShadowBot").strip()
BOT_PASSWORD = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()

USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026) python-requests"
RATE_LIMIT_DELAY = 1.8  # 1.8 seconds delay between repairs
EDIT_SUMMARY = "Auditing and fixing localized descriptions/labels"

# Regex Guardrails
BENGALI_SCRIPT_REGEX = re.compile(r'[\u0980-\u09FF]')
DEVANAGARI_SCRIPT_REGEX = re.compile(r'[\u0900-\u097F]')
LATIN_ALPHABET_REGEX = re.compile(r'[a-zA-Z]')

# Known bad strings to detect and repair
BAD_TEXT_PATTERNS = [
    r'Dynamic NLP Bot',
    r'আন্তর্জাতিক নদী',
    r'अंतर्राष्ट्रीय नदी',
    r'अंतरराष्ट्रीय नदी',
    r'भारतीय शहर'
]

# Configure UTF-8 stdout/stderr
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

logging.basicConfig(
    level=logging.INFO,
    format="%(message)s",
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("WikidataCleanupRepair")

# State Mapping Table
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
    "Madhya Pradesh": {"hi": "मध्य प्रदेश", "bn": "मध्यप्रदेश"},
    "Maharashtra": {"hi": "महाराष्ट्र", "bn": "মহারাষ্ট্র"},
    "Manipur": {"hi": "मणिपुर", "bn": "মণিপুর"},
    "Meghalaya": {"hi": "मेघालय", "bn": "মেঘালয়"},
    "Mizoram": {"hi": "मिजोरम", "bn": "মিজোরাম"},
    "Nagaland": {"hi": "नागालैंड", "bn": "নাগাল্যান্ড"},
    "Odisha": {"hi": "ओडिशा", "bn": "ওড়িশা"},
    "Orissa": {"hi": "ओडिशा", "bn": "ওড়িশা"},
    "Punjab": {"hi": "पंजाब", "bn": "পাঞ্জাব"},
    "Rajasthan": {"hi": "राजस्थान", "bn": "राजस्थान"},
    "Sikkim": {"hi": "सिक्किम", "bn": "সিকিম"},
    "Tamil Nadu": {"hi": "तमिलनाडु", "bn": "তামিলনাড়ু"},
    "Telangana": {"hi": "तेलंगाना", "bn": "तेलेंगाना"},
    "Tripura": {"hi": "त्रिपुरा", "bn": "त्रिपुरा"},
    "Uttar Pradesh": {"hi": "उत्तर प्रदेश", "bn": "उत्तरप्रदेश"},
    "Uttarakhand": {"hi": "उत्तराखंड", "bn": "উত্তরাখণ্ড"},
    "West Bengal": {"hi": "पश्चिम बंगाल", "bn": "পশ্চিমবঙ্গ"},
    "Delhi": {"hi": "दिल्ली", "bn": "দিল্লি"},
    "Jammu and Kashmir": {"hi": "जम्मू और कश्मीर", "bn": "জম্মু ও কাশ্মীর"},
    "Ladakh": {"hi": "लद्दाख", "bn": "লাদাখ"},
    "Puducherry": {"hi": "पुदुचेरी", "bn": "পুদুচেরি"},
    "Chandigarh": {"hi": "चंडीगढ़", "bn": "चंडीगढ़"}
}

def validate_script(text: str, lang: str) -> bool:
    if not text or not isinstance(text, str):
        return False
    if LATIN_ALPHABET_REGEX.search(text):
        return False
    if lang == "bn":
        return bool(BENGALI_SCRIPT_REGEX.search(text))
    elif lang == "hi":
        return bool(DEVANAGARI_SCRIPT_REGEX.search(text))
    return False

def transliterate_label(en_label: str, target_lang: str) -> Optional[str]:
    if not en_label or not isinstance(en_label, str):
        return None
    clean_label = en_label.strip()
    try:
        if target_lang == "hi":
            translit = sanscript.transliterate(clean_label, sanscript.ITRANS, sanscript.DEVANAGARI)
        elif target_lang == "bn":
            translit = sanscript.transliterate(clean_label, sanscript.ITRANS, sanscript.BENGALI)
        else:
            return None
        translit = unicodedata.normalize('NFC', translit).strip()
        if validate_script(translit, target_lang):
            return translit
    except Exception:
        pass
    return None

def parse_english_description(en_desc: str) -> Optional[Tuple[str, str]]:
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

class WikidataCleanupRepairBot:
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.csrf_token: Optional[str] = None
        # Extract base username for usercontribs (e.g. "SHADOWARROW 2026")
        self.target_user = BOT_USER.split('@')[0].strip()

    def login(self) -> bool:
        logger.info(f"[Auth] Logging in as '{BOT_USER}'...")
        res = self.session.get(API_URL, params={
            "action": "query",
            "meta": "tokens",
            "type": "login",
            "format": "json"
        }, timeout=30).json()

        login_token = res.get("query", {}).get("tokens", {}).get("logintoken")
        if not login_token:
            logger.error("[Auth] Failed to acquire login token.")
            return False

        log_res = self.session.post(API_URL, data={
            "action": "login",
            "lgname": BOT_USER,
            "lgpassword": BOT_PASSWORD,
            "lgtoken": login_token,
            "format": "json"
        }, timeout=30).json()

        if log_res.get("login", {}).get("result") != "Success":
            logger.error(f"[Auth] Login failed: {log_res}")
            return False

        csrf_res = self.session.get(API_URL, params={
            "action": "query",
            "meta": "tokens",
            "type": "csrf",
            "format": "json"
        }, timeout=30).json()

        self.csrf_token = csrf_res.get("query", {}).get("tokens", {}).get("csrftoken")
        if not self.csrf_token:
            logger.error("[Auth] Failed to acquire CSRF token.")
            return False

        logger.info("[Auth] Successfully logged in and acquired CSRF edit token.")
        return True

    def fetch_user_contributions(self, limit: int = 500) -> List[str]:
        logger.info(f"[Fetch] Querying usercontribs for user '{self.target_user}' (limit={limit})...")
        qids: Set[str] = set()
        uccontinue = None

        while len(qids) < limit:
            params = {
                "action": "query",
                "list": "usercontribs",
                "ucuser": self.target_user,
                "uclimit": "500",
                "ucnamespace": "0",
                "format": "json"
            }
            if uccontinue:
                params["uccontinue"] = uccontinue

            res = self.session.get(API_URL, params=params, timeout=30).json()
            contribs = res.get("query", {}).get("usercontribs", [])

            for item in contribs:
                title = item.get("title", "")
                if title.startswith("Q") and title[1:].isdigit():
                    qids.add(title)

            uccontinue = res.get("continue", {}).get("uccontinue")
            if not uccontinue or not contribs:
                break

        qids_list = sorted(list(qids))
        logger.info(f"[Fetch] Found {len(qids_list)} unique QIDs edited by '{self.target_user}'.")
        return qids_list

    def is_bad_value(self, text: str, lang: str) -> bool:
        if not text or not isinstance(text, str):
            return False
        if LATIN_ALPHABET_REGEX.search(text):
            return True
        for bad_pat in BAD_TEXT_PATTERNS:
            if re.search(bad_pat, text, re.IGNORECASE):
                return True
        if not validate_script(text, lang):
            return True
        return False

    def inspect_and_repair_entity(self, qid: str) -> bool:
        params = {
            "action": "wbgetentities",
            "ids": qid,
            "props": "labels|descriptions|sitelinks",
            "sitefilter": "bnwiki|hiwiki",
            "format": "json"
        }
        res = self.session.get(API_URL, params=params, timeout=30).json()
        entities = res.get("entities", {})
        entity = entities.get(qid, {})

        if not entity or "missing" in entity:
            return False

        labels = entity.get("labels", {})
        descriptions = entity.get("descriptions", {})
        sitelinks = entity.get("sitelinks", {})

        en_label = labels.get("en", {}).get("value", "")
        en_desc = descriptions.get("en", {}).get("value", "")

        hi_label_val = labels.get("hi", {}).get("value", "")
        bn_label_val = labels.get("bn", {}).get("value", "")

        hi_desc_val = descriptions.get("hi", {}).get("value", "")
        bn_desc_val = descriptions.get("bn", {}).get("value", "")

        bad_fields = []
        payload_labels = {}
        payload_descriptions = {}

        # 1. Inspect & Repair Hindi Label
        if hi_label_val and self.is_bad_value(hi_label_val, "hi"):
            bad_fields.append("hi label")
            new_hi_label = None
            hi_site = sitelinks.get("hiwiki", {}).get("title", "").strip()
            if hi_site:
                clean_hi = re.sub(r'\s*\([^)]*\)$', '', hi_site).strip()
                if validate_script(clean_hi, "hi"):
                    new_hi_label = clean_hi
            if not new_hi_label and en_label:
                new_hi_label = transliterate_label(en_label, "hi")

            if new_hi_label and validate_script(new_hi_label, "hi"):
                payload_labels["hi"] = {"language": "hi", "value": new_hi_label}
            else:
                payload_labels["hi"] = {"language": "hi", "remove": ""}

        # 2. Inspect & Repair Bengali Label
        if bn_label_val and self.is_bad_value(bn_label_val, "bn"):
            bad_fields.append("bn label")
            new_bn_label = None
            bn_site = sitelinks.get("bnwiki", {}).get("title", "").strip()
            if bn_site:
                clean_bn = re.sub(r'\s*\([^)]*\)$', '', bn_site).strip()
                if validate_script(clean_bn, "bn"):
                    new_bn_label = clean_bn
            if not new_bn_label and en_label:
                new_bn_label = transliterate_label(en_label, "bn")

            if new_bn_label and validate_script(new_bn_label, "bn"):
                payload_labels["bn"] = {"language": "bn", "value": new_bn_label}
            else:
                payload_labels["bn"] = {"language": "bn", "remove": ""}

        # 3. Parse state & generate proper localized descriptions if possible
        parsed_nlp = parse_english_description(en_desc)
        correct_descs = None
        if parsed_nlp:
            entity_type, state_name = parsed_nlp
            correct_descs = generate_localized_descriptions(entity_type, state_name)

        # 4. Inspect & Repair Hindi Description
        if hi_desc_val and self.is_bad_value(hi_desc_val, "hi"):
            bad_fields.append("hi description")
            if correct_descs and "hi" in correct_descs:
                payload_descriptions["hi"] = {"language": "hi", "value": correct_descs["hi"]}
            else:
                payload_descriptions["hi"] = {"language": "hi", "remove": ""}

        # 5. Inspect & Repair Bengali Description
        if bn_desc_val and self.is_bad_value(bn_desc_val, "bn"):
            bad_fields.append("bn description")
            if correct_descs and "bn" in correct_descs:
                payload_descriptions["bn"] = {"language": "bn", "value": correct_descs["bn"]}
            else:
                payload_descriptions["bn"] = {"language": "bn", "remove": ""}

        if not bad_fields and not payload_labels and not payload_descriptions:
            logger.info(f"[AUDITED] QID: {qid} | Clean (No bad data detected).")
            return False

        payload = {}
        if payload_labels:
            payload["labels"] = payload_labels
        if payload_descriptions:
            payload["descriptions"] = payload_descriptions

        edit_params = {
            "action": "wbeditentity",
            "id": qid,
            "token": self.csrf_token,
            "summary": EDIT_SUMMARY,
            "data": json.dumps(payload),
            "format": "json"
        }

        time.sleep(RATE_LIMIT_DELAY)
        write_res = self.session.post(API_URL, data=edit_params, timeout=30).json()

        if write_res.get("success") == 1:
            logger.info(f"[FIXED] QID: {qid} | Replaced bad fields successfully ({', '.join(bad_fields)}).")
            return True
        else:
            err_msg = write_res.get("error", {}).get("info", "Unknown error")
            logger.error(f"[ERROR] Failed to repair QID {qid}: {err_msg}")
            return False

    def run(self):
        logger.info("==================================================")
        logger.info("   WIKIDATA CLEANUP & REPAIR BOT (SHADOWARROW 2026)")
        logger.info("==================================================")

        if not self.login():
            logger.error("Authentication failed. Exiting.")
            sys.exit(1)

        qids = self.fetch_user_contributions(limit=500)
        if not qids:
            logger.info("No contributions found for account. Exiting.")
            return

        repaired_count = 0
        clean_count = 0

        for idx, qid in enumerate(qids, 1):
            try:
                fixed = self.inspect_and_repair_entity(qid)
                if fixed:
                    repaired_count += 1
                else:
                    clean_count += 1
            except Exception as e:
                logger.error(f"[EXCEPT] Error processing QID {qid}: {e}")

        logger.info("==================================================")
        logger.info(f"[COMPLETE] Audit finished! Total QIDs: {len(qids)} | Fixed: {repaired_count} | Clean: {clean_count}")
        logger.info("==================================================")

if __name__ == "__main__":
    bot = WikidataCleanupRepairBot()
    bot.run()
