from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Redemption, Meal, Partner
from app.schemas import RedemptionRequest, RedemptionOut
from app.services.redemption_service import RedemptionService

router = APIRouter(prefix="/redemptions", tags=["Redemptions"])


@router.post("/redeem", response_model=RedemptionOut)
async def redeem_meal(
    req: RedemptionRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Atomically redeems a meal credit using SELECT ... FOR UPDATE.
    Prevents race conditions and double-spending.
    """
    result = await RedemptionService.create_redemption(
        db=db,
        user_id=current_user.id,
        subscription_id=req.subscription_id,
        meal_id=req.meal_id,
        partner_id=req.partner_id,
    )
    return result


@router.get("/history")
async def get_redemption_history(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Redemption)
        .options(selectinload(Redemption.meal), selectinload(Redemption.settlement))
        .where(Redemption.user_id == current_user.id)
        .order_by(Redemption.created_at.desc())
        .limit(50)
    )
    res = await db.execute(stmt)
    redemptions = res.scalars().all()

    # Enrich partner names
    output = []
    for r in redemptions:
        partner_name = "Cafeteria"
        if r.partner_id:
            p_res = await db.execute(select(Partner.name).where(Partner.id == r.partner_id))
            p_name = p_res.scalar_one_or_none()
            if p_name:
                partner_name = p_name

        output.append({
            "id": r.id,
            "status": r.status,
            "qr_code": r.qr_code,
            "redeemed_at": r.redeemed_at,
            "created_at": r.created_at,
            "meal": {"name": r.meal.name, "category": r.meal.category} if r.meal else None,
            "partner": {"name": partner_name},
        })
    return output
