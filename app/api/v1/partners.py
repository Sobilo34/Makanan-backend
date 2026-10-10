import uuid
from typing import List, Optional
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select, update
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_password_hash, create_access_token
from app.core.dependencies import get_current_user, require_role, get_current_partner
from app.models import User, Partner, PartnerApplication, Meal, Redemption, Settlement
from app.schemas import (
    PartnerOut,
    PartnerApplyRequest,
    MealOut,
    MealCreate,
    MealUpdate,
    VerifyQRRequest,
    VerifyQROut,
    ConfirmRedemptionRequest,
    SettlementOut,
)
from app.services.redemption_service import RedemptionService
from app.services.settlement_service import SettlementService

router = APIRouter(prefix="/partners", tags=["Partners"])


@router.post("/apply")
async def partner_apply(req: PartnerApplyRequest, db: AsyncSession = Depends(get_db)):
    """Submits partner application and sets up partner user account."""
    # Check email
    user_stmt = select(User).where(User.email == req.email.lower().strip())
    user_res = await db.execute(user_stmt)
    if user_res.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Account with this email already exists")

    async with db.begin():
        # 1. Create Partner User
        user = User(
            email=req.email.lower().strip(),
            password_hash=get_password_hash(req.password),
            full_name=req.owner_name.strip(),
            role="partner",
            phone=req.phone,
        )
        db.add(user)
        await db.flush()

        # 2. Create Partner Record
        partner = Partner(
            user_id=user.id,
            name=req.businessName if hasattr(req, "businessName") else req.business_name,
            location=req.location,
            email=req.email.lower().strip(),
            phone=req.phone,
            description=req.description,
            status="active",
        )
        db.add(partner)

        # 3. Create Application Record
        application = PartnerApplication(
            business_name=req.business_name,
            owner_name=req.owner_name,
            email=req.email.lower().strip(),
            phone=req.phone,
            location=req.location,
            address=req.address,
            opening_time=req.opening_time,
            closing_time=req.closing_time,
            operating_days=req.operating_days,
            description=req.description,
            cuisine_types=req.cuisine_types,
            seating_capacity=req.seating_capacity,
            status="approved",
        )
        db.add(application)

    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "partner_id": partner.id}


@router.get("/me", response_model=PartnerOut)
async def get_my_partner_profile(
    current_partner: Partner = Depends(get_current_partner),
):
    return current_partner


class UpdatePartnerProfileRequest(BaseModel):
    name: Optional[str] = None
    phone: Optional[str] = None
    location: Optional[str] = None
    description: Optional[str] = None
    price_per_meal: Optional[float] = None


@router.put("/me", response_model=PartnerOut)
async def update_my_partner_profile(
    req: UpdatePartnerProfileRequest,
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    if req.name is not None:
        current_partner.name = req.name.strip()
    if req.phone is not None:
        current_partner.phone = req.phone.strip()
    if req.location is not None:
        current_partner.location = req.location.strip()
    if req.description is not None:
        current_partner.description = req.description.strip()
    if req.price_per_meal is not None and req.price_per_meal > 0:
        current_partner.price_per_meal = req.price_per_meal

    await db.commit()
    await db.refresh(current_partner)
    return current_partner


@router.post("/verify-qr", response_model=VerifyQROut)
async def verify_qr(
    req: VerifyQRRequest,
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    """Called by cafeteria scanner to verify student's QR code in real time."""
    result = await RedemptionService.verify_qr(
        db=db,
        qr_code_or_token=req.qr_code_or_token,
        partner_id=current_partner.id,
    )
    return result


@router.post("/confirm-redemption")
async def confirm_redemption(
    req: ConfirmRedemptionRequest,
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    """Called when partner confirms meal handover."""
    result = await RedemptionService.confirm_redemption(
        db=db,
        redemption_id=req.redemption_id,
        partner_id=current_partner.id,
    )
    return result


@router.get("/redemptions")
async def get_partner_redemptions(
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Redemption)
        .options(selectinload(Redemption.user), selectinload(Redemption.meal))
        .where(Redemption.partner_id == current_partner.id)
        .order_by(Redemption.created_at.desc())
        .limit(100)
    )
    res = await db.execute(stmt)
    redemptions = res.scalars().all()

    return [
        {
            "id": r.id,
            "status": r.status,
            "qr_code": r.qr_code,
            "redeemed_at": r.redeemed_at,
            "created_at": r.created_at,
            "student_name": r.user.full_name if r.user else "Student",
            "meal_name": r.meal.name if r.meal else "Meal",
        }
        for r in redemptions
    ]


@router.get("/settlements")
async def get_partner_settlements(
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Settlement)
        .where(Settlement.partner_id == current_partner.id)
        .order_by(Settlement.created_at.desc())
    )
    res = await db.execute(stmt)
    settlements = res.scalars().all()

    paid = [s for s in settlements if s.status == "paid"]
    pending = [s for s in settlements if s.status in ["pending", "requested", "processing"]]

    total_paid = sum(float(s.total_amount_myr) for s in paid)
    pending_amount = sum(float(s.total_amount_myr) for s in pending)
    total_redemptions = sum(s.total_redemptions for s in settlements)

    return {
        "kpis": {
            "total_paid": total_paid,
            "pending_amount": pending_amount,
            "total_redemptions": total_redemptions,
            "last_paid_date": paid[0].paid_at if paid else None,
        },
        "settlements": settlements,
    }


@router.post("/request-payout")
async def request_payout(
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    """
    Authoritative payout request. Sums only unsettled redemptions and links them to settlement.
    """
    return await SettlementService.request_payout(db=db, partner_id=current_partner.id)


@router.get("/meals")
async def get_partner_meals(
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Meal).where(Meal.partner_id == current_partner.id).order_by(Meal.created_at.desc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/meals")
async def create_partner_meal(
    req: MealCreate,
    current_partner: Partner = Depends(get_current_partner),
    db: AsyncSession = Depends(get_db),
):
    meal = Meal(
        partner_id=current_partner.id,
        name=req.name,
        description=req.description,
        category=req.category,
        tier=req.tier,
        price_myr=req.price_myr,
        calories=req.calories,
        prep_time_minutes=req.prep_time_minutes,
        image_url=req.image_url,
        availability=req.availability,
    )
    db.add(meal)
    await db.commit()
    await db.refresh(meal)
    return meal
