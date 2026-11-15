"""Security utilities: Passcode generation, bcrypt hashing, sessions, and rate limiting."""

import base64
import hashlib
import hmac
import json
import secrets
import string
import time
from typing import Any

import bcrypt

from app.config import (
    BCRYPT_ROUNDS,
    CARE_ID_PREFIX,
    CARE_ID_RANDOM_DIGITS,
    PASSCODE_RANDOM_DIGITS,
    PASSCODE_ROLE_PREFIXES,
    SESSION_TOKEN_EXPIRATION_SECONDS,
    logger,
    settings,
)


def generate_care_id() -> str:
    """Generate a unique and memorable Care Profile ID.

    Returns:
        str: Formatted Care Profile ID (e.g. 'CARE-5829').
    """
    digits = "".join(secrets.choice(string.digits) for _ in range(CARE_ID_RANDOM_DIGITS))
    return f"{CARE_ID_PREFIX}-{digits}"


def generate_passcode(role: str) -> str:
    """Generate an accessible, easy-to-read passcode prefixed by role.

    Args:
        role (str): The target role ('elder', 'caretaker', or 'family').

    Returns:
        str: Formatted role passcode (e.g. 'ELD-7291', 'CAR-4082', 'FAM-6315').
    """
    prefix = PASSCODE_ROLE_PREFIXES.get(role.strip().lower(), "KEY")
    digits = "".join(secrets.choice(string.digits) for _ in range(PASSCODE_RANDOM_DIGITS))
    return f"{prefix}-{digits}"


def hash_passcode(passcode: str) -> str:
    """Hash a plaintext passcode using bcrypt with configured work factor.

    Args:
        passcode (str): Plaintext user passcode.

    Returns:
        str: Salted and hashed bcrypt string.
    """
    normalized = passcode.strip().upper()
    salt = bcrypt.gensalt(rounds=BCRYPT_ROUNDS)
    hashed = bcrypt.hashpw(normalized.encode("utf-8"), salt)
    return hashed.decode("utf-8")


def verify_passcode(plain_passcode: str, hashed_passcode: str) -> bool:
    """Verify a candidate plaintext passcode against an existing bcrypt hash.

    Args:
        plain_passcode (str): The candidate passcode entered by the user.
        hashed_passcode (str): The stored bcrypt hash from the database.

    Returns:
        bool: True if candidate matches hash, False otherwise.
    """
    if not plain_passcode or not hashed_passcode:
        return False
    normalized = plain_passcode.strip().upper()
    try:
        return bcrypt.checkpw(normalized.encode("utf-8"), hashed_passcode.encode("utf-8"))
    except (ValueError, TypeError, Exception) as err:
        logger.warning("Passcode verification failed due to invalid hash format: %s", str(err))
        return False


def create_session_token(
    payload: dict[str, Any],
    expires_in_seconds: int = SESSION_TOKEN_EXPIRATION_SECONDS,
) -> str:
    """Create a signed, base64-encoded HMAC-SHA256 session token.

    Args:
        payload (Dict[str, Any]): Session payload (profile ID, role, etc.).
        expires_in_seconds (int): Lifetime of token in seconds.

    Returns:
        str: Signed token in '<data_b64>.<signature_b64>' format.
    """
    payload_copy = payload.copy()
    payload_copy["exp"] = int(time.time()) + expires_in_seconds
    raw_json = json.dumps(payload_copy, separators=(",", ":"), sort_keys=True).encode("utf-8")
    signature = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw_json, hashlib.sha256).digest()
    data_b64 = base64.urlsafe_b64encode(raw_json).decode("utf-8")
    sig_b64 = base64.urlsafe_b64encode(signature).decode("utf-8")
    return f"{data_b64}.{sig_b64}"


def decode_session_token(token: str) -> dict[str, Any] | None:
    """Verify cryptographic signature and expiration of an HMAC session token.

    Args:
        token (str): Base64-encoded session token string.

    Returns:
        Optional[Dict[str, Any]]: Decoded payload if valid, None if invalid or expired.
    """
    if not token or "." not in token:
        return None
    try:
        data_b64, sig_b64 = token.split(".", 1)
        raw_json = base64.urlsafe_b64decode(data_b64.encode("utf-8"))
        signature = base64.urlsafe_b64decode(sig_b64.encode("utf-8"))

        expected_sig = hmac.new(settings.SECRET_KEY.encode("utf-8"), raw_json, hashlib.sha256).digest()
        if not hmac.compare_digest(signature, expected_sig):
            logger.debug("Session token signature mismatch")
            return None

        payload: dict[str, Any] = json.loads(raw_json.decode("utf-8"))
        if payload.get("exp", 0) < time.time():
            logger.debug("Session token has expired")
            return None
        return payload
    except (ValueError, TypeError, json.JSONDecodeError, UnicodeDecodeError) as err:
        logger.debug("Malformed session token: %s", str(err))
        return None


def generate_csrf_token(seed: str | None = None) -> str:
    """Generate a cryptographically secure CSRF token.

    Args:
        seed (str | None): Optional seed string (e.g. session token).

    Returns:
        str: Hex-encoded CSRF token string.
    """
    if seed:
        return hmac.new(settings.SECRET_KEY.encode(), seed.encode(), hashlib.sha256).hexdigest()
    return secrets.token_hex(32)


def verify_csrf_token(submitted_token: str | None, expected_token: str | None) -> bool:
    """Verify submitted CSRF token matches expected token in constant time.

    Args:
        submitted_token (str | None): Token sent in request header or form body.
        expected_token (str | None): Token stored in cookie or session.

    Returns:
        bool: True if tokens are non-empty and match identically, False otherwise.
    """
    if not submitted_token or not expected_token:
        return False
    return hmac.compare_digest(submitted_token.strip(), expected_token.strip())


class AuthRateLimiter:
    """Sliding-window in-memory rate limiter to prevent brute-force passcode attacks."""

    def __init__(
        self,
        max_attempts: int = settings.MAX_AUTH_ATTEMPTS,
        window_seconds: int = settings.AUTH_LOCKOUT_SECONDS,
    ) -> None:
        """Initialize the rate limiter.

        Args:
            max_attempts (int): Maximum allowed failed attempts before lockout.
            window_seconds (int): Window duration in seconds.
        """
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self._attempts: dict[tuple[str, str], list[float]] = {}

    def _cleanup_old(self, key: tuple[str, str], now: float) -> None:
        """Remove timestamps outside the current sliding window.

        Args:
            key (Tuple[str, str]): Composite key of (ip, care_id).
            now (float): Current epoch timestamp.
        """
        if key in self._attempts:
            cutoff = now - self.window_seconds
            self._attempts[key] = [t for t in self._attempts[key] if t > cutoff]
            if not self._attempts[key]:
                del self._attempts[key]

    def is_rate_limited(self, ip: str, care_id: str) -> tuple[bool, int]:
        """Check if attempts for an IP and Care ID exceeded the threshold.

        Args:
            ip (str): Client IP address.
            care_id (str): Target Care ID.

        Returns:
            Tuple[bool, int]: (True if locked out, seconds remaining in lockout).
        """
        now = time.time()
        key = (ip, care_id.strip().upper())
        self._cleanup_old(key, now)

        attempts = self._attempts.get(key, [])
        if len(attempts) >= self.max_attempts:
            oldest_relevant = attempts[0]
            remaining = int(self.window_seconds - (now - oldest_relevant))
            return True, max(1, remaining)
        return False, 0

    def record_failure(self, ip: str, care_id: str) -> None:
        """Record a failed passcode attempt.

        Args:
            ip (str): Client IP address.
            care_id (str): Target Care ID.
        """
        now = time.time()
        key = (ip, care_id.strip().upper())
        self._cleanup_old(key, now)
        if key not in self._attempts:
            self._attempts[key] = []
        self._attempts[key].append(now)

    def record_success(self, ip: str, care_id: str) -> None:
        """Clear recorded failed attempts after successful authentication.

        Args:
            ip (str): Client IP address.
            care_id (str): Target Care ID.
        """
        key = (ip, care_id.strip().upper())
        if key in self._attempts:
            del self._attempts[key]


auth_rate_limiter = AuthRateLimiter(
    max_attempts=settings.MAX_AUTH_ATTEMPTS,
    window_seconds=settings.AUTH_LOCKOUT_SECONDS,
)
