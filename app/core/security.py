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
    if not token or str(token).strip().lower() in ["undefined", "null", "none", ""]:
        return None

    # 1. Native FastAPI JWT
    try:
        payload = jwt.decode(token, settings.JWT_SECRET, algorithms=[settings.JWT_ALGORITHM])
        return payload
    except jwt.PyJWTError:
        pass

    # 2. Supabase JWT fallback (allows transparent transition from Supabase auth session)
    try:
        unverified = jwt.decode(token, options={"verify_signature": False})
        exp = unverified.get("exp")
        now_ts = datetime.now(timezone.utc).timestamp()
        
        # Allow 30-day grace period for Supabase session transition
        if exp and (now_ts - exp) > (30 * 86400):
            return None  # truly expired beyond session window

        if unverified.get("sub"):
            user_meta = unverified.get("user_metadata") or {}
            app_meta = unverified.get("app_metadata") or {}
            role = user_meta.get("role") or app_meta.get("role") or unverified.get("role") or "student"
            full_name = user_meta.get("full_name") or user_meta.get("fullName") or unverified.get("email", "").split("@")[0]
            return {
                "sub": unverified.get("sub"),
                "email": unverified.get("email"),
                "role": role,
                "full_name": full_name,
                "is_supabase": True,
            }
    except Exception as e:
        print(f"[SECURITY] JWT decode error: {e}")
        pass

    return None


# ── HMAC-SHA256 Cryptographic Dynamic QR Token ────────────────────────────────
def base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).decode("utf-8").rstrip("=")


def base64url_decode(data: str) -> bytes:
    padding = "=" * (4 - (len(data) % 4))
    return base64.urlsafe_b64decode(data + padding)


def generate_qr_token(
    redemption_id: str,
    user_id: str,
    meal_id: str,
    partner_id: Optional[str] = None,
    expiry_seconds: int = 300,
) -> str:
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
