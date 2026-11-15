"""Application Configuration and Named Constants Module.

Reads configuration from environment variables with safe defaults and establishes
domain constants used across the application.
"""

import logging
import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file from project root if it exists
BASE_DIR: Path = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")

# ---------------------------------------------------------------------------
# Named Domain Constants (Centralized Configuration)
# ---------------------------------------------------------------------------
BCRYPT_ROUNDS: int = 12
DEFAULT_AUTH_MAX_ATTEMPTS: int = 5
DEFAULT_AUTH_LOCKOUT_SECONDS: int = 60
SESSION_COOKIE_NAME: str = "carenest_session"
SESSION_TOKEN_EXPIRATION_SECONDS: int = 86400 * 7  # 7 days

CARE_ID_PREFIX: str = "CARE"
CARE_ID_RANDOM_DIGITS: int = 4
PASSCODE_RANDOM_DIGITS: int = 4
PASSCODE_ROLE_PREFIXES: dict[str, str] = {
    "elder": "ELD",
    "caretaker": "CAR",
    "family": "FAM",
}

REMINDER_DOSE_FORWARD_HOURS: int = 2
REMINDER_APPOINTMENT_FORWARD_HOURS: int = 48
ADHERENCE_LOOKBACK_DAYS: int = 7
ADHERENCE_DEFAULT_PERCENTAGE: int = 100
RECENT_HISTORY_LIMIT: int = 10
DEFAULT_SCHEDULE_TIMES: str = "08:00"


class Settings:
    """Application settings loaded from environment variables."""

    APP_NAME: str = os.getenv("APP_NAME", "CareNest - Elderly Care Platform")
    ENVIRONMENT: str = os.getenv("ENVIRONMENT", "development")
    PORT: int = int(os.getenv("PORT", "8080"))
    SECRET_KEY: str = os.getenv("SECRET_KEY", "carenest-insecure-secret-key-change-me")

    # SQLite Database
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./healthapp.db")

    # Scheduler Secret Token for /tasks/send-reminders
    SCHEDULER_SECRET_TOKEN: str = os.getenv("SCHEDULER_SECRET_TOKEN", "scheduler-secret-token")

    # Google Gemini API Key
    GEMINI_API_KEY: str = os.getenv("GEMINI_API_KEY", "")

    # SMTP Email Configuration
    SMTP_HOST: str = os.getenv("SMTP_HOST", "")
    SMTP_PORT: int = int(os.getenv("SMTP_PORT", "587"))
    SMTP_USER: str = os.getenv("SMTP_USER", "")
    SMTP_PASSWORD: str = os.getenv("SMTP_PASSWORD", "")
    SMTP_FROM: str = os.getenv("SMTP_FROM", "CareNest Alerts <alerts@carenest.local>")
    SMTP_TLS: bool = os.getenv("SMTP_TLS", "true").lower() in ("true", "1", "yes")

    # Rate Limiting
    MAX_AUTH_ATTEMPTS: int = int(os.getenv("MAX_AUTH_ATTEMPTS", str(DEFAULT_AUTH_MAX_ATTEMPTS)))
    AUTH_LOCKOUT_SECONDS: int = int(os.getenv("AUTH_LOCKOUT_SECONDS", str(DEFAULT_AUTH_LOCKOUT_SECONDS)))


settings: Settings = Settings()

# Setup application logger
logger: logging.Logger = logging.getLogger("carenest")
if not logger.handlers:
    _handler = logging.StreamHandler()
    _formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)s] [%(name)s]: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    _handler.setFormatter(_formatter)
    logger.addHandler(_handler)
    logger.setLevel(logging.INFO if settings.ENVIRONMENT == "production" else logging.DEBUG)
