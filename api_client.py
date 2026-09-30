"""
MediaWiki API Client for Wikidata.
Handles 2-stage authentication, CSRF token management, rate-limiting,
maxlag error handling, exponential backoff, and session persistence.
"""

import time
import random
import logging
from typing import Dict, Any, Optional
import requests
from requests.exceptions import RequestException

from config import Config

logger = logging.getLogger("WikidataBot.APIClient")

class MediaWikiClient:
    def __init__(self, config: Config):
        self.config = config
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})
        
        self.csrf_token: Optional[str] = None
        self.last_write_time: float = 0.0
        self.is_logged_in: bool = False

    def _rate_limit(self) -> None:
        """Enforces rate-limiting delay between POST / write operations."""
        elapsed = time.time() - self.last_write_time
        if elapsed < self.config.rate_limit_delay:
            sleep_time = self.config.rate_limit_delay - elapsed
            logger.debug(f"Rate limiting: sleeping for {sleep_time:.2f}s")
            time.sleep(sleep_time)

    def request(
        self,
        method: str,
        params: Optional[Dict[str, Any]] = None,
        data: Optional[Dict[str, Any]] = None,
        is_write: bool = False
    ) -> Dict[str, Any]:
        """
        Executes HTTP requests with retry logic, maxlag checks, and rate-limiting.
        """
        params = params or {}
        data = data or {}

        # Set default format and maxlag
        if "format" not in params:
            params["format"] = "json"
        if "formatversion" not in params:
            params["formatversion"] = "2"
        if "maxlag" not in params and is_write:
            params["maxlag"] = self.config.maxlag

        if is_write:
            self._rate_limit()

        attempt = 0
        backoff = 2.0

        while attempt <= self.config.max_retries:
            attempt += 1
            try:
                start_time = time.time()
                if method.upper() == "POST":
                    response = self.session.post(self.config.api_url, params=params, data=data, timeout=30)
                else:
                    response = self.session.get(self.config.api_url, params=params, timeout=30)

                latency = time.time() - start_time
                logger.debug(f"HTTP {response.status_code} ({latency:.3f}s) for params={params}")

                if is_write:
                    self.last_write_time = time.time()

                # Handle HTTP Status errors
                if response.status_code in (429, 500, 502, 503, 504):
                    retry_after = response.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        wait_time = float(retry_after)
                    else:
                        wait_time = backoff + random.uniform(0.5, 1.5)

                    logger.warning(
                        f"Received HTTP {response.status_code}. Retrying in {wait_time:.2f}s "
                        f"(Attempt {attempt}/{self.config.max_retries})"
                    )
                    time.sleep(wait_time)
                    backoff *= 2.0
                    continue

                response.raise_for_status()
                res_json = response.json()

                # Check for MediaWiki API Level Errors / Maxlag
                if "error" in res_json:
                    err = res_json["error"]
                    err_code = err.get("code", "")
                    err_info = err.get("info", "")

                    if err_code == "maxlag":
                        retry_after = response.headers.get("Retry-After", "5")
                        try:
                            wait_time = float(retry_after)
                        except ValueError:
                            wait_time = 5.0
                        logger.warning(f"MediaWiki maxlag exceeded ({err_info}). Waiting {wait_time}s...")
                        time.sleep(wait_time)
                        continue

                    if err_code in ("readonly", "ratelimited"):
                        wait_time = backoff + random.uniform(1.0, 3.0)
                        logger.warning(f"MediaWiki returned error '{err_code}': {err_info}. Retrying in {wait_time:.2f}s...")
                        time.sleep(wait_time)
                        backoff *= 2.0
                        continue

                    if err_code in ("badtoken", "notloggedin") and is_write and attempt < self.config.max_retries:
                        logger.warning(f"Invalid token or session lost ({err_code}). Re-authenticating...")
                        self.login()
                        if data and "token" in data and self.csrf_token:
                            data["token"] = self.csrf_token
                        continue

                return res_json

            except (RequestException, ValueError) as e:
                wait_time = backoff + random.uniform(0.5, 1.5)
                logger.warning(
                    f"Network / parsing error: {e}. Retrying in {wait_time:.2f}s "
                    f"(Attempt {attempt}/{self.config.max_retries})"
                )
                time.sleep(wait_time)
                backoff *= 2.0

        raise RuntimeError(f"Max retries ({self.config.max_retries}) exceeded for MediaWiki request.")

    def login(self) -> bool:
        """
        Performs 2-Stage authentication with MediaWiki Action API.
        Step 1: Fetch logintoken
        Step 2: POST action=login with credentials
        Step 3: Fetch csrftoken for editing
        """
        logger.info(f"Authenticating as bot user: '{self.config.bot_user}'...")

        # Step 1: Request logintoken
        token_res = self.request("GET", params={"action": "query", "meta": "tokens", "type": "login"})
        login_token = token_res.get("query", {}).get("tokens", {}).get("logintoken")

        if not login_token:
            raise RuntimeError("Failed to obtain logintoken from MediaWiki API.")

        # Step 2: Authenticate via POST action=login
        login_payload = {
            "action": "login",
            "lgname": self.config.bot_user,
            "lgpassword": self.config.bot_password,
            "lgtoken": login_token
        }
        login_res = self.request("POST", data=login_payload)
        login_status = login_res.get("login", {}).get("result")

        if login_status != "Success":
            reason = login_res.get("login", {}).get("reason", "Unknown authentication failure")
            raise RuntimeError(f"Bot login failed: {login_status} - {reason}")

        self.is_logged_in = True
        logger.info("Successfully authenticated with MediaWiki API!")

        # Step 3: Fetch CSRF token for edit operations
        self.refresh_csrf_token()
        return True

    def refresh_csrf_token(self) -> str:
        """Fetches a fresh CSRF token required for write operations."""
        logger.debug("Fetching CSRF edit token...")
        token_res = self.request("GET", params={"action": "query", "meta": "tokens", "type": "csrf"})
        csrf_token = token_res.get("query", {}).get("tokens", {}).get("csrftoken")

        if not csrf_token or csrf_token == "+\\":
            raise RuntimeError("Obtained invalid CSRF token. Check bot permissions.")

        self.csrf_token = csrf_token
        logger.debug("CSRF token successfully acquired.")
        return csrf_token
