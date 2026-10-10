import pytest
import jwt
from datetime import datetime, timedelta, timezone
from app.core.config import settings
from app.core.security import (
    get_password_hash,
    verify_password,
    create_access_token,
    decode_access_token,
)


def test_password_hashing():
    """Verify bcrypt hash generation and matching."""
    plain = "SuperSecurePassword123!"
    hashed = get_password_hash(plain)
    assert hashed != plain
    assert hashed.startswith("$2b$") or hashed.startswith("$2a$")
    assert verify_password(plain, hashed) is True
    assert verify_password("WrongPassword!", hashed) is False
    assert verify_password("", hashed) is False


def test_jwt_signature_verification_strictness():
    """Verify that unsigned, tampered, or wrong-secret JWTs are strictly rejected."""
    payload = {"sub": "user-uuid-123", "email": "test@makanan.app", "role": "student"}
    valid_token = create_access_token(payload)
    decoded = decode_access_token(valid_token)
    assert decoded is not None
    assert decoded["sub"] == "user-uuid-123"
    assert decoded["role"] == "student"

    # Token signed with forged/wrong secret
    fake_secret = "wrong_secret_key_1234567890abcdef"
    forged_token = jwt.encode(
        {**payload, "exp": datetime.now(timezone.utc) + timedelta(hours=1)},
        fake_secret,
        algorithm="HS256",
    )
    assert decode_access_token(forged_token) is None

    # Tampered token payload
    parts = valid_token.split(".")
    tampered_token = f"{parts[0]}.eyJuZXciOiAidGFtcGVyZWQifQ.{parts[2]}"
    assert decode_access_token(tampered_token) is None

    # Expired token
    expired_token = create_access_token(payload, expires_delta=timedelta(seconds=-10))
    assert decode_access_token(expired_token) is None

    # Empty or null token strings
    assert decode_access_token("") is None
    assert decode_access_token("null") is None
    assert decode_access_token("undefined") is None


@pytest.mark.asyncio
async def test_security_headers_and_request_id(client):
    """Verify security headers middleware and X-Request-ID propagation."""
    res = await client.get("/api/v1/health")
    assert res.status_code == 200
    headers = res.headers
    assert headers.get("X-Content-Type-Options") == "nosniff"
    assert headers.get("X-Frame-Options") == "DENY"
    assert headers.get("X-XSS-Protection") == "1; mode=block"
    assert headers.get("Referrer-Policy") == "strict-origin-when-cross-origin"
    assert "X-Request-ID" in headers
    assert len(headers["X-Request-ID"]) > 0


@pytest.mark.asyncio
async def test_role_boundary_enforcement(client, student_auth_headers, partner_auth_headers, admin_auth_headers):
    """Verify strict role-based access control preventing privilege escalation."""
    # Student attempting Admin route -> 403 Forbidden
    res_student_admin = await client.get("/api/v1/admin/overview", headers=student_auth_headers)
    assert res_student_admin.status_code == 403

    # Partner attempting Admin route -> 403 Forbidden
    res_partner_admin = await client.get("/api/v1/admin/overview", headers=partner_auth_headers)
    assert res_partner_admin.status_code == 403

    # Student attempting Partner profile route -> 403 Forbidden
    res_student_partner = await client.get("/api/v1/partners/me", headers=student_auth_headers)
    assert res_student_partner.status_code == 403

    # Admin accessing Admin route -> 200 OK
    res_admin = await client.get("/api/v1/admin/overview", headers=admin_auth_headers)
    assert res_admin.status_code == 200
    data = res_admin.json()
    assert "total_students" in data
    assert "total_partners" in data


@pytest.mark.asyncio
async def test_unauthenticated_rejection(client):
    """Verify that protected endpoints reject missing or invalid auth tokens with 401."""
    res = await client.get("/api/v1/auth/me")
    assert res.status_code == 401

    res_bad = await client.get("/api/v1/auth/me", headers={"Authorization": "Bearer bad.token.here"})
    assert res_bad.status_code == 401
