import uuid
from datetime import datetime, timezone
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, func, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import require_role
from app.models import (
    User,
    Partner,
    PartnerApplication,
    MealPlan,
    Subscription,
    Redemption,
    Payment,
    Settlement,
    WaitlistSignup,
)

router = APIRouter(prefix="/admin", tags=["Admin"], dependencies=[Depends(require_role(["admin"]))])


@router.get("/overview")
async def get_admin_overview(db: AsyncSession = Depends(get_db)):
    # Total students
    s_stmt = select(func.count(User.id)).where(User.role == "student")
    s_count = (await db.execute(s_stmt)).scalar() or 0

    # Total partners
    p_stmt = select(func.count(Partner.id))
    p_count = (await db.execute(p_stmt)).scalar() or 0

    # Redemptions today
    now = datetime.now(timezone.utc)
    today_start = datetime(now.year, now.month, now.day, tzinfo=timezone.utc)
    r_stmt = select(func.count(Redemption.id)).where(Redemption.created_at >= today_start)
    r_count = (await db.execute(r_stmt)).scalar() or 0

    # Total revenue MYR
    rev_stmt = select(func.sum(Payment.amount_myr)).where(Payment.status == "completed")
    rev_total = float((await db.execute(rev_stmt)).scalar() or 0.0)

    # Pending settlements count
    set_stmt = select(func.count(Settlement.id)).where(Settlement.status.in_(["pending", "requested"]))
    set_count = (await db.execute(set_stmt)).scalar() or 0

    return {
        "total_students": s_count,
        "total_partners": p_count,
        "redemptions_today": r_count,
        "total_revenue_myr": rev_total,
        "pending_settlements_count": set_count,
    }


@router.get("/students")
async def list_students(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .options(selectinload(User.subscriptions))
        .where(User.role == "student")
        .order_by(User.created_at.desc())
    )
    res = await db.execute(stmt)
    users = res.scalars().all()

    return [
        {
            "id": u.id,
            "full_name": u.full_name,
            "email": u.email,
            "student_id": u.student_id,
            "is_active": u.is_active,
            "created_at": u.created_at,
            "active_subscription": any(s.status == "active" for s in u.subscriptions),
        }
        for u in users
    ]


@router.get("/students/{user_id}")
async def get_student_detail(user_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = (
        select(User)
        .options(
            selectinload(User.subscriptions).selectinload(Subscription.meal_plan),
            selectinload(User.redemptions).selectinload(Redemption.meal),
        )
        .where(User.id == user_id)
    )
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user:
        raise HTTPException(status_code=404, detail="Student not found")

    return {
        "id": user.id,
        "full_name": user.full_name,
        "email": user.email,
        "student_id": user.student_id,
        "is_active": user.is_active,
        "phone": user.phone,
        "created_at": user.created_at,
        "subscriptions": [
            {
                "id": s.id,
                "status": s.status,
                "credits_total": s.credits_total,
                "credits_used": s.credits_used,
                "starts_at": s.starts_at,
                "expires_at": s.expires_at,
                "meal_plan": {"name": s.meal_plan.name, "price_myr": float(s.meal_plan.price_myr)} if s.meal_plan else None,
            }
            for s in user.subscriptions
        ],
        "redemptions": [
            {
                "id": r.id,
                "redeemed_at": r.redeemed_at,
                "meal": {"name": r.meal.name} if r.meal else None,
            }
            for r in user.redemptions
        ],
    }


@router.get("/partners")
async def list_partners(db: AsyncSession = Depends(get_db)):
    stmt = select(Partner).order_by(Partner.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/payments")
async def list_payments(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Payment)
        .options(selectinload(Payment.user), selectinload(Payment.meal_plan))
        .order_by(Payment.created_at.desc())
        .limit(100)
    )
    res = await db.execute(stmt)
    payments = res.scalars().all()

    return [
        {
            "id": p.id,
            "student": p.user.full_name if p.user else "Unknown",
            "plan": p.meal_plan.name if p.meal_plan else "Meal Plan",
            "amount": float(p.amount_myr),
            "method": p.payment_method,
            "status": p.status,
            "reference_code": p.reference_code,
            "created_at": p.created_at,
        }
        for p in payments
    ]


@router.get("/settlements")
async def list_settlements(db: AsyncSession = Depends(get_db)):
    stmt = (
        select(Settlement)
        .options(selectinload(Settlement.partner))
        .order_by(Settlement.created_at.desc())
    )
    res = await db.execute(stmt)
    settlements = res.scalars().all()

    return [
        {
            "id": s.id,
            "partner_name": s.partner.name if s.partner else "Partner",
            "period_start": s.period_start,
            "period_end": s.period_end,
            "total_redemptions": s.total_redemptions,
            "total_amount_myr": float(s.total_amount_myr),
            "status": s.status,
            "payout_requested_at": s.payout_requested_at,
            "paid_at": s.paid_at,
            "payment_reference": s.payment_reference,
            "created_at": s.created_at,
        }
        for s in settlements
    ]


class MarkSettlementPaidRequest(BaseModel):
    reference: Optional[str] = "BANK-TRF-COMPLETED"


@router.post("/settlements/{settlement_id}/mark-paid")
async def mark_settlement_paid(
    settlement_id: uuid.UUID,
    req: Optional[MarkSettlementPaidRequest] = None,
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    ref = (req.reference if req and req.reference else None) or "BANK-TRF-COMPLETED"
    stmt = (
        update(Settlement)
        .where(Settlement.id == settlement_id)
        .values(status="paid", paid_at=now, payment_reference=ref, updated_at=now)
    )
    res = await db.execute(stmt)
    await db.commit()
    return {"success": True}


@router.get("/redemptions")
async def list_all_redemptions(
    limit: int = 100,
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Redemption)
        .options(
            selectinload(Redemption.user),
            selectinload(Redemption.meal),
            selectinload(Redemption.partner),
            selectinload(Redemption.subscription).selectinload(Subscription.meal_plan),
        )
        .order_by(Redemption.created_at.desc())
        .limit(limit)
    )
    res = await db.execute(stmt)
    redemptions = res.scalars().all()

    return [
        {
            "id": r.id,
            "status": r.status,
            "qr_code": r.qr_code,
            "redeemed_at": r.redeemed_at or r.created_at,
            "created_at": r.created_at,
            "student_name": r.user.full_name if r.user else "Student",
            "meal_name": r.meal.name if r.meal else "Meal",
            "partner_name": r.partner.name if r.partner else "Partner",
            "plan_name": r.subscription.meal_plan.name if (r.subscription and r.subscription.meal_plan) else "Standard",
        }
        for r in redemptions
    ]


class CreateMealPlanRequest(BaseModel):
    name: str
    tier: str
    price_myr: float
    credits: int
    description: Optional[str] = None
    is_active: bool = True


@router.post("/meal-plans")
async def create_meal_plan(
    req: CreateMealPlanRequest,
    db: AsyncSession = Depends(get_db),
):
    plan = MealPlan(
        name=req.name,
        tier=req.tier,
        price_myr=req.price_myr,
        credits=req.credits,
        description=req.description,
        is_active=req.is_active,
    )
    db.add(plan)
    await db.commit()
    await db.refresh(plan)
    return plan


class UpdateMealPlanRequest(BaseModel):
    name: Optional[str] = None
    tier: Optional[str] = None
    price_myr: Optional[float] = None
    credits: Optional[int] = None
    description: Optional[str] = None
    is_active: Optional[bool] = None


@router.put("/meal-plans/{plan_id}")
async def update_meal_plan(
    plan_id: uuid.UUID,
    req: UpdateMealPlanRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(MealPlan).where(MealPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")

    if req.name is not None:
        plan.name = req.name
    if req.tier is not None:
        plan.tier = req.tier
    if req.price_myr is not None:
        plan.price_myr = req.price_myr
    if req.credits is not None:
        plan.credits = req.credits
    if req.description is not None:
        plan.description = req.description
    if req.is_active is not None:
        plan.is_active = req.is_active

    await db.commit()
    await db.refresh(plan)
    return plan


class UpdatePartnerStatusRequest(BaseModel):
    status: Optional[str] = None
    is_active: Optional[bool] = None


@router.put("/partners/{partner_id}")
async def update_partner_status(
    partner_id: uuid.UUID,
    req: UpdatePartnerStatusRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Partner).where(Partner.id == partner_id)
    res = await db.execute(stmt)
    partner = res.scalar_one_or_none()
    if not partner:
        raise HTTPException(status_code=404, detail="Partner not found")

    if req.status is not None:
        partner.status = req.status
    if req.is_active is not None:
        partner.is_active = req.is_active

    await db.commit()
    await db.refresh(partner)
    return partner


@router.get("/waitlist")
async def list_admin_waitlist(db: AsyncSession = Depends(get_db)):
    """Retrieve all waitlist signups for admin inspection."""
    stmt = select(WaitlistSignup).order_by(WaitlistSignup.created_at.desc())
    res = await db.execute(stmt)
    entries = res.scalars().all()
    return [
        {
            "id": str(e.id),
            "email": e.email,
            "full_name": e.full_name or "Student",
            "university": "Albukhary International University",
            "phone": None,
            "source": "Landing Page",
            "created_at": e.created_at.isoformat() if e.created_at else datetime.now(timezone.utc).isoformat(),
        }
        for e in entries
    ]

