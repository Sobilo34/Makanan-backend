import pytest
import uuid
from datetime import datetime, timezone, timedelta
from sqlalchemy import select
from app.models import Subscription, MealPlan, WalletTransaction


@pytest.mark.asyncio
async def test_wallet_and_cancel_subscription_flow(client, student_user, student_auth_headers, db_session):
    """
    Test real-time subscription cancellation and wallet refunding:
      1. Create an active subscription with 20 total credits, 5 used.
      2. Fetch wallet summary -> verify 15 remaining credits and active status.
      3. Cancel subscription -> atomic status transition to cancelled, 15 credits refunded to ledger.
      4. Verify subsequent cancel request returns 404.
    """
    # 1. Fetch a meal plan
    plan_res = await db_session.execute(select(MealPlan).limit(1))
    plan = plan_res.scalar_one_or_none()
    assert plan is not None

    sub_id = uuid.uuid4()
    sub = Subscription(
        id=sub_id,
        user_id=student_user.id,
        meal_plan_id=plan.id,
        status="active",
        credits_total=20,
        credits_used=5,
        starts_at=datetime.now(timezone.utc),
        expires_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db_session.add(sub)
    await db_session.commit()

    # 2. Check wallet
    wallet_res = await client.get("/api/v1/students/wallet", headers=student_auth_headers)
    assert wallet_res.status_code == 200
    wallet_data = wallet_res.json()
    assert wallet_data["credits_remaining"] == 15
    assert wallet_data["credits_used"] == 5
    assert wallet_data["active_subscription"]["id"] == str(sub_id)

    # 3. Cancel subscription
    cancel_res = await client.post(
        "/api/v1/students/cancel-subscription",
        headers=student_auth_headers,
        json={"subscription_id": str(sub_id)},
    )
    assert cancel_res.status_code == 200
    cancel_data = cancel_res.json()
    assert cancel_data["success"] is True
    assert cancel_data["credits_refunded"] == 15

    # 4. Verify subscription status updated and ledger entry exists
    await db_session.refresh(sub)
    assert sub.status == "cancelled"

    tx_res = await db_session.execute(
        select(WalletTransaction).where(
            WalletTransaction.user_id == student_user.id,
            WalletTransaction.subscription_id == sub_id,
        )
    )
    tx = tx_res.scalar_one_or_none()
    assert tx is not None
    assert tx.credits_delta == 15
    assert tx.balance_after >= 15
    assert "refunded" in tx.description

    # 5. Subsequent cancel on already cancelled subscription returns 404
    second_cancel = await client.post(
        "/api/v1/students/cancel-subscription",
        headers=student_auth_headers,
        json={"subscription_id": str(sub_id)},
    )
    assert second_cancel.status_code == 404
    assert second_cancel.json()["detail"] == "No active subscription found to cancel"
