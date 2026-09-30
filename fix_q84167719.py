"""
Fix Script: Reverts/removes English label copied into Bangla on Q84167719.
"""

import sys
import time
import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://www.wikidata.org/w/api.php"
BOT_USER = "SHADOWARROW 2026@ShadowBot"
BOT_PASSWORD = ""
USER_AGENT = "ShadowBot/1.0 (https://www.wikidata.org/wiki/User:SHADOWARROW_2026; contact: local-dev) python-requests"

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

session = requests.Session()
session.headers.update({"User-Agent": USER_AGENT})

def login():
    res = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "login", "format": "json"}).json()
    token = res.get("query", {}).get("tokens", {}).get("logintoken")
    
    session.post(API_URL, data={
        "action": "login",
        "lgname": BOT_USER,
        "lgpassword": BOT_PASSWORD,
        "lgtoken": token,
        "format": "json"
    })
    
    csrf_res = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "csrf", "format": "json"}).json()
    return csrf_res.get("query", {}).get("tokens", {}).get("csrftoken")

def fix_item():
    csrf_token = login()
    print("LoggedIn. Clearing English text from Bangla label on Q84167719...")
    
    for attempt in range(1, 6):
        res_bn = session.post(API_URL, data={
            "action": "wbsetlabel",
            "id": "Q84167719",
            "language": "bn",
            "value": "",
            "summary": "Reverting automated edit copying English label into Bangla",
            "token": csrf_token,
            "bot": "1",
            "format": "json"
        }).json()
        print(f"Attempt {attempt} - Clear 'bn' label result: {res_bn}")
        if res_bn.get("success") == 1:
            print("Successfully cleared Bangla label on Q84167719!")
            break
        print("Rate throttled. Pausing 15 seconds before retry...")
        time.sleep(15)

if __name__ == "__main__":
    fix_item()
