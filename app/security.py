"""Security utilities: Passcode generation, bcrypt hashing, sessions, and rate limiting."""

import time
import secrets
import string
import hmac
import hashlib
import json
import base64
from typing import Optional, Dict, Tuple
import bcrypt

from app.config import settings


# ---------------------------------------------------------------------------
# Passcode & Identifier Generation
# ---------------------------------------------------------------------------

def generate_care_id() -> str:
    """Generate a clean, memorable Care Profile ID like CARE-5829."""
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"CARE-{digits}"


def generate_passcode(role: str) -> str:
    """Generate an accessible, easy-to-read passcode prefixed with role.
    
    Examples: ELD-7291, CAR-4082, FAM-6315
    """
    prefix = {
        "elder": "ELD",
        "caretaker": "CAR",
        "family": "FAM",
    }.get(role.lower(), "KEY")
    digits = "".join(secrets.choice(string.digits) for _ in range(4))
    return f"{prefix}-{digits}"


# ---------------------------------------------------------------------------
# Bcrypt Hashing & Verification
# ---------------------------------------------------------------------------

def hash_passcode(passcode: str) -> str:
    """Hash a plaintext passcode using bcrypt."""
    normalized = passcode.strip().upper()
    salt = bcrypt.gensalt(rounds=12)
    hashed = bcrypt.hashpw(normalized.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_passcode(plain_passcode: str, hashed_passcode: str) -> bool:
    """Verify a plaintext passcode against its bcrypt hash."""
    if not plain_passcode or not hashed_passcode:
        return False
    normalized = plain_passcode.strip().upper()
    try:
        return bcrypt.checkpw(normalized.encode("utf-8"), hashed_passcode.encode("utf-8"))
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Tamper-Proof Session Cookie Tokens (HMAC-SHA256)
# ---------------------------------------------------------------------------

def create_session_token(payload: dict, expires_in_seconds: int = 86400 * 7) -> str:
    """Create a signed, base64-encoded session token with timestamp."""
    payload_copy = payload.copy()
    payload_copy["exp"] = int(time.time()) + expires_in_seconds
    raw_json = json.dumps(payload_copy, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw_json, hashlib.sha256).digest()
    combined = base64.urlsafe_b64encode(raw_json).decode("utf-8") + "." + base64.urlsafe_b64encode(signature).decode("utf-8")
    return combined


def decode_session_token(token: str) -> Optional[dict]:
    """Verify signature and expiration of session token. Returns payload dict or None."""
    if not token or "." not in token:
        return None
    try:
        data_b64, sig_b64 = token.split(".", 1)
        raw_json = base64.urlsafe_b64decode(data_b64.encode("utf-8"))
        signature = base64.urlsafe_b64decode(sig_b64.encode("utf-8"))

        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw_json, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_sig):
            return None

        payload = json.loads(raw_json.decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            return None  # Expired
        return payload
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Rate Limiter for Passcode Authentication Attempts
# ---------------------------------------------------------------------------

class AuthRateLimiter:
    """In-memory rate limiter to prevent brute-force attacks on passcodes.
    
    Tracks failed attempts per (IP, care_id) tuple over a sliding window.
    """

    def __init__(self, max_attempts: int = 5, window_seconds: int = 60):
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        # Key: (ip, care_id) -> list of timestamp floats
        self._attempts: Dict[Tuple[str, str], list] = {}

    def _cleanup_old(self, key: Tuple[str, str], now: float):
        if key in self._attempts:
            cutoff = now - self.window_seconds
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
            if not self._attempts[key]:
                del self._attempts[key]

    def is_rate_limited(self, ip: str, care_id: str) -> Tuple[bool, int]:
        """Check if attempts exceeded limit. Returns (is_limited, seconds_remaining)."""
        now = time.time()
        key = (ip, care_id.strip().upper())
        self._cleanup_old(key, now)

        attempts = self._attempts.get(key, [])
        if len(attempts) >= self.max_attempts:
            oldest_relevant = attempts[0]
            remaining = int(self.window_seconds - (now - oldest_relevant))
            return True, max(1, remaining)
        return False, 0

    def record_failure(self, ip: str, care_id: str):
        """Record a failed attempt."""
        now = time.time()
        key = (ip, care_id.strip().upper())
        self._cleanup_old(key, now)
        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append(now)

    def record_success(self, ip: str, care_id: str):
        """Clear attempts on successful login."""
        key = (ip, care_id.strip().upper())
        if key in self._attempts:
            del self._attempts[key]


auth_rate_limiter = AuthRateLimiter(
    max_attempts=settings.MAX_AUTH_ATTEMPTS,
    window_seconds=settings.AUTH_LOCKOUT_SECONDS,
)
