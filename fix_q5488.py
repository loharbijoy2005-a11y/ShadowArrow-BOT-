"""
Emergency Fix Script: Clears incorrect description from Q5488 (aplasia) on Wikidata.
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
    # Step 1: Login Token
    res = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "login", "format": "json"}).json()
    token = res.get("query", {}).get("tokens", {}).get("logintoken")
    
    # Step 2: Login
    session.post(API_URL, data={
        "action": "login",
        "lgname": BOT_USER,
        "lgpassword": BOT_PASSWORD,
        "lgtoken": token,
        "format": "json"
    })
    
    # Step 3: CSRF Token
    csrf_res = session.get(API_URL, params={"action": "query", "meta": "tokens", "type": "csrf", "format": "json"}).json()
    return csrf_res.get("query", {}).get("tokens", {}).get("csrftoken")

def fix_item():
    csrf_token = login()
    print("LoggedIn. Fixing Q5488 (aplasia)...")
    
    # Clear incorrect 'bn' description on Q5488
    res_bn = session.post(API_URL, data={
        "action": "wbsetdescription",
        "id": "Q5488",
        "language": "bn",
        "value": "",
        "summary": "Reverting incorrect automated description edit on Q5488",
        "token": csrf_token,
        "bot": "1",
        "format": "json"
    }).json()
    print(f"Clear 'bn' description result: {res_bn}")
    
    time.sleep(3.0)
    
    # Clear incorrect 'hi' description on Q5488
    res_hi = session.post(API_URL, data={
        "action": "wbsetdescription",
        "id": "Q5488",
        "language": "hi",
        "value": "",
        "summary": "Reverting incorrect automated description edit on Q5488",
        "token": csrf_token,
        "bot": "1",
        "format": "json"
    }).json()
    print(f"Clear 'hi' description result: {res_hi}")

if __name__ == "__main__":
    fix_item()
