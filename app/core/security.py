import time
import hmac
import hashlib
import json
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
from passlib.context import CryptContext
import jwt
from app.core.config import settings

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except Exception:
        return False


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def create_access_token(data: Dict[str, Any], expires_delta: Optional[timedelta] = None) -> str:
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "iat": datetime.now(timezone.utc)})
    encoded_jwt = jwt.encode(to_encode, settings.JWT_SECRET, algorithm=settings.JWT_ALGORITHM)
    return encoded_jwt


def decode_access_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Decodes and cryptographically verifies an access token using HMAC-SHA256.
    Rejects expired, malformed, or untrusted tokens.
    """
    if not token or str(token).strip().lower() in ["undefined", "null", "none", ""]:
        return None

    try:
        payload = jwt.decode(
            token,
            settings.JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            options={"require": ["exp", "sub"]},
        )
        return payload
    except jwt.PyJWTError:
        return None


# ── HMAC-SHA256 Cryptographic Dynamic QR Token ────────────────────────────────
def base64url_encode(data: bytes) -> str:
    """
    Encode bytes to base64url without padding.

    >>> base64url_encode(b"hello world")
    'aGVsbG8gd29ybGQ'
    >>> base64url_encode(b"test1234")
    'dGVzdDEyMzQ'
    """
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def base64url_decode(data: str) -> bytes:
    """
    Decode base64url string with automatic padding calculation.

    >>> base64url_decode('aGVsbG8gd29ybGQ')
    b'hello world'
    >>> base64url_decode('dGVzdDEyMzQ')
    b'test1234'
    """
    remainder = len(data) % 4
    padding = "=" * (4 - remainder) if remainder != 0 else ""
    return base64.urlsafe_b64decode(data + padding)


def generate_qr_token(
    redemption_id: str,
    user_id: str,
    meal_id: str,
    partner_id: Optional[str] = None,
    expiry_seconds: int = 300,
) -> str:
    """
    Generates an HMAC-SHA256 signed dynamic QR token with an expiry window.

    >>> token = generate_qr_token("rid-1", "uid-1", "mid-1", "pid-1", 300)
    >>> isinstance(token, str) and "." in token
    True
    """
    payload = {
        "rid": redemption_id,
        "uid": user_id,
        "mid": meal_id,
        "pid": partner_id,
        "exp": int(time.time()) + expiry_seconds,
    }
    payload_bytes = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    payload_b64 = base64url_encode(payload_bytes)

    sig = hmac.new(
        settings.QR_SECRET.encode("utf-8"),
        payload_b64.encode("utf-8"),
        hashlib.sha256,
    ).digest()
    sig_b64 = base64url_encode(sig)

    return f"{payload_b64}.{sig_b64}"


def verify_qr_token(token: str) -> Optional[Dict[str, Any]]:
    """
    Verifies the HMAC-SHA256 signature and expiry timestamp of a dynamic QR token.
    Uses constant-time comparison to prevent timing attacks.

    >>> token = generate_qr_token("rid-1", "uid-1", "mid-1", "pid-1", 300)
    >>> res = verify_qr_token(token)
    >>> res["rid"] == "rid-1" and res["uid"] == "uid-1"
    True
    >>> verify_qr_token("tampered.signature") is None
    True
    >>> verify_qr_token("") is None
    True
    """
    if not token or "." not in token:
        return None
    try:
        parts = token.split(".")
        if len(parts) != 2:
            return None
        payload_b64, sig_b64 = parts[0], parts[1]

        expected_sig = hmac.new(
            settings.QR_SECRET.encode("utf-8"),
            payload_b64.encode("utf-8"),
            hashlib.sha256,
        ).digest()
        expected_sig_b64 = base64url_encode(expected_sig)

        if not hmac.compare_digest(sig_b64, expected_sig_b64):
            return None

        payload_bytes = base64url_decode(payload_b64)
        payload = json.loads(payload_bytes.decode("utf-8"))

        # Verify time validity
        if payload.get("exp", 0) < int(time.time()):
            return None

        return payload
    except Exception:
        return None
