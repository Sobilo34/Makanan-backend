import uuid
from typing import Optional, List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Subscription, MealPlan, WalletTransaction, Redemption
from app.schemas import WalletSummaryOut, SubscriptionOut, WalletTransactionOut, CancelSubscriptionRequest

router = APIRouter(prefix="/students", tags=["Students"])


@router.get("/dashboard-summary")
async def get_dashboard_summary(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Returns aggregated student metrics in one fast query instead of multiple client roundtrips."""
    # Active subscription
    sub_stmt = (
        select(Subscription)
        .options(selectinload(Subscription.meal_plan))
        .where(Subscription.user_id == current_user.id, Subscription.status == "active")
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub_res = await db.execute(sub_stmt)
    sub = sub_res.scalar_one_or_none()

    credits_remaining = (sub.credits_total - sub.credits_used) if sub else 0
    credits_used = sub.credits_used if sub else 0

    # Recent redemptions count
    red_stmt = select(Redemption).where(Redemption.user_id == current_user.id)
    red_res = await db.execute(red_stmt)
    total_redemptions = len(red_res.scalars().all())

    return {
        "user": {
            "id": current_user.id,
            "full_name": current_user.full_name,
            "email": current_user.email,
            "student_id": current_user.student_id,
        },
        "subscription": {
            "id": sub.id,
            "status": sub.status,
            "credits_total": sub.credits_total,
            "credits_used": sub.credits_used,
            "credits_remaining": credits_remaining,
            "expires_at": sub.expires_at,
            "meal_plans": sub.meal_plan,
        } if sub else None,
        "credits_remaining": credits_remaining,
        "credits_used": credits_used,
        "total_meals_redeemed": total_redemptions,
    }


@router.get("/wallet", response_model=WalletSummaryOut)
async def get_wallet(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    # Active subscription
    sub_stmt = (
        select(Subscription)
        .options(selectinload(Subscription.meal_plan))
        .where(Subscription.user_id == current_user.id, Subscription.status == "active")
        .order_by(Subscription.created_at.desc())
        .limit(1)
    )
    sub_res = await db.execute(sub_stmt)
    sub = sub_res.scalar_one_or_none()

    credits_remaining = (sub.credits_total - sub.credits_used) if sub else 0
    credits_used = sub.credits_used if sub else 0

    # Recent ledger transactions
    tx_stmt = (
        select(WalletTransaction)
        .where(WalletTransaction.user_id == current_user.id)
        .order_by(WalletTransaction.created_at.desc())
        .limit(20)
    )
    tx_res = await db.execute(tx_stmt)
    transactions = tx_res.scalars().all()

    sub_out = None
    if sub:
        sub_out = SubscriptionOut.model_validate(sub)
        sub_out.credits_remaining = credits_remaining
        if sub.meal_plan:
            sub_out.meal_plans = sub.meal_plan

    return {
        "active_subscription": sub_out,
        "credits_remaining": credits_remaining,
        "credits_used": credits_used,
        "total_meals_purchased": sub.credits_total if sub else 0,
        "recent_transactions": transactions,
    }


@router.post("/cancel-subscription")
async def cancel_subscription(
    req: CancelSubscriptionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Atomically cancels an active subscription and refunds remaining credits to the ledger.
    """
    async with db.begin():
        stmt = (
            select(Subscription)
            .where(
                Subscription.id == req.subscription_id,
                Subscription.user_id == current_user.id,
                Subscription.status == "active",
            )
            .with_for_update()
        )
        res = await db.execute(stmt)
        sub = res.scalar_one_or_none()

        if not sub:
            raise HTTPException(status_code=404, detail="No active subscription found to cancel")

        credits_remaining = sub.credits_total - sub.credits_used
        sub.status = "cancelled"

        # Record refund in ledger
        if credits_remaining > 0:
            ledger = WalletTransaction(
                user_id=current_user.id,
                subscription_id=sub.id,
                description=f"Subscription cancelled — {credits_remaining} meal credit(s) refunded",
                credits_delta=credits_remaining,
                balance_after=credits_remaining,
            )
            db.add(ledger)

    return {
        "success": True,
        "credits_refunded": credits_remaining,
    }
