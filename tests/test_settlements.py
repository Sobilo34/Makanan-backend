import pytest
import uuid
from datetime import datetime, timezone
from sqlalchemy import select
from app.models import Settlement, Partner


@pytest.mark.asyncio
async def test_admin_settlements_lifecycle(client, admin_auth_headers, student_auth_headers, db_session):
    """Verify admin settlement retrieval and payout mark-as-paid functionality."""
    # Ensure a test partner exists
    partner_res = await db_session.execute(select(Partner).limit(1))
    partner = partner_res.scalar_one_or_none()
    assert partner is not None, "Need partner for settlement test"

    # Create a pending settlement
    settlement_id = uuid.uuid4()
    now = datetime.now(timezone.utc)
    settlement = Settlement(
        id=settlement_id,
        partner_id=partner.id,
        period_start=now,
        period_end=now,
        total_redemptions=25,
        total_amount_myr=200.0,
        status="pending",
    )
    db_session.add(settlement)
    await db_session.commit()

    # 1. Admin lists settlements
    list_res = await client.get("/api/v1/admin/settlements", headers=admin_auth_headers)
    assert list_res.status_code == 200
    settlements = list_res.json()
    assert any(str(s["id"]) == str(settlement_id) for s in settlements)

    # 2. Student attempting to mark settlement paid -> 403 Forbidden
    student_res = await client.post(
        f"/api/v1/admin/settlements/{settlement_id}/mark-paid",
        headers=student_auth_headers,
        json={"reference": "DUITNOW-BATCH-999"},
    )
    assert student_res.status_code == 403

    # 3. Admin marks settlement as paid
    admin_res = await client.post(
        f"/api/v1/admin/settlements/{settlement_id}/mark-paid",
        headers=admin_auth_headers,
        json={"reference": "DUITNOW-BATCH-999"},
    )
    assert admin_res.status_code == 200
    assert admin_res.json()["success"] is True

    # 4. Verify status in database
    await db_session.refresh(settlement)
    assert settlement.status == "paid"
    assert settlement.payment_reference == "DUITNOW-BATCH-999"
    assert settlement.paid_at is not None
