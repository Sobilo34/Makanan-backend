import pytest
import uuid
from sqlalchemy import select
from app.core.security import generate_qr_token, verify_qr_token
from app.models import User, Partner, Meal, Subscription, Redemption, MealPlan


def test_qr_token_unit_integrity():
    """Verify cryptographic HMAC-SHA256 dynamic QR generation and validation."""
    rid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    pid = str(uuid.uuid4())

    token = generate_qr_token(rid, uid, mid, pid, expiry_seconds=300)
    assert token is not None
    assert "." in token

    # Valid token verification
    verified = verify_qr_token(token)
    assert verified is not None
    assert verified["rid"] == rid
    assert verified["uid"] == uid
    assert verified["mid"] == mid
    assert verified["pid"] == pid


def test_expired_qr_token_rejection():
    """Verify that expired QR tokens are rejected."""
    rid = str(uuid.uuid4())
    uid = str(uuid.uuid4())
    mid = str(uuid.uuid4())
    token = generate_qr_token(rid, uid, mid, expiry_seconds=-10)
    assert verify_qr_token(token) is None


def test_tampered_qr_token_rejection():
    """Verify that tampered QR tokens fail HMAC signature verification."""
    token = generate_qr_token("rid-original", "uid-1", "mid-1", expiry_seconds=300)
    parts = token.split(".")
    # Tamper with the base64 payload
    tampered_token = f"eyJyaWQiOiAicmlkLWhhY2tlZCJ9.{parts[1]}"
    assert verify_qr_token(tampered_token) is None


@pytest.mark.asyncio
async def test_full_redemption_lifecycle(client, student_user, student_auth_headers, partner_auth_headers, db_session):
    """
    Test real-time end-to-end redemption flow:
      1. Student redeems a meal -> credit deducted, signed QR token generated.
      2. Partner verifies the QR token.
      3. Partner confirms fulfillment -> status becomes completed.
      4. Partner attempting double fulfillment is rejected.
    """
    # 1. Fetch meal and create isolated subscription for test runner student
    meal_res = await db_session.execute(
        select(Meal).where(Meal.is_active == True).limit(1)
    )
    meal = meal_res.scalar_one_or_none()
    assert meal is not None, "Need active meal for test"

    plan_res = await db_session.execute(
        select(MealPlan).where(MealPlan.is_active == True).limit(1)
    )
    plan = plan_res.scalar_one_or_none()
    assert plan is not None, "Need active meal plan for test"

    sub = Subscription(
        id=uuid.uuid4(),
        user_id=student_user.id,
        meal_plan_id=plan.id,
        status="active",
        credits_total=20,
        credits_used=0,
    )
    db_session.add(sub)
    await db_session.commit()
    await db_session.refresh(sub)
    initial_used = 0

    # 2. Student calls redeem endpoint
    redeem_res = await client.post(
        "/api/v1/redemptions/redeem",
        headers=student_auth_headers,
        json={
            "subscription_id": str(sub.id),
            "meal_id": str(meal.id),
            "partner_id": str(meal.partner_id) if meal.partner_id else None,
        },
    )
    assert redeem_res.status_code == 200, f"Redeem failed: {redeem_res.text}"
    redemption_data = redeem_res.json()
    assert "redemption_id" in redemption_data
    assert redemption_data["status"] == "pending"
    qr_token = redemption_data.get("qr_token")
    qr_code = redemption_data.get("qr_code")
    assert qr_code is not None
    r_id = redemption_data["redemption_id"]

    # Verify credit was deducted
    await db_session.refresh(sub)
    assert sub.credits_used == initial_used + 1

    # 3. Partner verifies the QR code
    verify_res = await client.post(
        "/api/v1/partners/verify-qr",
        headers=partner_auth_headers,
        json={"qr_code_or_token": qr_token or qr_code},
    )
    assert verify_res.status_code == 200, f"Partner QR verify failed: {verify_res.text}"
    v_data = verify_res.json()
    assert v_data["valid"] is True
    assert v_data["redemption_id"] == r_id

    # 4. Partner confirms and fulfills redemption
    confirm_res = await client.post(
        "/api/v1/partners/confirm-redemption",
        headers=partner_auth_headers,
        json={"redemption_id": r_id},
    )
    assert confirm_res.status_code == 200, f"Confirm failed: {confirm_res.text}"
    c_data = confirm_res.json()
    assert c_data["success"] is True

    # 5. Prevent double fulfillment / returns already_confirmed
    re_confirm = await client.post(
        "/api/v1/partners/confirm-redemption",
        headers=partner_auth_headers,
        json={"redemption_id": r_id},
    )
    assert re_confirm.status_code == 200
    assert re_confirm.json().get("already_confirmed") is True

    # 6. Cleanup test records
    redemption_record = await db_session.get(Redemption, uuid.UUID(r_id))
    if redemption_record:
        await db_session.delete(redemption_record)
    await db_session.delete(sub)
    await db_session.commit()

