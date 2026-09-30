"""
Configuration loader for Wikidata Bot.
Reads environment variables using python-dotenv with fallback defaults and validation.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from dotenv import load_dotenv

# Load .env file if available
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

@dataclass
class Config:
    bot_user: str
    bot_password: str
    api_url: str
    user_agent: str
    rate_limit_delay: float
    maxlag: int
    max_retries: int

    @classmethod
    def from_env(cls) -> "Config":
        bot_user = os.getenv("WIKIDATA_BOT_USER", "").strip()
        bot_password = os.getenv("WIKIDATA_BOT_PASSWORD", "").strip()
        api_url = os.getenv("WIKIDATA_API_URL", "https://www.wikidata.org/w/api.php").strip()
        user_agent = os.getenv(
            "USER_AGENT",
            "ShadowBot/1.0 (contact: User:SHADOWARROW 2026) python-requests/2.34.2"
        ).strip()
        
        rate_limit_delay = float(os.getenv("RATE_LIMIT_DELAY", "2.5"))
        maxlag = int(os.getenv("MAXLAG", "5"))
        max_retries = int(os.getenv("MAX_RETRIES", "5"))

        # Safety enforcement for rate limit
        if rate_limit_delay < 2.0:
            rate_limit_delay = 2.0

        return cls(
            bot_user=bot_user,
            bot_password=bot_password,
            api_url=api_url,
            user_agent=user_agent,
            rate_limit_delay=rate_limit_delay,
            maxlag=maxlag,
            max_retries=max_retries
        )

    def validate(self, require_auth: bool = True) -> None:
        """Validates critical credentials and settings."""
        if require_auth:
            if not self.bot_user:
                raise ValueError("WIKIDATA_BOT_USER is missing or empty in .env")
            if not self.bot_password:
                raise ValueError("WIKIDATA_BOT_PASSWORD is missing or empty in .env")
        if not self.api_url:
            raise ValueError("WIKIDATA_API_URL is missing or empty in .env")
        if not self.user_agent:
            raise ValueError("USER_AGENT is missing or empty in .env")
