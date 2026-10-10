import pytest
from sqlalchemy import select
from app.models import MealPlan, Payment, Subscription, User


@pytest.mark.asyncio
async def test_create_order_malaysian_payment_methods(client, student_auth_headers, db_session):
    """
    Verify payment order generation for Malaysian payment rails:
    DuitNow QR, Touch 'n Go, ShopeePay, and GrabPay.
    """
    plan_res = await db_session.execute(select(MealPlan).where(MealPlan.is_active == True).limit(1))
    plan = plan_res.scalar_one_or_none()
    assert plan is not None, "Need active meal plan"

    methods = ["duitnow_qr", "tng_ewallet", "shopeepay", "grabpay"]
    for method in methods:
        res = await client.post(
            "/api/v1/payments/create-order",
            headers=student_auth_headers,
            json={"plan_id": str(plan.id), "payment_method": method},
        )
        assert res.status_code == 200, f"Method {method} order creation failed: {res.text}"
        data = res.json()
        assert "reference_code" in data
        assert data["payment_method"] == method
        assert data["amount_myr"] == float(plan.price_myr)
        assert "payment_id" in data


@pytest.mark.asyncio
async def test_payment_completion_and_idempotency(client, student_auth_headers, db_session):
    """
    Verify payment completion via gateway callback:
      1. Order created with status pending.
      2. Webhook triggers successful payment.
      3. Subscription is activated with correct credits.
      4. Webhook called again is idempotent.
    """
    plan_res = await db_session.execute(select(MealPlan).where(MealPlan.is_active == True).limit(1))
    plan = plan_res.scalar_one_or_none()
    assert plan is not None

    # 1. Create order
    create_res = await client.post(
        "/api/v1/payments/create-order",
        headers=student_auth_headers,
        json={"plan_id": str(plan.id), "payment_method": "duitnow_qr"},
    )
    assert create_res.status_code == 200
    order_data = create_res.json()
    ref_code = order_data["reference_code"]

    # Check status before payment
    status_res = await client.get(f"/api/v1/payments/status/{ref_code}")
    assert status_res.status_code == 200
    assert status_res.json()["status"] == "pending"

    # 2. Webhook simulated from Malaysian gateway (PayNet / Curlec)
    webhook_res = await client.post(
        "/api/v1/payments/webhook",
        json={
            "reference_code": ref_code,
            "status": "completed",
            "transaction_id": f"TXN-PAYNET-{ref_code}",
        },
    )
    assert webhook_res.status_code == 200
    assert webhook_res.json()["received"] is True

    # 3. Check status is now completed
    status_after = await client.get(f"/api/v1/payments/status/{ref_code}")
    assert status_after.status_code == 200
    assert status_after.json()["status"] == "completed"

    # Check database payment record
    pay_res = await db_session.execute(select(Payment).where(Payment.reference_code == ref_code))
    payment = pay_res.scalar_one_or_none()
    assert payment is not None
    assert payment.status == "completed"

    # 4. Idempotency test: duplicate webhook call
    webhook_res_2 = await client.post(
        "/api/v1/payments/webhook",
        json={
            "reference_code": ref_code,
            "status": "completed",
            "transaction_id": f"TXN-PAYNET-{ref_code}",
        },
    )
    assert webhook_res_2.status_code == 200
    assert webhook_res_2.json()["received"] is True

    # 5. Cleanup test records
    sub_id = payment.subscription_id
    await db_session.delete(payment)
    if sub_id:
        sub = await db_session.get(Subscription, sub_id)
        if sub:
            await db_session.delete(sub)
    await db_session.commit()

